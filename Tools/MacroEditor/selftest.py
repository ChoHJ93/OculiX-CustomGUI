# -*- coding: utf-8 -*-
"""GUI 없이 데이터 모델과 스키마를 검증한다.

편집기는 손으로 클릭해봐야 알 수 있는 부분이 많지만, 데이터 조작이 틀리면
매크로가 조용히 망가진다. 그 부분만이라도 자동으로 확인한다.

실행: python selftest.py
"""

import os
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

engine_conditions = {"imageExists", "imageMissing", "textExists", "textMissing",
                     "colorMatches", "not", "all", "any"}
check("조건 종류 일치", set(schema.CONDITION_TYPES.keys()) == engine_conditions)

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

v3 = model.Macro()
v3.append(None, None, {"type": "click", "steps": []})
check("click에 image/point 없으면 잡아냄",
      any("image" in p for p in v3.validate()))

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
