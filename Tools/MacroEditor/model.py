# -*- coding: utf-8 -*-
"""매크로 데이터 모델 - GUI와 무관한 순수 데이터 조작.

GUI 없이 단독으로 테스트할 수 있도록 tkinter에 의존하지 않는다.

단계 경로(path)는 int와 str이 번갈아 나오는 튜플이다.
    (3,)                 최상위 3번 단계
    (3, "then", 0)       3번 단계(if)의 then 분기 0번
    (1, "steps", 2, "else", 0)   중첩도 가능
"""

import copy
import json
import os

import graph_model
import pnginfo
import schema

# 자식 단계를 담는 컨테이너 키
CONTAINER_KEYS = {
    "if": ["then", "else"],
    "repeat": ["steps"],
}


def container_keys(step):
    """이 단계가 자식 단계를 가질 수 있으면 그 키 목록을 반환."""
    return CONTAINER_KEYS.get(step.get("type"), [])


class MacroError(Exception):
    pass


class Macro(object):

    def __init__(self, data=None, path=None):
        if data is None:
            data = self.blank()
        self.data = data
        self.path = path
        self.dirty = False

    # ------------------------------------------------------------ 생성/입출력

    @staticmethod
    def blank(name=u"새 매크로"):
        return {
            "name": name,
            "version": 1,
            "settings": {
                "screen": 0,
                "defaultSimilarity": 0.90,
                "defaultTimeout": 10,
                "stepDelay": 0,
            },
            "steps": [],
        }

    @classmethod
    def load(cls, path):
        f = open(path, "rb")
        try:
            raw = f.read()
        finally:
            f.close()
        data = json.loads(raw.decode("utf-8"))
        if "steps" not in data and "nodes" not in data:
            raise MacroError(u"'steps'(트리)도 'nodes'(그래프)도 없습니다: %s" % path)
        return cls(data, path)

    @property
    def is_graph(self):
        return "nodes" in self.data and "steps" not in self.data

    def save(self, path=None):
        target = path or self.path
        if not target:
            raise MacroError(u"저장 경로가 없습니다")
        folder = os.path.dirname(target)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        text = json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=False)
        f = open(target, "wb")
        try:
            f.write(text.encode("utf-8"))
            f.write(b"\n")
        finally:
            f.close()
        self.path = target
        self.dirty = False
        return target

    @property
    def folder(self):
        """이 매크로 json이 있는 폴더."""
        if not self.path:
            return None
        return os.path.dirname(os.path.abspath(self.path))

    @property
    def resource_folder(self):
        """이미지가 놓이는 폴더. 하위 매크로면 **부모 매크로 폴더**다.

        가족이 이미지 한 벌을 공유하므로, 실행기와 편집기가 같은 곳을 봐야
        한다. 여기가 어긋나면 '없는 이미지' 경고가 잘못 뜬다.
        """
        if not self.folder:
            return None
        return graph_model.family_root(self.folder)

    @property
    def scaling(self):
        """이 매크로에 적용되는 해상도 대응 설정. 없거나 잘못됐으면 None.

        하위 매크로는 자기 설정을 쓰지 않으므로 부모 것을 읽는다.
        """
        data = self.data
        root = self.resource_folder
        if root and os.path.normcase(root) != os.path.normcase(self.folder):
            data = graph_model.read_macro_file(os.path.join(root, "macro.json"))
        spec = graph_model.scaling_of(data)
        if spec is None or graph_model.validate_scaling(
                {"settings": {"scaling": spec}}):
            return None
        return spec

    # ---------------------------------------------------------------- 경로 조작

    @property
    def steps(self):
        return self.data.setdefault("steps", [])

    def _resolve(self, path):
        """path가 가리키는 단계가 속한 리스트와 인덱스를 반환."""
        if not path:
            raise MacroError(u"빈 경로")
        lst = self.steps
        i = 0
        while i < len(path) - 1:
            index = path[i]
            key = path[i + 1]
            if not isinstance(index, int) or not isinstance(key, basestring_types):
                raise MacroError(u"잘못된 경로 형식: %r" % (path,))
            if index < 0 or index >= len(lst):
                raise MacroError(u"경로 범위 초과: %r" % (path,))
            lst = lst[index].setdefault(key, [])
            i += 2
        return lst, path[-1]

    def get(self, path):
        lst, index = self._resolve(path)
        if index < 0 or index >= len(lst):
            raise MacroError(u"경로 범위 초과: %r" % (path,))
        return lst[index]

    def insert(self, path, step):
        """path 위치에 삽입. 기존 항목은 뒤로 밀린다."""
        lst, index = self._resolve(path)
        index = max(0, min(index, len(lst)))
        lst.insert(index, step)
        self.dirty = True
        return path[:-1] + (index,)

    def append(self, parent_path, key, step):
        """컨테이너 단계(if/repeat)의 자식 리스트 끝에 추가.

        parent_path 가 None 이면 최상위에 추가한다.
        """
        if parent_path is None:
            self.steps.append(step)
            self.dirty = True
            return (len(self.steps) - 1,)
        parent = self.get(parent_path)
        if key not in container_keys(parent):
            raise MacroError(u"%r 단계는 '%s' 자식을 가질 수 없습니다"
                             % (parent.get("type"), key))
        lst = parent.setdefault(key, [])
        lst.append(step)
        self.dirty = True
        return parent_path + (key, len(lst) - 1)

    def remove(self, path):
        lst, index = self._resolve(path)
        if index < 0 or index >= len(lst):
            raise MacroError(u"경로 범위 초과: %r" % (path,))
        removed = lst.pop(index)
        self.dirty = True
        return removed

    def move(self, path, delta):
        """같은 리스트 안에서 위/아래로 이동. 새 경로를 반환."""
        lst, index = self._resolve(path)
        target = index + delta
        if target < 0 or target >= len(lst):
            return path
        lst[index], lst[target] = lst[target], lst[index]
        self.dirty = True
        return path[:-1] + (target,)

    def duplicate(self, path):
        lst, index = self._resolve(path)
        clone = copy.deepcopy(lst[index])
        lst.insert(index + 1, clone)
        self.dirty = True
        return path[:-1] + (index + 1,)

    def replace(self, path, step):
        lst, index = self._resolve(path)
        lst[index] = step
        self.dirty = True

    # ------------------------------------------------------------------ 순회

    def walk(self):
        """(path, step, depth)를 깊이 우선으로 순회."""
        for item in self._walk_list(self.steps, (), 0):
            yield item

    def _walk_list(self, lst, prefix, depth):
        for i, step in enumerate(lst):
            path = prefix + (i,)
            yield (path, step, depth)
            for key in container_keys(step):
                children = step.get(key) or []
                for item in self._walk_list(children, path + (key,), depth + 1):
                    yield item

    def count(self):
        if self.is_graph:
            return len(self.data.get("nodes") or [])
        n = 0
        for _ in self.walk():
            n += 1
        return n

    def all_steps(self):
        """트리든 그래프든 모든 단계 dict를 돌려준다."""
        if self.is_graph:
            return list(self.data.get("nodes") or [])
        return [s for _p, s, _d in self.walk()]

    # ------------------------------------------------------------------ 검사

    def validate(self, cautions=None):
        """엔진이 거부할 정의를 미리 잡아낸다. 문제 목록을 반환.

        `cautions` 에 리스트를 주면 오류는 아니지만 알아 두면 좋은 것들이
        거기에 담긴다. graph_model.validate_node_params 와 같은 방식이다.

        그래프 형식은 연결 구조까지 봐야 하므로 graph_model.Graph.validate()가
        담당한다. 여기서는 빈 목록을 돌려주고 호출부가 그쪽을 쓴다.
        """
        if self.is_graph:
            return []
        problems = graph_model.validate_scaling(self.data)
        for path, step, _depth in self.walk():
            stype = step.get("type")
            where = u"단계 %s (%s)" % (format_path(path), stype or u"타입없음")

            if not stype:
                problems.append(u"%s: type이 없습니다" % where)
                continue

            if stype == "repeat":
                has_times = "times" in step
                has_while = "while" in step
                if not has_times and not has_while:
                    problems.append(u"%s: times 또는 while이 필요합니다" % where)
                if has_while and "maxIterations" not in step:
                    problems.append(
                        u"%s: while 반복에는 maxIterations가 필수입니다 "
                        u"(무한 루프 방지)" % where)
                if has_times and has_while:
                    problems.append(u"%s: times와 while을 함께 쓸 수 없습니다" % where)

            if stype == "if" and "condition" not in step:
                problems.append(u"%s: condition이 없습니다" % where)

            if stype in ("waitImage", "waitVanish") and not step.get("image"):
                problems.append(u"%s: image가 필요합니다" % where)

            # 그래프 형식과 같은 규칙이다. 대상을 하나도 주지 않으면 커서가
            # 지금 있는 자리에서 그대로 실행되므로 오류가 아니라 경고다.
            if stype in ("click", "doubleClick", "rightClick", "hover", "wheel"):
                if not (step.get("image") or step.get("text")
                        or step.get("point")) and cautions is not None:
                    cautions.append(
                        u"%s: 대상이 없어 현재 커서 위치에서 그대로 실행됩니다. "
                        u"의도한 것이 아니면 이미지나 좌표를 지정하세요" % where)

            # 드래그는 '현재 커서 위치' 같은 기본값이 성립하지 않아 오류로 둔다.
            if stype == "drag":
                for side, side_label in (("from", u"시작"), ("to", u"끝")):
                    spot = step.get(side) or {}
                    if not (spot.get("image") or spot.get("text")
                            or spot.get("point")):
                        problems.append(
                            u"%s: 드래그 %s 지점에 image, text, point 중 "
                            u"하나가 필요합니다" % (where, side_label))

            if stype == "waitColor":
                if not step.get("point"):
                    problems.append(u"%s: point가 필요합니다" % where)
                if not step.get("rgb"):
                    problems.append(u"%s: rgb가 필요합니다" % where)
        return problems

    def _image_refs(self):
        """(위치, 이름, 절대경로) - 이 매크로가 참조하는 이미지 전부."""
        folder = self.resource_folder
        if self.is_graph:
            entries = [((n.get("id", "?"),), n) for n in (self.data.get("nodes") or [])]
        else:
            entries = [(p, s) for p, s, _d in self.walk()]
        refs = []
        for path, step in entries:
            for name in self._images_in(step):
                if name:
                    refs.append((format_path(path), name))
        for name in schema.condition_images(self.data.get("watch")):
            if name:
                refs.append((u"감시 조건", name))
        out = []
        for where, name in refs:
            full = name
            if folder and not os.path.isabs(full):
                # `@폴더` 에만 있는 이미지도 있는 이미지다
                found = graph_model.locate_image(folder, name)
                full = found["path"] if found else os.path.join(folder, name)
            out.append((where, name, full))
        return out

    def missing_images(self):
        """참조하는데 실제로 없는 이미지 파일 목록."""
        return [(where, name) for where, name, full in self._image_refs()
                if not os.path.exists(full)]

    def risky_images(self, system_dpi):
        """OculiX 마스크 매칭 버그에 걸리는 템플릿. (위치, 이름, 이유) 목록.

        투명 픽셀이 있는데 DPI 가 시스템과 다르면, 대상이 화면에 아직 없을 때
        'matchTemplateMask' 오류로 바로 실패한다. 자세한 이유는 pnginfo 참조.
        같은 파일을 여러 노드가 써도 한 번 읽는다.
        """
        verdicts = {}
        out = []
        for where, name, full in self._image_refs():
            if not os.path.exists(full):
                continue
            if full not in verdicts:
                verdicts[full] = pnginfo.mask_dpi_risk(full, system_dpi)
            if verdicts[full]:
                out.append((where, name, verdicts[full]))
        return out

    @staticmethod
    def _images_in(step):
        # 노드에 그림을 그리는 쪽과 같은 목록을 봐야 한다. schema 에 한 번만 둔다.
        return [name for _label, name in schema.image_params(step)]


def format_path(path):
    """(1, 'then', 0) -> '1 > then > 0'"""
    return u" > ".join(unicode_types(p) for p in path)


# Python 2/3 양쪽에서 동작하도록 (편집기는 Python 3, 참고용 스크립트는 2일 수 있음)
try:
    basestring_types = basestring
    unicode_types = unicode
except NameError:
    basestring_types = str
    unicode_types = str
