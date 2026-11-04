# -*- coding: utf-8 -*-
"""GUI 없이 데이터 모델과 스키마를 검증한다.

편집기는 손으로 클릭해봐야 알 수 있는 부분이 많지만, 데이터 조작이 틀리면
매크로가 조용히 망가진다. 그 부분만이라도 자동으로 확인한다.

실행: python selftest.py
"""

import os
import re
import sys
import json
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# model 이 graph_model 을 쓴다 (하위 매크로의 이미지 폴더 판정). 편집기와 같은
# 경로 설정을 여기서도 해 둬야 단독 실행이 된다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "Scripts", "Common"))

import graph_model
import model
import schema


PASS = []
FAIL = []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print("  [PASS] %-44s %s" % (name, detail))
    else:
        FAIL.append(name)
        print("  [FAIL] %-44s %s" % (name, detail))
    return condition


def section(title):
    print("")
    print("=== %s ===" % title)


# --------------------------------------------------------------- 스키마

section("스키마 정의")

engine_steps = {
    "log", "wait", "waitImage", "waitVanish", "click", "doubleClick",
    "rightClick", "hover", "mouseDown", "mouseUp", "drag", "wheel",
    "type", "key", "waitColor", "waitText", "if", "repeat", "break",
    "call", "run",
}
declared = set(schema.STEP_TYPES.keys())
check("엔진 지원 단계가 모두 등록됨", engine_steps <= declared,
      "누락: %s" % sorted(engine_steps - declared))
check("엔진에 없는 단계가 없음", declared <= engine_steps,
      "초과: %s" % sorted(declared - engine_steps))

# 목록을 여기 또 적지 않는다. 두 벌이 되면 한쪽만 갱신돼서 (paramCompare 가
# 그랬다) 멀쩡한 조건을 테스트가 실패로 잡는다.
engine_conditions = set(graph_model.CONDITION_TYPES)
check("조건 종류 일치", set(schema.CONDITION_TYPES.keys()) == engine_conditions,
      "schema 만: %s / graph_model 만: %s"
      % (sorted(set(schema.CONDITION_TYPES.keys()) - engine_conditions),
         sorted(engine_conditions - set(schema.CONDITION_TYPES.keys()))))

ok = True
for stype in schema.STEP_TYPES:
    for field in schema.fields_for(stype):
        if "name" not in field or "type" not in field or "label" not in field:
            ok = False
            print("      필드 정의 불완전: %s / %r" % (stype, field))
check("모든 필드 정의에 name/type/label 있음", ok)

for stype in schema.STEP_TYPES:
    step = schema.new_step(stype)
    if step.get("type") != stype:
        check("new_step(%s)" % stype, False)
        break
else:
    check("new_step()이 모든 종류 생성 가능", True,
          "%d종" % len(schema.STEP_TYPES))

check("if는 then/else 컨테이너를 가짐",
      schema.containers_for("if") == ["then", "else"])
check("repeat는 steps 컨테이너를 가짐",
      schema.containers_for("repeat") == ["steps"])
check("model과 schema의 컨테이너 정의 일치",
      all(model.CONTAINER_KEYS.get(t, []) == schema.containers_for(t)
          for t in schema.STEP_TYPES))


# --------------------------------------------------------------- 경로 조작

section("단계 트리 조작")

m = model.Macro()
m.append(None, None, schema.new_step("log"))
m.append(None, None, schema.new_step("if"))
m.append(None, None, schema.new_step("repeat"))
check("최상위 3개 추가", len(m.steps) == 3)

if_path = (1,)
p1 = m.append(if_path, "then", schema.new_step("click"))
p2 = m.append(if_path, "then", schema.new_step("wait"))
p3 = m.append(if_path, "else", schema.new_step("log"))
check("if의 then에 2개, else에 1개",
      len(m.get(if_path)["then"]) == 2 and len(m.get(if_path)["else"]) == 1,
      "%s %s %s" % (p1, p2, p3))

rep_path = (2,)
m.append(rep_path, "steps", schema.new_step("log"))
nested = m.append(rep_path, "steps", schema.new_step("if"))
m.append(nested, "then", schema.new_step("break"))
check("중첩 컨테이너 (repeat > if > then)",
      m.get(nested + ("then", 0))["type"] == "break", "%s" % (nested,))

check("get(path) 정확", m.get(p1)["type"] == "click")

moved = m.move(p1, 1)
check("move 아래로", m.get(moved)["type"] == "click" and moved == (1, "then", 1))
moved = m.move(moved, -1)
check("move 위로 (원위치)", moved == (1, "then", 0))
check("경계에서 move는 무시", m.move((0,), -1) == (0,))

dup = m.duplicate(p1)
check("duplicate", len(m.get(if_path)["then"]) == 3 and dup == (1, "then", 1))
# 깊은 복사인지: 원본을 바꿔도 복제본이 안 따라와야 한다
m.get(p1)["label"] = u"원본만"
check("duplicate는 깊은 복사", m.get(dup).get("label") != u"원본만")
m.remove(dup)

removed = m.remove((0,))
check("remove", removed["type"] == "log" and len(m.steps) == 2)

before = m.count()
inserted = m.insert((0,), schema.new_step("log"))
check("insert가 앞으로 밀어냄",
      m.get((0,))["type"] == "log" and m.count() == before + 1,
      "%s" % (inserted,))

paths = [p for p, _s, _d in m.walk()]
check("walk가 중첩까지 순회", len(paths) == m.count(), "%d개" % len(paths))
check("walk 경로가 전부 유효", all(m.get(p) is not None for p in paths))

depths = dict((p, d) for p, _s, d in m.walk())
check("중첩 깊이 계산", depths[nested + ("then", 0)] == 2)

try:
    m.get((99,))
    check("범위 밖 접근은 예외", False)
except model.MacroError:
    check("범위 밖 접근은 예외", True)

try:
    m.append((0,), "then", schema.new_step("log"))
    check("log에 자식 추가는 거부", False)
except model.MacroError:
    check("log에 자식 추가는 거부", True)


# --------------------------------------------------------------- 저장/불러오기

section("저장 / 불러오기 왕복")

tmp = tempfile.mkdtemp(prefix="macroeditor_")
try:
    m.data["name"] = u"한글 이름 테스트"
    m.append(None, None, dict(schema.new_step("log"), message=u"한글 메시지 ✓"))
    target = os.path.join(tmp, "Sample", "macro.json")
    m.save(target)
    check("저장 (폴더 자동 생성)", os.path.exists(target))

    raw = open(target, "rb").read().decode("utf-8")
    check("UTF-8로 저장되고 한글이 이스케이프되지 않음",
          u"한글 메시지" in raw)
    check("JSON으로 다시 파싱 가능", json.loads(raw) is not None)

    m2 = model.Macro.load(target)
    check("불러온 매크로가 동일", m2.data == m.data)
    check("folder 속성", m2.folder == os.path.dirname(target))
    check("불러온 직후 dirty 아님", m2.dirty is False)

    m2.append(None, None, schema.new_step("log"))
    check("수정하면 dirty", m2.dirty is True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------- 검증 규칙

section("정의 검증 (엔진이 거부할 것을 미리 잡기)")

v = model.Macro()
v.append(None, None, {"type": "repeat", "while": {"type": "imageExists",
                                                  "image": "a.png"}, "steps": []})
problems = v.validate()
check("while에 maxIterations 없으면 잡아냄",
      any("maxIterations" in p for p in problems),
      "%d건" % len(problems))

v2 = model.Macro()
v2.append(None, None, {"type": "repeat", "times": 3, "maxIterations": 5,
                       "while": {"type": "imageExists"}, "steps": []})
check("times와 while 동시 사용을 잡아냄",
      any(u"함께" in p for p in v2.validate()))

# 대상 없는 클릭은 '지금 커서 자리에서 실행' 이라 오류가 아니다.
# 의도한 경우가 드무니 경고로만 알린다 (그래프 형식과 같은 규칙).
v3 = model.Macro()
v3.append(None, None, {"type": "click", "steps": []})
_v3_cautions = []
_v3_problems = v3.validate(_v3_cautions)
check("대상 없는 클릭은 오류가 아니다",
      not any("image" in p for p in _v3_problems), "%r" % (_v3_problems,))
check("대상 없는 클릭은 경고로 알린다",
      any(u"현재 커서 위치" in c for c in _v3_cautions), "%r" % (_v3_cautions,))

v4 = model.Macro()
v4.append(None, None, {"type": "if", "then": [], "else": []})
check("if에 condition 없으면 잡아냄",
      any("condition" in p for p in v4.validate()))

v5 = model.Macro()
v5.append(None, None, {"type": "waitColor", "point": [1, 2]})
check("waitColor에 rgb 없으면 잡아냄",
      any("rgb" in p for p in v5.validate()))

good = model.Macro()
good.append(None, None, {"type": "repeat", "while": {"type": "imageExists",
                                                     "image": "a.png"},
                         "maxIterations": 10, "steps": []})
good.append(None, None, {"type": "click", "image": "b.png"})
check("올바른 정의는 문제 없음", good.validate() == [],
      "%r" % (good.validate(),))


# --------------------------------------------------------------- 요약 표시

section("트리 요약 문자열")

check("log 요약", u"안녕" in schema.summarize({"type": "log", "message": u"안녕"}))
check("click 이미지 요약",
      u"ok.png" in schema.summarize({"type": "click", "image": "ok.png"}))
check("click 좌표 요약",
      u"(10, 20)" in schema.summarize({"type": "click", "point": [10, 20]}))
check("repeat 횟수 요약",
      u"5회" in schema.summarize({"type": "repeat", "times": 5}))
check("repeat while 요약",
      u"while" in schema.summarize({"type": "repeat",
                                    "while": {"type": "imageExists", "image": "x.png"},
                                    "maxIterations": 9}))
check("if 조건 요약",
      u"x.png" in schema.summarize({"type": "if",
                                    "condition": {"type": "imageExists",
                                                  "image": "x.png"}}))
check("중첩 조건 요약",
      u"AND" in schema.describe_condition(
          {"type": "all", "conditions": [{"type": "imageExists", "image": "a.png"},
                                         {"type": "imageMissing", "image": "b.png"}]}))
check("label이 있으면 우선 표시",
      schema.summarize({"type": "log", "label": u"내 이름", "message": "x"}).startswith(u"내 이름"))


# --------------------------------------------------------------- 예제 매크로

section("기존 예제 매크로 호환성")

example = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "..", "Macros", "Example", "macro.json")
example = os.path.normpath(example)
if os.path.exists(example):
    ex = model.Macro.load(example)
    check("Example 매크로 로드", ex.count() > 0, "%d단계" % ex.count())
    check("Example 매크로 검증 통과", ex.validate() == [], "%r" % (ex.validate(),))
    unknown = [s.get("type") for _p, s, _d in ex.walk()
               if s.get("type") not in schema.STEP_TYPES]
    check("Example에 미지원 단계 없음", not unknown, "%r" % (unknown,))
    missing = ex.missing_images()
    check("Example의 이미지 파일 존재", not missing, "%r" % (missing,))
else:
    check("Example 매크로 존재", False, example)


# --------------------------------------------------------------- 투명 템플릿

section("투명 템플릿 + DPI 불일치 (OculiX matchTemplateMask 버그)")

import pnginfo
import struct
import zlib


def _png(path, color, rows, dpi=None, filters=(0,)):
    """테스트용 PNG 를 표준 라이브러리만으로 쓴다.

    rows 는 픽셀 튜플의 줄 목록. filters 의 필터를 줄마다 돌아가며 써서
    PNG 필터 풀기(_unfilter)까지 지나가게 한다.
    """
    channels = {2: 3, 6: 4}[color]
    width, height = len(rows[0]), len(rows)

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

    raw = bytearray()
    prev = bytearray(width * channels)
    for y, row in enumerate(rows):
        line = bytearray(v for px in row for v in px)
        kind = filters[y % len(filters)]
        out = bytearray()
        for i, v in enumerate(line):
            left = line[i - channels] if i >= channels else 0
            up_left = prev[i - channels] if i >= channels else 0
            pred = {0: 0, 1: left, 2: prev[i], 3: (left + prev[i]) >> 1,
                    4: paeth(left, prev[i], up_left)}[kind]
            out.append((v - pred) & 0xFF)
        raw.append(kind)
        raw.extend(out)
        prev = line
    data = b"\x89PNG\r\n\x1a\n" + chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0))
    if dpi is not None:
        ppm = int(round(dpi / 0.0254))
        data += chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    data += chunk(b"IDAT", zlib.compress(bytes(raw)))
    data += chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(data)
    return path


_pt = tempfile.mkdtemp(prefix="pnginfo_")
try:
    _opaque = [[(10 * x, 20 * y, 30, 255) for x in range(6)] for y in range(5)]
    _holed = [list(r) for r in _opaque]
    _holed[3][4] = (0, 0, 0, 0)                 # 투명 픽셀 하나 (필터 4 줄)
    _all_filters = (0, 1, 2, 3, 4)

    p1 = _png(os.path.join(_pt, "holed_nodpi.png"), 6, _holed,
              filters=_all_filters)
    info = pnginfo.read(p1)
    check("필터 0~4 를 풀어 투명 픽셀 하나를 찾는다",
          info is not None and info.transparent and info.dpi is None,
          "%r" % (info and (info.transparent, info.dpi),))
    check("투명 + DPI 기록 없음 -> 위험", pnginfo.mask_dpi_risk(p1, 120.0))

    p2 = _png(os.path.join(_pt, "holed_120.png"), 6, _holed, dpi=119.9896,
              filters=_all_filters)
    check("DPI 를 읽는다 (편집기 캡처와 같은 119.99)",
          abs(pnginfo.read(p2).dpi - 119.9896) < 0.05,
          "%r" % (pnginfo.read(p2).dpi,))
    check("투명 + DPI 120 (시스템과 같음) -> 안전",
          pnginfo.mask_dpi_risk(p2, 120.0) is None)

    p3 = _png(os.path.join(_pt, "holed_96.png"), 6, _holed, dpi=96)
    check("투명 + DPI 96 -> 위험 (125% PC 에서 실측으로 터진 값)",
          pnginfo.mask_dpi_risk(p3, 120.0))

    # 알파 채널만 있고 전부 불투명이면 OculiX 가 마스크를 쓰지 않는다.
    # 이 프로젝트에 그런 파일이 여럿 있어 헛경고를 내면 안 된다.
    p4 = _png(os.path.join(_pt, "opaque_nodpi.png"), 6, _opaque,
              filters=_all_filters)
    check("알파가 있어도 전부 불투명이면 안전",
          not pnginfo.read(p4).transparent
          and pnginfo.mask_dpi_risk(p4, 120.0) is None)

    p5 = _png(os.path.join(_pt, "rgb_nodpi.png"), 2,
              [[px[:3] for px in r] for r in _opaque])
    check("투명 없는 RGB 는 DPI 와 무관하게 안전",
          pnginfo.mask_dpi_risk(p5, 120.0) is None)

    p6 = os.path.join(_pt, "not_png.png")
    with open(p6, "wb") as handle:
        handle.write(b"GIF89a....")
    check("PNG 가 아니면 판정하지 않는다", pnginfo.read(p6) is None
          and pnginfo.mask_dpi_risk(p6, 120.0) is None)

    # 매크로 검사에 연결돼 있는가 - 노드 위치와 함께 한 번만 보고한다
    mdir = os.path.join(_pt, "Masked")
    os.makedirs(mdir)
    _png(os.path.join(mdir, "house.png"), 6, _holed)
    _png(os.path.join(mdir, "ok.png"), 6, _holed, dpi=119.9896)
    mm = model.Macro(graph_model.blank(u"투명"))
    mm.data["nodes"] = [
        {"id": "n1", "type": "waitImage", "image": "house.png"},
        {"id": "n2", "type": "click", "image": "house.png"},
        {"id": "n3", "type": "waitImage", "image": "ok.png"},
        {"id": "n4", "type": "waitImage", "image": "missing.png"},
    ]
    mm.save(os.path.join(mdir, "macro.json"))
    risky = mm.risky_images(120.0)
    check("검사가 위험한 템플릿을 쓰는 노드를 모두 짚는다",
          sorted((w, n) for w, n, _r in risky)
          == [("n1", "house.png"), ("n2", "house.png")], "%r" % (risky,))
    check("이유에 오류 이름과 고치는 법이 들어 있다",
          risky and u"matchTemplateMask" in risky[0][2]
          and u"[캡처]" in risky[0][2], risky and risky[0][2])
finally:
    shutil.rmtree(_pt, ignore_errors=True)


# --------------------------------------------------------------- 해상도 대응

section("저장된 창 위치 (모니터 구성이 바뀌었을 때)")

import screenutil

# 실제로 겪은 값. 왼쪽 모니터에 있던 창을 1920x1080 단일 모니터에서 열었다.
_one = [(0, 0, 1920, 1040)]
_text, _moved = screenutil.fit_geometry("1924x1041+-2065+-24", _one)
check("없는 모니터의 위치는 옮긴다", _moved, _text)
_m = re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", _text)
_w, _h, _x, _y = [int(v) for v in _m.groups()]
check("옮긴 창이 작업 영역 안에 들어온다",
      _x >= 0 and _y >= 0 and _x + _w <= 1920 and _y + _h + 32 <= 1040, _text)
check("크기는 화면에 맞게 줄인다", _w == 1920 and _h == 1008, _text)

_text, _moved = screenutil.fit_geometry("800x600+100+50", _one)
check("보이는 창은 그대로 둔다",
      _text == "800x600+100+50" and not _moved, _text)
_text, _moved = screenutil.fit_geometry("800x600+-300+50", _one)
check("일부가 밖이어도 제목 표시줄을 잡을 수 있으면 둔다", not _moved, _text)
_text, _moved = screenutil.fit_geometry("800x600+-750+50", _one)
check("제목 표시줄이 거의 안 보이면 옮긴다", _moved, _text)
_text, _moved = screenutil.fit_geometry("800x600+100+2000", _one)
check("세로로 벗어나도 옮긴다", _moved, _text)
_text, _moved = screenutil.fit_geometry("800x600+-20+-8", _one)
check("최대화에 가까운 음수 좌표는 옮기지 않는다", not _moved, _text)

_two = [(0, 0, 1920, 1040), (-2560, 0, 0, 1400)]
_text, _moved = screenutil.fit_geometry("1924x1041+-2065+-24", _two)
check("모니터가 그대로 있으면 왼쪽 음수 좌표도 그대로 둔다", not _moved, _text)
_off = [(0, 0, 1366, 728), (1366, 0, 3286, 1040)]
_text, _moved = screenutil.fit_geometry("900x700+-1500+10", _off)
check("주 모니터 기준으로 가운데에 놓는다",
      _text == "900x696+233+0", _text)

check("위치가 없는 값은 건드리지 않는다",
      screenutil.fit_geometry("1320x860", _one) == ("1320x860", False))
check("읽을 수 없는 값은 건드리지 않는다",
      screenutil.fit_geometry("망가진 값", _one) == (u"망가진 값", False))
check("모니터 정보를 못 얻으면 건드리지 않는다",
      screenutil.fit_geometry("800x600+-5000+0", [])
      == ("800x600+-5000+0", False))
_real = screenutil.work_areas()
check("실제 모니터의 작업 영역을 읽는다",
      len(_real) >= 1 and _real[0][2] > _real[0][0], "%r" % (_real,))


section("해상도 대응")

_ref = [1, 30, 1364, 1072]
_t = graph_model.Transform(_ref, [1, 31, 1278, 1000])
check("배율은 창 안쪽 기준", abs(_t.sx - 0.9370) < 0.0001
      and abs(_t.sy - 0.9328) < 0.0001 and abs(_t.scale - 0.9349) < 0.0001,
      "%.4f %.4f %.4f" % (_t.sx, _t.sy, _t.scale))
check("크기가 다르면 변환한다", not _t.identity)
check("좌표 변환", _t.point((88, 73)) == [83, 71], "%r" % (_t.point((88, 73)),))

_worst = 0
for _x in range(1, 1365, 37):
    for _y in range(30, 1102, 41):
        _back = _t.inverse_point(_t.point((_x, _y)))
        _worst = max(_worst, abs(_back[0] - _x), abs(_back[1] - _y))
check("왕복 오차 2px 이내", _worst <= 2, "최대 %d" % _worst)

check("영역은 바깥으로 넓어진다",
      _t.region([934, 898, 429, 206]) == [871, 836, 411, 201],
      "%r" % (_t.region([934, 898, 429, 206]),))
check("영역을 화면 안으로 자른다",
      _t.region([278, 57, 1171, 1106], [0, 0, 1920, 1080])
      == [256, 52, 1106, 1028])
check("화면을 벗어난 영역도 크기가 0 이 되지 않는다",
      _t.region([3000, 3000, 10, 10], [0, 0, 1920, 1080])[2:] == [1, 1])
check("영역 역변환", _t.inverse_region(_t.region([500, 500, 100, 100]))
      [2] > 100, "%r" % (_t.inverse_region(_t.region([500, 500, 100, 100])),))
check("오프셋도 함께 줄어든다", _t.offset((-96, 158)) == [-90, 147],
      "%r" % (_t.offset((-96, 158)),))

# 폭을 소수 버림하면 실제 렌더링에서 점수가 0.05 떨어진다 (Pattern.resize 의 문제)
check("템플릿 크기는 반올림 (1278x1000)", _t.image_size(341, 61) == (319, 57),
      "%r" % (_t.image_size(341, 61),))
_t2 = graph_model.Transform(_ref, [1, 38, 1279, 1006])
check("템플릿 크기는 반올림 (1279x1006)", _t2.image_size(341, 61) == (320, 57),
      "%r" % (_t2.image_size(341, 61),))
check("아주 작아도 1px 은 남는다",
      graph_model.Transform(_ref, [0, 0, 10, 10]).image_size(1, 1) == (1, 1))
check("가로세로비 차이", abs(_t.aspect_drift() - 0.0044) < 0.0002,
      "%.4f" % _t.aspect_drift())
check("축소본 폴더 이름", _t.size_key() == "1278x1000")

_same = graph_model.Transform(_ref, [0.8, 30.4, 1364.0, 1072.8])
check("물리값을 나눈 소수값도 기준으로 본다", _same.identity)
check("기준이면 좌표를 건드리지 않는다", _same.point((88, 73)) == [88, 73]
      and _same.region([1, 2, 3, 4]) == [1, 2, 3, 4]
      and _same.offset((5, 6)) == [5, 6])
check("3px 다르면 기준이 아니다",
      not graph_model.Transform(_ref, [1, 30, 1367, 1072]).identity)

# 스냅으로 옮겨 가는 창. 크기는 같고 위치만 다르다 (실제 실행에서 나온 값)
_moved = graph_model.Transform(_ref, [100, 200, 1364.0, 1072.8])
check("창 위치만 다르면 기준이 아니다", not _moved.identity)
check("창 위치만 다르면 크기가 바뀐 것이 아니다", not _moved.resized)
check("크기가 같으면 배율은 정확히 1", _moved.sx == 1.0 and _moved.sy == 1.0
      and _moved.scale == 1.0, "%r %r" % (_moved.sx, _moved.sy))
check("창 위치만 다르면 좌표만 옮긴다", _moved.point((88, 73)) == [187, 243],
      "%r" % (_moved.point((88, 73)),))
check("창 위치만 다르면 오프셋은 그대로다", _moved.offset((-96, 158)) == [-96, 158])
check("창 위치만 다르면 템플릿 크기도 그대로다",
      _moved.image_size(637, 483) == (637, 483))
check("창 위치만 다르면 그렇게 설명한다", u"창 위치만" in _moved.describe())
check("크기가 다르면 크기가 바뀐 것이다", _t.resized)

_spec = {"window": {"title": "x"}, "client": _ref, "screen": [2048, 1152]}
_s = graph_model.screen_view(_spec, (1920, 1080))
check("화면 공간은 화면 크기에 비례한다", _s.point((1000, 500)) == [938, 469],
      "%r" % (_s.point((1000, 500)),))
check("화면 공간의 오프셋은 그대로다", _s.offset((-96, 158)) == [-96, 158])
check("화면 공간은 내용물을 줄이지 않는다", not _s.scales_content)
check("작업 표시줄 영역이 1080p 화면 안에 들어온다",
      _s.region([145, 1104, 1607, 48], [0, 0, 1920, 1080])
      == [131, 1031, 1516, 49])

check("같은 크기 판정", graph_model.same_size((2048, 1152), (2049, 1151))
      and not graph_model.same_size((1920, 1080), (2048, 1152)))

_macro = {"settings": {"scaling": _spec}}
check("올바른 설정은 통과", graph_model.validate_scaling(_macro) == [])
check("설정이 없으면 통과", graph_model.validate_scaling({"settings": {}}) == [])
check("없으면 scaling_of 는 None",
      graph_model.scaling_of({"settings": {}}) is None)
for _bad, _why in (({"client": _ref, "screen": [1, 1]}, "창 지정 없음"),
                   ({"window": {"title": "x"}, "client": [1, 2, 3],
                     "screen": [1, 1]}, "client 개수"),
                   ({"window": {"title": "x"}, "client": [1, 2, 0, 3],
                     "screen": [1, 1]}, "client 크기 0"),
                   ({"window": {"title": "x"}, "client": _ref,
                     "screen": [0, 1]}, "screen 크기 0")):
    check("잘못된 설정을 잡는다: %s" % _why, len(graph_model.validate_scaling(
        {"settings": {"scaling": _bad}})) == 1)
check("잘못된 좌표 기준을 잡는다",
      len(graph_model.validate_scaling({"space": "moon"})) == 1)
check("노드의 잘못된 좌표 기준을 잡는다", len(graph_model.validate_node_params(
    [{"id": "n1", "type": "click", "point": [1, 2], "space": "moon"}])) == 1)
check("조건의 잘못된 좌표 기준을 잡는다", len(graph_model.validate_node_params(
    [{"id": "n1", "type": "if", "condition": {
        "type": "imageExists", "image": "a.png", "space": "moon"}}])) == 1)
check("올바른 좌표 기준은 통과", graph_model.validate_node_params(
    [{"id": "n1", "type": "click", "point": [1, 2], "space": "screen"}]) == [])

_it = tempfile.mkdtemp(prefix="scaling_")
try:
    def _touch(*parts):
        path = os.path.join(_it, *parts)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
        with open(path, "wb") as out:
            out.write(b"x")
        return path

    _base = _touch("a.png")
    _mine = _touch("@1920x1080", "a.png")
    _other = _touch("@1536x864", "b.png")
    graph_model.write_capture_info(os.path.join(_it, "@1920x1080"),
                                   (1920, 1080), [1, 31, 1278, 1000])

    _found = graph_model.locate_image(_it, "a.png", (1920, 1080))
    check("이 화면의 @폴더를 먼저 쓴다", _found["path"] == _mine
          and _found["capture"]
          and _found["client"] == [1.0, 31.0, 1278.0, 1000.0], "%r" % (_found,))
    _found = graph_model.locate_image(_it, "a.png", (2048, 1152))
    check("다른 화면은 기준 이미지를 쓴다", _found["path"] == _base
          and not _found["capture"])
    _found = graph_model.locate_image(_it, "a.png")
    check("화면을 모르면 기준 이미지를 쓴다", _found["path"] == _base)
    _found = graph_model.locate_image(_it, "b.png", (1920, 1080))
    check("기준 이미지가 없으면 다른 @폴더를 쓴다", _found["path"] == _other
          and _found["client"] is None)
    check("어디에도 없으면 None",
          graph_model.locate_image(_it, "c.png", (1920, 1080)) is None)
    check("절대 경로는 그대로", graph_model.locate_image(
        _it, _base)["path"] == _base)

    check("같은 이름 전부 모은다",
          graph_model.image_family(_it, "a.png") == [_base, _mine],
          "%r" % (graph_model.image_family(_it, "a.png"),))
    check("@폴더 경로를 기준 경로로", graph_model.base_image_path(_mine) == _base)
    check("기준 경로는 그대로", graph_model.base_image_path(_base) == _base)
    check("캡처 폴더 판별", graph_model.is_image_folder("@1920x1080")
          and graph_model.is_image_folder(".scaled")
          and not graph_model.is_image_folder("Sub"))

    graph_model.write_capture_info(os.path.join(_it, "@1920x1080"),
                                   (1920, 1080))
    check("창을 못 쟀으면 아는 값을 지우지 않는다",
          graph_model.read_capture_client(os.path.join(_it, "@1920x1080"))
          == [1.0, 31.0, 1278.0, 1000.0])
    check("축소본 경로", graph_model.scaled_image_path(_it, "a.png", _t)
          == os.path.join(_it, ".scaled", "1278x1000", "a.png"))
finally:
    shutil.rmtree(_it, ignore_errors=True)

_plain_macro = {"name": "t", "steps": [{"type": "log", "message": "x"}]}
_plain_model = model.Macro()
_plain_model.data = dict(_plain_macro, settings={"scaling": {"client": [1]}})
check("트리 형식도 잘못된 설정을 잡는다", len(_plain_model.validate()) >= 1)


# --------------------------------------------------------------- 결과

print("")
print("=" * 60)
print("passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    print("실패:")
    for name in FAIL:
        print("  - %s" % name)
    sys.exit(1)
print("SELFTEST_OK")
sys.exit(0)
