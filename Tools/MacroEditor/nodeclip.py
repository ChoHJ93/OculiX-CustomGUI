# -*- coding: utf-8 -*-
u"""노드 복사 / 붙여넣기 - 클립보드에 담기는 꾸러미와 그것을 옮겨심는 일.

고른 노드를 JSON 한 덩어리로 만들어 클립보드에 글자로 넣는다. 글자라서
편집기를 두 개 띄워 놓아도 서로 오가고, 같은 매크로 안에서도 그대로 쓴다.

옮길 때 손봐야 하는 것이 세 가지다.

노드 id
    붙여넣는 그래프에 이미 같은 id 가 있을 수 있으니 전부 새로 발급하고,
    꾸러미 안의 연결도 새 id 로 고쳐 잇는다. 고른 노드 **사이**의 연결만
    담기므로 바깥으로 나가던 연결은 따라오지 않는다.

이미지
    이미지 이름은 매크로 폴더 기준의 상대 이름이다. 다른 매크로에 붙이면
    그 폴더에 그 파일이 없다. 그래서 원본 폴더에서 복사해 온다.
    같은 이름이 이미 있으면 **덮어쓰지 않는다** - 내용이 같으면 그대로 쓰고,
    다르면 `이름 (2).png` 로 복사한 뒤 노드의 참조를 그 이름으로 바꾼다.
    남의 매크로가 쓰고 있는 그림을 조용히 갈아치우는 사고를 막기 위해서다.

호출 참조
    `./이름` 은 그 매크로 가족 안에서만 뜻이 있다. 가족이 다른 곳에 붙이면
    가리킬 곳이 없다. 여기서 몰래 고치지 않는다 - 붙여넣은 뒤 기존 호출
    검사(`MacroEditorApp.check_call_targets`)로 짚어서 로그에 알린다.

tkinter 에 기대지 않는다. 클립보드에 넣고 빼는 것은 `node_canvas` 쪽 일이다.
"""

import copy
import json
import os
import shutil

import graph_model
import schema


# 클립보드 글자의 첫머리에 들어가는 표식. 형식이 바뀌면 뒤의 숫자를 올린다.
KIND = "oculix.nodes/1"

# 이름 충돌 때 붙일 꼬리번호의 한계. 여기까지 가면 폴더가 이미 이상한 상태다.
MAX_RENAME = 200


# --------------------------------------------------------------------- 꾸러미

def pack(graph, node_ids, source_dir=None, source_name=None):
    u"""고른 노드와 그 사이의 연결만 떼어 낸 꾸러미를 만든다.

    노드 순서는 그래프에 실린 순서를 따른다. 붙여넣을 때 이 순서의 첫 노드가
    (빈 그래프라면) 시작 노드가 되므로, 집합의 들쭉날쭉한 순서를 쓰면
    붙여넣을 때마다 결과가 달라진다.
    """
    wanted = set(node_ids)
    ids = [n.get("id") for n in graph.nodes if n.get("id") in wanted]
    if not ids:
        return None
    inside = set(ids)
    return {
        "kind": KIND,
        "sourceDir": os.path.abspath(source_dir) if source_dir else None,
        "sourceName": source_name or u"",
        "nodes": [copy.deepcopy(graph.node(i)) for i in ids],
        "links": [copy.deepcopy(l) for l in graph.links
                  if l.get("from") in inside and l.get("to") in inside],
    }


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=1)


def loads(text):
    u"""클립보드 글자를 꾸러미로. 우리 것이 아니면 None.

    클립보드에는 아무 글자나 들어 있을 수 있다. 표식과 모양을 다 확인한다.
    """
    if not text or KIND not in text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("kind") != KIND:
        return None
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    for node in nodes:
        if not isinstance(node, dict) or not node.get("type"):
            return None
    links = data.get("links")
    if not isinstance(links, list):
        data["links"] = []
    return data


# ---------------------------------------------------------------------- 이미지

def image_names(payload):
    u"""꾸러미가 참조하는 이미지 이름들. 절대 경로는 뺀다.

    절대 경로는 폴더를 옮겨도 그대로 가리키므로 복사할 이유가 없다.
    """
    found = []
    for node in payload.get("nodes") or []:
        for _label, name in schema.image_params(node):
            if name and not os.path.isabs(name) and name not in found:
                found.append(name)
    return found


def _same_bytes(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        fa = open(a, "rb")
        try:
            fb = open(b, "rb")
            try:
                return fa.read() == fb.read()
            finally:
                fb.close()
        finally:
            fa.close()
    except OSError:
        return False


def _free_name(folder, name):
    u"""폴더에 없는 이름을 찾아 준다. `target.png` -> `target (2).png`."""
    head, tail = os.path.split(name)
    stem, ext = os.path.splitext(tail)
    for i in range(2, MAX_RENAME):
        candidate = os.path.join(head, u"%s (%d)%s" % (stem, i, ext)) \
            if head else u"%s (%d)%s" % (stem, i, ext)
        if not os.path.exists(os.path.join(folder, candidate)):
            return candidate.replace("\\", "/")
    return None


def _copy_variants(source, target_dir, name, new_name):
    u"""`@폴더` 에 다시 찍어 둔 이미지도 함께 옮긴다. 옮긴 개수를 돌려준다.

    옮기는 쪽에 이미 있으면 덮어쓰지 않는다 - 기준 이미지와 같은 원칙이다.
    """
    copied = 0
    for folder in graph_model.capture_folders(source):
        src = os.path.join(folder, name)
        if not os.path.isfile(src):
            continue
        folder_to = os.path.join(target_dir, os.path.basename(folder))
        if not os.path.isdir(folder_to):
            os.makedirs(folder_to)
        info = os.path.join(folder, graph_model.CAPTURE_INFO)
        info_to = os.path.join(folder_to, graph_model.CAPTURE_INFO)
        if os.path.isfile(info) and not os.path.isfile(info_to):
            shutil.copyfile(info, info_to)
        dst = os.path.join(folder_to, new_name)
        if not os.path.isfile(dst):
            shutil.copyfile(src, dst)
            copied += 1
    return copied


def import_images(payload, target_dir):
    u"""꾸러미의 이미지를 목적지 폴더로 가져온다.

    반환은 ({옛 이름: 새 이름}, [(로그 태그, 알림 줄)], 실제로 복사한 개수).
    이름이 그대로면 매핑에 넣지 않는다. 복사가 필요 없는 경우(같은 폴더)는
    아무것도 하지 않는다.
    """
    notes = []
    names = image_names(payload)
    if not names:
        return {}, notes, 0
    source = payload.get("sourceDir")
    if not target_dir:
        notes.append(("err",
                      u"매크로를 저장하지 않아 이미지를 가져오지 못했습니다 "
                      u"(%d개). 저장한 뒤 다시 붙여넣으세요" % len(names)))
        return {}, notes, 0
    if not source:
        notes.append(("err",
                      u"복사한 쪽 매크로가 저장 전이라 이미지를 가져오지 "
                      u"못했습니다 (%d개)" % len(names)))
        return {}, notes, 0
    if os.path.normcase(os.path.abspath(source)) == \
            os.path.normcase(os.path.abspath(target_dir)):
        return {}, notes, 0       # 같은 폴더다. 그림은 이미 제자리에 있다

    mapping = {}
    copied = 0
    for name in names:
        src = os.path.join(source, name)
        if not os.path.isfile(src):
            if graph_model.image_family(source, name):
                copied += _copy_variants(source, target_dir, name, name)
            else:
                notes.append(("err", u"원본 이미지가 없습니다: %s" % name))
            continue
        dst = os.path.join(target_dir, name)
        final = name
        if os.path.isfile(dst):
            if _same_bytes(src, dst):
                # 이미 같은 그림이 있다
                copied += _copy_variants(source, target_dir, name, name)
                continue
            renamed = _free_name(target_dir, name)
            if renamed is None:
                notes.append(("err",
                              u"이름이 겹쳐 가져오지 못했습니다: %s" % name))
                continue
            dst = os.path.join(target_dir, renamed)
            final = renamed
            mapping[name] = renamed
            notes.append(("info",
                          u"이름이 겹쳐 다른 이름으로 가져왔습니다: %s -> %s"
                          % (name, renamed)))
        try:
            folder = os.path.dirname(dst)
            if folder and not os.path.isdir(folder):
                os.makedirs(folder)
            shutil.copyfile(src, dst)
            copied += 1 + _copy_variants(source, target_dir, name, final)
        except Exception as exc:
            mapping.pop(name, None)
            notes.append(("err", u"이미지 복사 실패: %s (%s)" % (name, exc)))
    if copied:
        notes.append(("info",
                      u"이미지 %d개를 이 매크로 폴더로 가져왔습니다" % copied))
    return mapping, notes, copied


# -------------------------------------------------------------------- 옮겨심기

def paste(graph, payload, at=None, offset=(30, 30), image_map=None):
    u"""꾸러미를 그래프에 심는다. 새로 생긴 노드 id 를 순서대로 돌려준다.

    `at` 을 주면 꾸러미가 차지하던 사각형의 왼쪽 위 모서리를 그 월드 좌표에
    맞춘다(마우스가 가리킨 곳에 통째로 놓는 셈이다). 없으면 원래 자리에서
    `offset` 만큼 밀어 놓는다 - 같은 매크로에 붙일 때 원본과 겹치지 않게.
    """
    nodes = payload.get("nodes") or []
    if not nodes:
        return []
    xs = [int((n.get("ui") or {}).get("x", 0)) for n in nodes]
    ys = [int((n.get("ui") or {}).get("y", 0)) for n in nodes]
    if at is not None:
        dx, dy = int(at[0]) - min(xs), int(at[1]) - min(ys)
    else:
        dx, dy = int(offset[0]), int(offset[1])

    remap = {}
    new_ids = []
    for node in nodes:
        clone = copy.deepcopy(node)
        old_id = clone.pop("id", None)
        if image_map:
            schema.rewrite_images(clone, image_map)
        ui = clone.setdefault("ui", {})
        ui["x"] = int(ui.get("x", 0)) + dx
        ui["y"] = int(ui.get("y", 0)) + dy
        graph.add_node(clone)
        if old_id:
            remap[old_id] = clone["id"]
        new_ids.append(clone["id"])

    for link in payload.get("links") or []:
        from_id = remap.get(link.get("from"))
        to_id = remap.get(link.get("to"))
        if not from_id or not to_id:
            continue
        try:
            graph.connect(from_id, link.get("pin"), to_id)
        except graph_model.GraphError:
            # 핀 이름이 없는 노드 종류로 바뀐 오래된 꾸러미. 노드는 살리고
            # 연결만 버린다 - 통째로 실패시키는 것보다 고치기 쉽다.
            continue
    return new_ids
