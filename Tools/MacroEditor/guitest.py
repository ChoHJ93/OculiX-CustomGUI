# -*- coding: utf-8 -*-
"""GUI 코드 경로 검증.

마우스 클릭을 흉내내지 않고 위젯 구성 함수를 직접 호출한다.
속성 폼은 단계 종류마다 다른 위젯을 만들기 때문에, 한 종류라도 깨지면
그 단계를 고르는 순간 편집기가 죽는다. 그 사고를 여기서 잡는다.

실행: python guitest.py
"""

import io
import json
import os
import shutil
import sys
import tempfile
import tkinter as tk
from tkinter import ttk as ttk_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import macro_editor
import model
import node_canvas
import notify
import schema

PROJECT_ROOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Scripts", "Common"))
import graph_model

MACROS_REAL = os.path.join(PROJECT_ROOT, "Macros")

PASS = []
FAIL = []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print("  [%s] %-46s %s" % ("PASS" if condition else "FAIL", name, detail))
    return condition


def section(title):
    print("")
    print("=== %s ===" % title)


def _find_widgets(widget, kinds):
    """위젯 트리에서 주어진 클래스의 위젯을 만들어진 순서대로 모은다."""
    out = []
    for w in widget.winfo_children():
        if isinstance(w, kinds):
            out.append(w)
        out.extend(_find_widgets(w, kinds))
    return out


def _field_widget(widget, label, kinds):
    """속성 패널에서 이 라벨이 붙은 입력 위젯을 찾는다. 없으면 None.

    한 줄(Frame)이 [라벨][입력칸] 으로 이루어진다는 build_field 의 구조를
    그대로 이용한다. 순서 인덱스로 집으면 스키마에 필드가 하나 늘 때마다
    엉뚱한 칸을 집게 된다.
    """
    for frame in _find_widgets(widget, (ttk_module.Frame, ttk_module.LabelFrame)):
        names = [w for w in frame.winfo_children()
                 if isinstance(w, ttk_module.Label)]
        if not any(w.cget("text") == label for w in names):
            continue
        found = [w for w in frame.winfo_children() if isinstance(w, kinds)]
        if found:
            return found[0]
    return None


def _field_entry(widget, label):
    return _field_widget(widget, label, ttk_module.Entry)


def _field_text(widget, label):
    return _field_widget(widget, label, tk.Text)


def _all_labels(widget):
    """위젯 트리 안의 라벨 글자를 전부 모은다."""
    out = []
    for w in widget.winfo_children():
        if isinstance(w, ttk_module.Label):
            try:
                out.append(w.cget("text"))
            except Exception:
                pass
        out.extend(_all_labels(w))
    return out


import runlog as editor_runlog
import settings as editor_settings
import theme

# 실행 로그도 마찬가지다. 테스트가 사용자의 Logs\Runs 에 파일을 쌓거나
# latest.log 를 덮어쓰면 정작 필요할 때 진짜 로그를 밀어낸다.
_runlog_tmp = tempfile.mkdtemp(prefix="runlog_")
editor_runlog.LOG_DIR = os.path.join(_runlog_tmp, "Runs")
editor_runlog.LATEST = os.path.join(editor_runlog.LOG_DIR, "latest.log")

# 테스트가 사용자의 실제 편집기 설정을 읽거나 덮어쓰지 않게 격리한다.
# 이걸 안 하면 저장된 레이아웃에 따라 테스트 결과가 달라진다.
_settings_tmp = tempfile.mkdtemp(prefix="settings_")
_real_settings_path = editor_settings.PATH
editor_settings.PATH = os.path.join(_settings_tmp, "layout.json")

root = tk.Tk()
root.withdraw()                      # 화면에 띄우지 않는다
theme.apply(root)
# 저장된 창 위치가 없는 모니터를 가리키는 상태로 연다. 모니터를 뺀 뒤 창이
# 화면 밖에 떠서 보이지 않던 사고의 재현이다.
_real_load = macro_editor.settings.load
macro_editor.settings.load = lambda: dict(_real_load(),
                                          geometry="1400x900+-9000+-24")
app = macro_editor.MacroEditorApp(root)
macro_editor.settings.load = _real_load
root.update_idletasks()
_start_geometry = root.geometry()
root.withdraw()

section("앱 구성")
check("앱 생성", app is not None)
check("저장 위치가 화면 밖이면 보이는 곳에서 연다",
      macro_editor.screenutil.fit_geometry(_start_geometry)[1] is False,
      _start_geometry)
check("창을 옮겼다고 로그로 알린다",
      any(u"화면 밖" in _t for _t, _tag in app._log_buffer))
check("트리 위젯 존재", app.tree is not None)
check("빈 매크로로 시작", app.macro.count() == 0)


section("모든 단계 종류: 추가 + 속성 폼 생성")

for stype in schema.STEP_TYPES:
    try:
        app.macro = model.Macro()
        app.current_path = None
        app.apply_mode()
        app.add_step(stype)
        path = (0,)
        app.current_path = path
        app.build_properties()          # 여기서 위젯이 실제로 만들어진다
        root.update_idletasks()
        widgets = len(app.prop_frame.winfo_children())
        check(u"%s 속성 폼" % stype, widgets > 0, u"위젯 %d개" % widgets)
    except Exception as exc:
        check(u"%s 속성 폼" % stype, False, u"%s: %s" % (type(exc).__name__, exc))


section("모든 조건 종류: 조건 편집기 생성")

app.macro = model.Macro()
app.current_path = None
app.apply_mode()
app.add_step("if")
app.current_path = (0,)
for ctype in schema.CONDITION_TYPES:
    try:
        step = app.macro.get((0,))
        step["condition"] = schema.new_condition(ctype)
        app.build_properties()
        root.update_idletasks()
        check(u"조건 %s" % ctype, True)
    except Exception as exc:
        check(u"조건 %s" % ctype, False, u"%s: %s" % (type(exc).__name__, exc))


section("중첩 구조 트리 표시")

app.macro = model.Macro()
app.current_path = None
app.apply_mode()
app.add_step("repeat")
repeat_path = (0,)
app.macro.append(repeat_path, "steps", schema.new_step("if"))
inner_if = repeat_path + ("steps", 0)
app.macro.append(inner_if, "then", schema.new_step("click"))
app.macro.append(inner_if, "else", schema.new_step("break"))
app.refresh_tree()
root.update_idletasks()

items = app.tree.get_children("")
check("최상위 항목 1개", len(items) == 1)
step_items = [p for p in app.item_paths.values() if isinstance(p[-1], int)]
check("단계 노드 4개", len(step_items) == 4, u"%d개" % len(step_items))
bucket_items = [p for p in app.item_paths.values() if isinstance(p[-1], str)]
check("컨테이너 표시줄 3개 (steps/then/else)", len(bucket_items) == 3,
      u"%r" % ([p[-1] for p in bucket_items],))
check("깊이 3단계 경로 존재",
      any(len(p) == 5 for p in app.item_paths.values()),
      u"%r" % ([p for p in app.item_paths.values() if len(p) == 5],))


section("단계 조작")

app.macro = model.Macro()
app.current_path = None
app.apply_mode()
for t in ("log", "wait", "click"):
    app.add_step(t)
app.refresh_tree()
check("3개 추가됨", app.macro.count() == 3)

app.tree.selection_set(app.path_items[(0,)])
app.on_select()
app.move_step(1)
check("move로 순서 변경", app.macro.get((1,))["type"] == "log",
      u"%r" % [s["type"] for s in app.macro.steps])

app.tree.selection_set(app.path_items[(1,)])
app.on_select()
app.toggle_step()
check("toggle로 비활성화", app.macro.get((1,)).get("enabled") is False)
app.tree.selection_set(app.path_items[(1,)])
app.on_select()
app.toggle_step()
check("toggle로 다시 활성화 (키 제거)", "enabled" not in app.macro.get((1,)))

app.tree.selection_set(app.path_items[(1,)])
app.on_select()
app.duplicate_step()
check("duplicate", app.macro.count() == 4)

app.tree.selection_set(app.path_items[(1,)])
app.on_select()
app.delete_step()
check("delete", app.macro.count() == 3)


section("컨테이너 안으로 단계 추가")

app.macro = model.Macro()
app.current_path = None
app.apply_mode()
app.add_step("if")
app.refresh_tree()
app.tree.selection_set(app.path_items[(0,)])
app.on_select()
app.add_step("log")                  # if 선택 상태 -> then 안으로 들어가야 함
check("if 선택 상태에서 추가하면 then 안으로",
      len(app.macro.get((0,)).get("then") or []) == 1,
      u"then=%d else=%d" % (len(app.macro.get((0,)).get("then") or []),
                            len(app.macro.get((0,)).get("else") or [])))

app.refresh_tree()
else_path = (0, "else")
if else_path in app.path_items:
    app.tree.selection_set(app.path_items[else_path])
    app.on_select()
    app.add_step("wait")
    check(u"[거짓일 때] 표시줄 선택 후 추가하면 else 안으로",
          len(app.macro.get((0,)).get("else") or []) == 1)
else:
    check(u"[거짓일 때] 표시줄 존재", False)


section("값 편집 -> 데이터 반영")

app.macro = model.Macro()
app.current_path = None
app.apply_mode()
app.add_step("waitImage")
step = app.macro.get((0,))
app.current_path = (0,)
app.build_properties()

# 폼 대신 변환 함수를 직접 검증 (폼은 이 함수를 그대로 쓴다)
check("point 파싱", app._text_to_value("point", "100, 200") == [100, 200])
check("region 파싱", app._text_to_value("region", "1 2 3 4") == [1, 2, 3, 4])
check("rgb 파싱", app._text_to_value("rgb", "200,30,30") == [200, 30, 30])
check("tolerance 스칼라", app._text_to_value("tolerance", "10") == 10)
check("tolerance 채널별", app._text_to_value("tolerance", "10,5,20") == [10, 5, 20])
check("float 파싱", app._text_to_value("float", "0.9") == 0.9)
try:
    app._text_to_value("point", "1,2,3")
    check("잘못된 point는 거부", False)
except ValueError:
    check("잘못된 point는 거부", True)
check("값 -> 문자열 왕복", app._value_to_text([1, 2, 3]) == "1, 2, 3")


section("검사 기능")

app.macro = model.Macro()
app.macro.append(None, None, {"type": "repeat",
                              "while": {"type": "imageExists", "image": "a.png"},
                              "steps": []})
app.current_path = None
app.apply_mode()
check("maxIterations 누락을 검사가 잡음", app.validate_macro() is False)

app.macro = model.Macro()
app.macro.append(None, None, {"type": "log", "message": "hi"})
app.refresh_tree()
check("정상 매크로는 검사 통과", app.validate_macro() is True)


section("저장 -> 재로드 -> 트리 재구성")

tmp = tempfile.mkdtemp(prefix="guitest_")
try:
    app.macro = model.Macro(model.Macro.blank(u"통합 테스트"))
    app.current_path = None
    app.refresh_tree()
    app.add_step("repeat")
    app.macro.append((0,), "steps", schema.new_step("waitImage"))
    app.macro.get((0, "steps", 0))["image"] = "target.png"
    app.macro.append((0,), "steps", schema.new_step("click"))
    app.macro.get((0, "steps", 1))["point"] = [500, 300]
    app.refresh_tree()

    target = os.path.join(tmp, "IntegTest", "macro.json")
    app.macro.save(target)
    check("저장", os.path.exists(target))

    before = app.macro.count()
    app.macro = model.Macro.load(target)
    app.current_path = None
    app.refresh_tree()
    root.update_idletasks()
    check("재로드 후 단계 수 동일", app.macro.count() == before,
          u"%d -> %d" % (before, app.macro.count()))
    check("재로드 후 트리 재구성",
          len([p for p in app.item_paths.values() if isinstance(p[-1], int)]) == before)

    # 모든 단계를 하나씩 선택하며 속성 폼을 그려본다
    crashed = []
    for path in sorted([p for p in app.item_paths.values() if isinstance(p[-1], int)]):
        try:
            app.current_path = path
            app.build_properties()
            root.update_idletasks()
        except Exception as exc:
            crashed.append((path, exc))
    check("모든 단계 선택해도 폼이 죽지 않음", not crashed, u"%r" % (crashed,))
finally:
    shutil.rmtree(tmp, ignore_errors=True)


section("노드 그래프 모드")

import graph_model

app.macro = model.Macro(graph_model.blank(u"노드 테스트"))
app.current_path = None
app.apply_mode()
check("그래프 형식이면 노드 모드로 전환", app.mode == "graph", app.mode)
check("캔버스에 그래프가 연결됨", app.canvas_view.graph is not None)

for stype in schema.STEP_TYPES:
    try:
        node = app.canvas_view.add_node(stype, 0, 0)
        app.on_node_selected(node["id"])
        root.update_idletasks()
        ok = node is not None and len(app.prop_frame.winfo_children()) > 0
        if not ok:
            check(u"노드 %s 추가+속성" % stype, False)
            break
    except Exception as exc:
        check(u"노드 %s 추가+속성" % stype, False, u"%s: %s" % (type(exc).__name__, exc))
        break
else:
    check("모든 종류를 노드로 추가하고 속성 표시", True,
          u"%d종" % len(schema.STEP_TYPES))

g = app.canvas_view.graph
check("컨테이너 키가 노드에 남지 않음",
      all("then" not in n and "steps" not in n for n in g.nodes))

app.macro = model.Macro(graph_model.blank(u"연결"))
app.apply_mode()
n1 = app.canvas_view.add_node("log", 0, 0)
n2 = app.canvas_view.add_node("log", 200, 0)
n3 = app.canvas_view.add_node("if", 400, 0)
g = app.canvas_view.graph
check("첫 노드가 시작 노드가 됨", g.entry == n1["id"], g.entry)

g.connect(n1["id"], "next", n2["id"])
check("연결 생성", g.target(n1["id"], "next") == n2["id"])
g.connect(n1["id"], "next", n3["id"])
check("같은 출력 핀 재연결은 교체", g.target(n1["id"], "next") == n3["id"])
check("링크가 중복되지 않음", len(g.links) == 1, u"%d개" % len(g.links))

g.connect(n3["id"], "true", n2["id"])
g.connect(n3["id"], "false", n2["id"])
check("두 출력이 한 노드로 합류 가능", len(g.incoming(n2["id"])) == 2)

try:
    g.connect(n1["id"], "true", n2["id"])
    check("없는 핀 연결은 거부", False)
except graph_model.GraphError:
    check("없는 핀 연결은 거부", True)
try:
    g.connect(n1["id"], "next", n1["id"])
    check("자기 자신 연결은 거부", False)
except graph_model.GraphError:
    check("자기 자신 연결은 거부", True)

g.connect(n2["id"], "next", n1["id"])          # 순환 생성
errors, warnings = g.validate()
check("순환을 경고로 알림", any(u"순환" in w for w in warnings), u"%r" % (warnings,))

app.canvas_view._delete_node(n3["id"])
check("노드 삭제 시 관련 연결도 제거",
      all(l["from"] != n3["id"] and l["to"] != n3["id"] for l in g.links))

app.canvas_view.selected_node = None
app.canvas_view.selected_link = (n1["id"], "next")
app.canvas_view.delete_selection()
check("연결 선택 후 삭제", g.target(n1["id"], "next") is None)

app.canvas_view.auto_layout()
positions = [(n["ui"]["x"], n["ui"]["y"]) for n in g.nodes]
check("자동 정렬이 좌표를 배치", len(set(positions)) == len(positions),
      u"%r" % (positions,))

sx, sy = app.canvas_view.to_screen(100, 50)
wx, wy = app.canvas_view.to_world(sx, sy)
check("좌표 변환 왕복", abs(wx - 100) < 0.01 and abs(wy - 50) < 0.01)
app.canvas_view.zoom = 1.7
sx, sy = app.canvas_view.to_screen(100, 50)
wx, wy = app.canvas_view.to_world(sx, sy)
check("확대 상태에서도 왕복", abs(wx - 100) < 0.01 and abs(wy - 50) < 0.01)
app.canvas_view.reset_view()


section(u"매크로 매개변수")

# 값을 선언된 타입으로 맞춰서 넣는다. "3" 과 3 이 섞이면 비교 조건이 말없이
# 어긋나기 때문에, 못 맞추는 값은 조용히 넘기지 않고 거부한다.
for _v, _t, _want in [(3, "int", 3), ("3", "int", 3), (3.0, "int", 3),
                      ("2.5", "float", 2.5), (5, "string", u"5"),
                      ("yes", "bool", True), (u"거짓", "bool", False),
                      (True, "string", u"true")]:
    check(u"타입 변환 %r -> %s" % (_v, _t),
          graph_model.coerce_param(_v, _t) == _want,
          u"%r" % (graph_model.coerce_param(_v, _t),))
for _v, _t in [("3.5", "int"), ("abc", "int"), (True, "int"), ("maybe", "bool")]:
    try:
        graph_model.coerce_param(_v, _t)
        check(u"잘못된 값은 거부 %r/%s" % (_v, _t), False)
    except graph_model.ParamError:
        check(u"잘못된 값은 거부 %r/%s" % (_v, _t), True)

_decl = {"params": [{"name": "n", "type": "int", "default": 3},
                    {"name": "who", "type": "string"}]}
_vals, _bad = graph_model.bind_params(_decl, {"who": "abc"})
check(u"안 넘긴 값은 기본값으로", _vals == {"n": 3, "who": u"abc"} and not _bad,
      u"%r %r" % (_vals, _bad))
_vals, _bad = graph_model.bind_params(_decl, {"who": "abc", "n": "7"})
check(u"넘긴 값이 기본값을 덮는다", _vals.get("n") == 7 and not _bad, u"%r" % (_vals,))
_vals, _bad = graph_model.bind_params(_decl, {})
check(u"기본값 없는 매개변수를 빠뜨리면 오류",
      any(u"who" in b for b in _bad), u"%r" % (_bad,))
_vals, _bad = graph_model.bind_params(_decl, {"who": "a", "typo": 1})
check(u"선언에 없는 값을 넘기면 오류", any(u"typo" in b for b in _bad),
      u"%r" % (_bad,))

check(u"선언 검사 - 이름 중복",
      any(u"중복" in p for p in graph_model.validate_params(
          {"params": [{"name": "a", "type": "int"},
                      {"name": "a", "type": "int"}]})))
check(u"선언 검사 - 모르는 타입",
      any(u"타입" in p for p in graph_model.validate_params(
          {"params": [{"name": "a", "type": "date"}]})))
check(u"선언 검사 - 기본값이 타입과 안 맞음",
      any(u"기본값" in p for p in graph_model.validate_params(
          {"params": [{"name": "a", "type": "int", "default": "x"}]})),
      u"%r" % (graph_model.validate_params(
          {"params": [{"name": "a", "type": "int", "default": "x"}]}),))
check(u"선언이 없으면 조용하다", graph_model.validate_params({}) == [])

# 조건이 참조하는 매개변수는 선언돼 있어야 한다.
# 이름을 바꿨을 때 조건이 조용히 어긋나는 것을 막는 검사다.
_pg = graph_model.Graph(graph_model.blank(u"매개변수 분기"))
_pg.data["params"] = [{"name": "count", "type": "int", "default": 1}]
_pn = _pg.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "count", "op": ">=", "value": "3"}}, 0, 0)
_pg.entry = _pn["id"]
_pe, _pw = _pg.validate()
check(u"선언된 매개변수를 쓰면 통과", not _pe, u"%r" % (_pe,))
_pn["condition"]["param"] = "gone"
_pe, _pw = _pg.validate()
check(u"선언에 없는 매개변수를 쓰면 오류",
      any(u"gone" in e for e in _pe), u"%r" % (_pe,))
_pn["condition"]["param"] = "count"
_pn["condition"]["op"] = "=~"
_pe, _pw = _pg.validate()
check(u"모르는 비교 방법은 오류", any(u"비교 방법" in e for e in _pe),
      u"%r" % (_pe,))

# 중첩 조건(all/not) 안쪽의 매개변수도 잡아야 한다
_pg2 = graph_model.Graph(graph_model.blank(u"중첩"))
_pg2.data["params"] = [{"name": "count", "type": "int", "default": 1}]
_pn2 = _pg2.add_node({"type": "if", "condition": {
    "type": "all", "conditions": [
        {"type": "not", "condition": {"type": "paramCompare",
                                      "param": "nope", "op": "==",
                                      "value": "1"}}]}}, 0, 0)
_pg2.entry = _pn2["id"]
_pe2, _pw2 = _pg2.validate()
check(u"중첩 조건 안의 매개변수도 검사한다", any(u"nope" in e for e in _pe2),
      u"%r" % (_pe2,))

check(u"조건 한 줄 요약",
      schema.describe_condition({"type": "paramCompare", "param": "n",
                                 "op": ">=", "value": 3}) == u"n >= 3",
      schema.describe_condition({"type": "paramCompare", "param": "n",
                                 "op": ">=", "value": 3}))

# 호출 노드가 넘기는 값이 대상 선언과 맞는지 - 편집기가 실행 전에 잡아야 한다
_ptmp = tempfile.mkdtemp(prefix="params_")
_callee_dir = os.path.join(_ptmp, "Macros", "Callee")
os.makedirs(_callee_dir)
_callee = graph_model.blank(u"피호출")
_callee["params"] = [{"name": "who", "type": "string"}]
_cnode = {"id": "c1", "type": "log", "message": "hi", "ui": {"x": 0, "y": 0}}
_callee["nodes"] = [_cnode]
_callee["entry"] = "c1"
with io.open(os.path.join(_callee_dir, "macro.json"), "w", encoding="utf-8") as _fh:
    _fh.write(json.dumps(_callee, ensure_ascii=False))

_caller_dir = os.path.join(_ptmp, "Macros", "Caller")
os.makedirs(_caller_dir)
app.macro = model.Macro(graph_model.blank(u"호출자"),
                        path=os.path.join(_caller_dir, "macro.json"))
app.current_path = None
app.apply_mode()
_call = app.canvas_view.add_node("call", 0, 0)
_call["macro"] = "Callee"
app.graph.entry = _call["id"]

_call["args"] = {"who": "abc"}
check(u"맞는 값을 넘기면 통과", not app.check_call_targets(),
      u"%r" % (app.check_call_targets(),))
_call["args"] = {}
check(u"필수 값을 안 넘기면 잡는다",
      any(u"who" in p for p in app.check_call_targets()),
      u"%r" % (app.check_call_targets(),))
_call["args"] = {"who": "a", "wrongName": 1}
check(u"대상에 없는 값을 넘기면 잡는다",
      any(u"wrongName" in p for p in app.check_call_targets()),
      u"%r" % (app.check_call_targets(),))

# 반복 변수 참조는 아직 '값'이 아니다. 실행 전 검사가 타입 변환을 시도하면
# 정상 매크로가 정의 오류로 막힌다 - 실제로 그렇게 막혔던 자리다.
_loop = app.canvas_view.add_node("repeat", 0, 200)
_loop.pop("times", None)
_loop["forEach"] = {"param": "charNo", "type": "int", "values": [2, 3]}
app.graph.connect(_loop["id"], "body", _call["id"])
_call["args"] = {"who": graph_model.param_ref("charNo")}
check(u"반복 변수 참조를 넘겨도 실행 전 검사를 통과",
      not app.check_call_targets(), u"%r" % (app.check_call_targets(),))
check(u"참조를 넘긴 그래프에 정의 오류가 없다",
      not app.graph.validate()[0], u"%r" % (app.graph.validate()[0],))

_call["args"] = {"없는이름": graph_model.param_ref("charNo")}
check(u"참조라도 대상에 없는 이름이면 잡는다",
      any(u"없는이름" in p for p in app.check_call_targets()),
      u"%r" % (app.check_call_targets(),))

_call["args"] = {"who": graph_model.param_ref("타이포")}
check(u"이 매크로에 없는 이름을 참조하면 검사가 잡는다",
      any(u"타이포" in e for e in app.graph.validate()[0]),
      u"%r" % (app.graph.validate()[0],))

# 실행 시점에는 풀리지 않은 참조를 통과시키면 안 된다 (방어선)
_decl_ref = {"params": [{"name": "n", "type": "int"}]}
_v, _bad = graph_model.bind_params(
    _decl_ref, {"n": graph_model.param_ref("charNo")})
check(u"풀리지 않은 참조는 실행 시점 결합에서 막힌다",
      any(u"값으로 바뀌지 않았습니다" in b for b in _bad), u"%r" % (_bad,))

app.graph.remove_node(_loop["id"])      # 뒤 검사들이 쓰던 상태로 되돌린다
_call["args"] = {"who": "abc"}
check(u"반복 노드를 치우면 원래대로 통과", not app.check_call_targets(),
      u"%r" % (app.check_call_targets(),))

# 대상 매크로 선언을 읽어 칸을 만든다
_call["args"] = {"who": "abc"}
app.on_node_selected(_call["id"])
root.update_idletasks()
_cl = _all_labels(app.prop_frame)
check(u"호출 노드가 대상의 매개변수 칸을 만든다",
      any(u"who" in t and u"문자열" in t for t in _cl), u"%r" % (_cl,))
shutil.rmtree(_ptmp, ignore_errors=True)


section(u"드래그 경유지")


check(u"경유지 파싱 - 쉼표와 세미콜론",
      app._text_to_value("points", "300,400 ; 500,200") == [[300, 400], [500, 200]])
check(u"경유지 파싱 - 공백 구분도 허용",
      app._text_to_value("points", "300 400;500 200") == [[300, 400], [500, 200]])
check(u"빈 값은 빈 목록", app._text_to_value("points", "   ") == [])
for _bad in ("300,400,500", "abc", "1,2 ; 3"):
    try:
        app._text_to_value("points", _bad)
        check(u"잘못된 경유지는 거부 %r" % _bad, False)
    except ValueError:
        check(u"잘못된 경유지는 거부 %r" % _bad, True)
check(u"좌표 여러 개는 세미콜론으로 표시",
      app._value_to_text([[1, 2], [3, 4]]) == "1, 2 ; 3, 4",
      app._value_to_text([[1, 2], [3, 4]]))
check(u"좌표 하나는 예전 그대로", app._value_to_text([1, 2]) == "1, 2")
check(u"글자 -> 값 -> 글자 왕복",
      app._text_to_value("points", app._value_to_text([[300, 400], [500, 200]]))
      == [[300, 400], [500, 200]])

_wc = []
_werr = graph_model.validate_node_params([
    {"id": "d1", "type": "drag", "from": {"point": [1, 2]}, "to": {"point": [3, 4]},
     "waypoints": [[5, 6], [7, 8]]},
    {"id": "d2", "type": "drag", "from": {"point": [1, 2]}, "to": {"point": [3, 4]},
     "waypoints": [[5, 6], [7]]},
], _wc)
check(u"올바른 경유지는 통과", not any(u"d1" in e for e in _werr), u"%r" % (_werr,))
check(u"망가진 경유지는 오류", any(u"d2" in e and u"경유지 2번" in e for e in _werr),
      u"%r" % (_werr,))

app.macro = model.Macro()
app.current_path = None
app.apply_mode()
app.add_step("drag")
app.current_path = (0,)
app.build_properties()
root.update_idletasks()
_wl = _all_labels(app.prop_frame)
check(u"드래그 속성에 경유지 칸이 있다", u"경유지" in _wl, u"%r" % (_wl,))


section(u"노드에 이미지 매개변수 표시")

# 한 노드가 이미지를 여럿 쓸 수 있다. 어느 자리에 어떤 그림을 넣었는지
# 노드에서 바로 보여야 한다. 목록 정의는 schema 한 곳에만 둔다.
check(u"드래그는 시작/끝 두 장",
      schema.image_params({"type": "drag", "from": {"image": "s.png"},
                           "to": {"image": "e.png"}})
      == [(u"시작", "s.png"), (u"끝", "e.png")])
check(u"분기 조건의 이미지도 잡는다",
      schema.image_params({"type": "if", "condition": {
          "type": "imageExists", "image": "c.png"}}) == [(u"조건", "c.png")])
check(u"중첩 조건(all/not) 안쪽까지 훑는다",
      [n for _l, n in schema.image_params({"type": "if", "condition": {
          "type": "all", "conditions": [
              {"type": "imageExists", "image": "c1.png"},
              {"type": "not", "condition": {"type": "imageMissing",
                                            "image": "c2.png"}}]}})]
      == ["c1.png", "c2.png"])
check(u"repeat 의 while 조건도 잡는다",
      schema.image_params({"type": "repeat", "while": {
          "type": "imageExists", "image": "w.png"}}) == [(u"조건", "w.png")])
check(u"이미지가 없으면 빈 목록",
      schema.image_params({"type": "log", "message": "hi"}) == [])

_imgdir = os.path.join(MACROS_REAL, "RunHyperV")
if not os.path.isdir(_imgdir):
    skip(u"노드 썸네일 그리기", u"%s 가 없습니다" % _imgdir)
else:
    app.macro = model.Macro(graph_model.blank(u"썸네일"))
    app.current_path = None
    app.apply_mode()
    _tg = app.canvas_view.graph
    app.canvas_view.set_graph(_tg, base_dir=_imgdir)
    app.canvas_view.canvas.configure(width=1000, height=800)

    _drag = app.canvas_view.add_node("drag", 20, 20)
    _drag["from"] = {"image": "image_13.png"}
    _drag["to"] = {"image": "VM01_LoginButton.png"}
    _ifn = app.canvas_view.add_node("if", 20, 340)
    _ifn["condition"] = {"type": "imageExists", "image": "image_11.png"}
    _tg.entry = _drag["id"]
    app.canvas_view.redraw()
    root.update_idletasks()

    def _drawn(node_id, kind):
        return [i for i in app.canvas_view.canvas.find_withtag("node:%s" % node_id)
                if app.canvas_view.canvas.type(i) == kind]

    def _drawn_text(node_id):
        return [app.canvas_view.canvas.itemcget(i, "text")
                for i in _drawn(node_id, "text")]

    check(u"드래그는 그림 두 장을 그린다",
          len(_drawn(_drag["id"], "image")) == 2,
          u"%d개" % len(_drawn(_drag["id"], "image")))
    _dtext = _drawn_text(_drag["id"])
    check(u"어느 자리 그림인지 라벨이 붙는다",
          u"시작" in _dtext and u"끝" in _dtext, u"%r" % (_dtext,))
    check(u"분기 노드도 조건 이미지를 그린다",
          len(_drawn(_ifn["id"], "image")) == 1,
          u"%d개" % len(_drawn(_ifn["id"], "image")))

    # 접기 - Unity/UE 셰이더 노드처럼 그림만 접었다 편다
    _h_open = app.canvas_view.node_height(_drag)
    check(u"펼친 상태 아이콘은 ▼", u"▼" in _dtext, u"%r" % (_dtext,))
    app.canvas_view._toggle_images(_drag["id"])
    root.update_idletasks()
    _h_shut = app.canvas_view.node_height(_drag)
    check(u"접으면 그림이 사라진다", len(_drawn(_drag["id"], "image")) == 0)
    check(u"접으면 노드가 낮아진다", _h_shut < _h_open,
          u"%.0f -> %.0f" % (_h_open, _h_shut))
    _stext = _drawn_text(_drag["id"])
    check(u"접힌 상태 아이콘은 ▶", u"▶" in _stext, u"%r" % (_stext,))
    check(u"접어도 몇 장인지 알려준다",
          any(u"이미지 2장" in t for t in _stext), u"%r" % (_stext,))
    check(u"접은 상태가 노드에 저장된다",
          _drag["ui"].get("imagesCollapsed") is True, u"%r" % (_drag.get("ui"),))

    app.canvas_view._toggle_images(_drag["id"])
    root.update_idletasks()
    check(u"다시 펴면 그림이 돌아온다",
          len(_drawn(_drag["id"], "image")) == 2)
    check(u"펴면 기본값이라 키를 남기지 않는다",
          "imagesCollapsed" not in _drag["ui"], u"%r" % (_drag.get("ui"),))

    # 그림이 없는 노드에는 접기 아이콘도 없어야 한다
    _plain = app.canvas_view.add_node("log", 400, 20)
    app.canvas_view.redraw()
    root.update_idletasks()
    check(u"이미지 없는 노드엔 접기 아이콘이 없다",
          u"▼" not in _drawn_text(_plain["id"]),
          u"%r" % (_drawn_text(_plain["id"]),))

# 드래그 속성 폼에 오프셋 칸이 생겼는지
app.macro = model.Macro()
app.current_path = None
app.apply_mode()
app.add_step("drag")
app.current_path = (0,)
app.build_properties()
root.update_idletasks()



_dl = _all_labels(app.prop_frame)
check(u"드래그 시작/끝에 오프셋 칸이 있다", _dl.count(u"오프셋") == 2,
      u"%r" % (_dl,))
check(u"이미지·좌표 칸은 그대로", _dl.count(u"이미지") == 2 and _dl.count(u"좌표") == 2,
      u"%r" % (_dl,))


section(u"노드 머리에 id 표시")

# 로그와 검사 메시지가 노드 id 로 노드를 가리킨다. 화면에 그 값이 없으면
# 어떤 노드 이야기인지 대조할 수 없다. 이름은 왼쪽, id 는 오른쪽에 둔다.
app.macro = model.Macro(graph_model.blank(u"id 표시"))
app.current_path = None
app.apply_mode()
_ig = app.canvas_view.graph
app.canvas_view.canvas.configure(width=900, height=600)
_short = app.canvas_view.add_node("log", 20, 20)
_long = app.canvas_view.add_node("waitImage", 20, 200)
_long["label"] = u"아주 길고 긴 이름을 가진 노드입니다 정말로 깁니다"
_ig.entry = _short["id"]
app.canvas_view.redraw()
root.update_idletasks()


def _texts(node_id):
    """그 노드가 그린 텍스트 항목들. {글자: bbox}"""
    out = {}
    for item in app.canvas_view.canvas.find_withtag("node:%s" % node_id):
        if app.canvas_view.canvas.type(item) == "text":
            out[app.canvas_view.canvas.itemcget(item, "text")] = \
                app.canvas_view.canvas.bbox(item)
    return out


_a = _texts(_short["id"])
_b = _texts(_long["id"])
check(u"노드 id 가 그려진다", _short["id"] in _a and _long["id"] in _b,
      u"%r" % (sorted(_a.keys()),))

# 오른쪽 정렬: id 의 오른쪽 끝이 노드 오른쪽 가장자리 가까이에 있어야 한다
_rect = app.canvas_view.node_rect(_ig.node(_long["id"]))
_id_box = _b[_long["id"]]
check(u"id 는 오른쪽 정렬", _rect[2] - _id_box[2] < 14,
      u"노드 오른쪽 %r, id 오른쪽 %r" % (_rect[2], _id_box[2]))

# 이름은 왼쪽. 긴 이름이 id 를 침범하면 안 된다.
_title_box = _b[[k for k in _b if k.startswith(u"아주 길고")][0]]
check(u"이름은 왼쪽 정렬", _title_box[0] - _rect[0] < 20,
      u"%r vs %r" % (_title_box[0], _rect[0]))
check(u"긴 이름이 id 를 덮지 않는다", _title_box[2] <= _id_box[0],
      u"이름 오른쪽 %r, id 왼쪽 %r" % (_title_box[2], _id_box[0]))
check(u"넘치는 이름은 잘린다",
      any(k.endswith(u"…") for k in _b), u"%r" % (sorted(_b.keys()),))

# 시작 노드는 '시작' 표시와 id 가 함께 있어야 하고 서로 겹치면 안 된다
check(u"시작 노드는 시작 표시와 id 를 함께 보여준다",
      u"시작" in _a and _short["id"] in _a, u"%r" % (sorted(_a.keys()),))
check(u"'시작' 은 id 왼쪽에", _a[u"시작"][2] <= _a[_short["id"]][0],
      u"%r / %r" % (_a[u"시작"], _a[_short["id"]]))
check(u"시작 노드도 이름이 겹치지 않는다",
      _a[u"로그 출력"][2] <= _a[u"시작"][0],
      u"%r / %r" % (_a[u"로그 출력"], _a[u"시작"]))

# 폭 측정 헬퍼 자체
check(u"폭 측정은 글자 수가 아니라 픽셀",
      app.canvas_view._text_width(u"WWWW", ("맑은 고딕", 9, "bold")) >
      app.canvas_view._text_width(u"iiii", ("맑은 고딕", 9, "bold")))
check(u"자리가 없으면 빈 문자열",
      app.canvas_view._fit(u"어떤 이름", ("맑은 고딕", 9, "bold"), 0) == u"")

# 확대/축소해도 겹치면 안 된다. 작은 글씨는 최소 크기에서 멈추므로 축소할수록
# id 가 차지하는 비율이 커진다 - 배율마다 따로 확인해야 하는 이유다.
_ig.entry = _long["id"]
_zoom_bad = []
for _z in (0.35, 0.5, 1.0, 1.7, 2.5):
    app.canvas_view.zoom = _z
    app.canvas_view.redraw()
    root.update_idletasks()
    _boxes = _texts(_long["id"])
    _idb = _boxes.get(_long["id"])
    _names = [k for k in _boxes if k.startswith(u"아주") or k == u"…"]
    _tb = _boxes[_names[0]] if _names else None
    _sb = _boxes.get(u"시작")
    if _tb and _sb and _tb[2] > _sb[0]:
        _zoom_bad.append((_z, "이름-시작"))
    if _sb and _idb and _sb[2] > _idb[0]:
        _zoom_bad.append((_z, "시작-id"))
check(u"모든 배율에서 겹치지 않는다", not _zoom_bad, u"%r" % (_zoom_bad,))
app.canvas_view.reset_view()


section(u"고른 노드부터 실행")

# 노드를 하나만 골랐을 때만 동작해야 한다. 여러 개면 어디서 시작할지 모호하고,
# 하나도 없으면 대상이 없다. 실행 인자로만 전달하고 파일은 고치지 않는다.
import runner as runner_module

app.macro = model.Macro(graph_model.blank(u"부분 실행"))
app.current_path = None
app.apply_mode()
_rg = app.canvas_view.graph
_r1 = app.canvas_view.add_node("log", 0, 0)["id"]
_r2 = app.canvas_view.add_node("log", 240, 0)["id"]
_rg.entry = _r1
_saved_entry = _rg.entry

_rtmp = tempfile.mkdtemp(prefix="runfrom_")
app.macro.save(os.path.join(_rtmp, "RunFrom", "macro.json"))

# 아래부터 가짜 실행이 시작된다. 시험 중에 진짜 F6 을 잡지 않게 시험용 키로 둔다.
import hotkey as hotkey_module
app.pause_hotkey = hotkey_module.GlobalHotkey(0x87, lambda: None, hotkey_id=70)
check(u"편집기를 켠 직후에는 일시정지 버튼이 꺼져 있다",
      str(app.pause_button.cget("state")) == "disabled",
      str(app.pause_button.cget("state")))

_run_calls = []
_orig_run = runner_module.run_macro
runner_module.run_macro = (
    lambda path, on_line, on_done, start_node=None, resume=False:
    _run_calls.append((path, start_node)) or type(
        "FakeJob", (), {"is_running": lambda self: False, "stop": lambda self: None})())
try:
    app.canvas_view.set_selection([_r2], active=_r2)
    app.run_from_selected_node()
    check(u"하나만 고르면 그 노드부터 실행",
          len(_run_calls) == 1 and _run_calls[0][1] == _r2, u"%r" % (_run_calls,))
    check(u"매크로에 저장된 시작 노드는 그대로", _rg.entry == _saved_entry, _rg.entry)

    del _run_calls[:]
    app.job = None
    app.canvas_view.set_selection([_r1, _r2])
    app.run_from_selected_node()
    check(u"여러 개를 고르면 실행하지 않는다", _run_calls == [], u"%r" % (_run_calls,))
    check(u"여러 개일 때 이유를 알려 준다", u"하나만" in app.status.get(),
          app.status.get())

    del _run_calls[:]
    app.job = None
    app.canvas_view.set_selection([])
    app.run_from_selected_node()
    check(u"하나도 안 골랐으면 실행하지 않는다", _run_calls == [], u"%r" % (_run_calls,))

    # 트리 형식에서는 애초에 노드가 없다
    del _run_calls[:]
    app.job = None
    app.macro = model.Macro()
    app.current_path = None
    app.apply_mode()
    app.run_from_selected_node()
    check(u"트리 모드에서는 동작하지 않는다", _run_calls == [], u"%r" % (_run_calls,))
    check(u"트리 모드에서 이유를 알려 준다", u"노드 모드" in app.status.get(),
          app.status.get())
finally:
    runner_module.run_macro = _orig_run
    app.job = None
    shutil.rmtree(_rtmp, ignore_errors=True)

check(u"Shift+F5 바인딩", bool(app.root.bind("<Shift-F5>")))


section(u"입력 노드의 대상 검사")

# 대상을 하나도 주지 않은 클릭/휠은 '현재 커서 위치에서 실행'이라 오류가
# 아니다. 다만 의도한 경우가 드무니 경고로 알린다. 드래그는 그런 기본값이
# 없으므로 오류다 - 오류는 실행 자체를 막는다.
_cases = [
    {"id": "c1", "type": "click"},
    {"id": "c2", "type": "click", "point": [10, 20]},
    {"id": "w1", "type": "wheel"},
    {"id": "w2", "type": "wheel", "image": "a.png"},
    {"id": "d1", "type": "drag"},
    {"id": "d2", "type": "drag", "from": {"point": [1, 2]}},
    {"id": "d3", "type": "drag", "from": {"point": [1, 2]}, "to": {"image": "b.png"}},
    {"id": "m1", "type": "mouseDown"},
    {"id": "k1", "type": "key", "key": "ENTER"},
]
_cautions = []
_errors = graph_model.validate_node_params(_cases, _cautions)
_err_text = u" | ".join(_errors)
_note_text = u" | ".join(_cautions)

check(u"대상 없는 클릭은 오류가 아니다", u"c1(click)" not in _err_text, _err_text)
check(u"대상 없는 클릭은 경고로 알린다", u"c1(click)" in _note_text, _note_text)
check(u"대상 없는 휠도 경고로 알린다", u"w1(wheel)" in _note_text, _note_text)
check(u"대상을 준 클릭은 조용하다",
      u"c2(click)" not in _note_text and u"c2(click)" not in _err_text)
check(u"대상을 준 휠도 조용하다",
      u"w2(wheel)" not in _note_text and u"w2(wheel)" not in _err_text)
check(u"드래그는 두 지점이 없으면 오류",
      _err_text.count(u"d1(drag)") == 2, _err_text)
check(u"드래그 한쪽만 있어도 오류", u"d2(drag)" in _err_text, _err_text)
check(u"양쪽을 준 드래그는 통과",
      u"d3(drag)" not in _err_text and u"d3(drag)" not in _note_text)
check(u"mouseDown/key 는 원래 대상이 없어 조용하다",
      u"m1(" not in _err_text + _note_text and u"k1(" not in _err_text + _note_text)

# 오류는 실행을 막고 경고는 막지 않는다 - 그래프 전체 검사로 확인
_g = graph_model.Graph(graph_model.blank(u"대상 검사"))
_only_click = _g.add_node({"type": "click"}, 0, 0)
_g.entry = _only_click["id"]
_e, _w = _g.validate()
check(u"대상 없는 클릭만으로도 실행 가능한 그래프", not _e, u"%r" % (_e,))
check(u"그 경고가 warnings 로 올라온다",
      any(u"현재 커서 위치" in x for x in _w), u"%r" % (_w,))

# 트리 형식에도 같은 규칙이 따로 적혀 있다. 둘이 어긋나면 형식을 바꿨을 때
# 검사 결과가 달라진다.
_tree = model.Macro()
for _s in ({"type": "click"}, {"type": "wheel"}, {"type": "drag"},
           {"type": "click", "point": [1, 2]}, {"type": "mouseDown"}):
    _tree.append(None, None, dict(_s))
_tree_notes = []
_tree_errors = _tree.validate(_tree_notes)
check(u"트리 형식도 대상 없는 클릭을 오류로 보지 않는다",
      not any(u"click" in e for e in _tree_errors), u"%r" % (_tree_errors,))
check(u"트리 형식도 같은 경고를 낸다",
      sum(1 for x in _tree_notes if u"현재 커서 위치" in x) == 2,
      u"%r" % (_tree_notes,))
check(u"트리 형식도 드래그는 오류",
      sum(1 for e in _tree_errors if u"drag" in e) == 2, u"%r" % (_tree_errors,))
check(u"cautions 를 안 넘겨도 터지지 않는다", _tree.validate() is not None)


section(u"노드 다중 선택 / 그룹 이동")


class FakeEvent(object):
    """캔버스 바인딩에 넘길 최소한의 마우스 이벤트."""

    def __init__(self, x, y, state=0):
        self.x = x
        self.y = y
        self.state = state


def marquee(x0, y0, x1, y1, mode=node_canvas.SELECT_REPLACE):
    """빈 곳에서 눌러 끌었다가 떼는 동작을 그대로 재현한다."""
    cv._on_press(FakeEvent(x0, y0), mode)
    cv._on_drag(FakeEvent(x1, y1))
    cv._on_release(FakeEvent(x1, y1))


app.macro = model.Macro(graph_model.blank(u"다중 선택"))
app.current_path = None
app.apply_mode()
g = app.canvas_view.graph
cv = app.canvas_view
cv.reset_view()

na = cv.add_node("log", 0, 0)["id"]
nb = cv.add_node("log", 0, 220)["id"]
nfar = cv.add_node("log", 900, 900)["id"]
npart = cv.add_node("log", 260, 0)["id"]

ra = cv.node_rect(g.node(na))
rb = cv.node_rect(g.node(nb))
rp = cv.node_rect(g.node(npart))

# na, nb 를 완전히 감싸고 npart 는 왼쪽 절반만 걸치는 사각형
box = (min(ra[0], rb[0]) - 10, min(ra[1], rb[1]) - 10,
       (rp[0] + rp[2]) / 2.0, max(ra[3], rb[3]) + 10)
check(u"테스트 전제: npart 가 실제로 걸쳐 있다",
      box[2] > rp[0] and box[2] < rp[2])

marquee(*box)
check(u"범위 선택은 완전히 들어온 노드만 잡는다",
      cv.selected_nodes == {na, nb}, u"%r" % (sorted(cv.selected_nodes),))
check(u"범위 밖 노드는 선택되지 않는다", nfar not in cv.selected_nodes)
check(u"범위 선택 후 활성 노드가 정해진다", cv.selected_node in cv.selected_nodes)

# 되돌려 그리는 도중 좌표가 흐트러지지 않았는지
check(u"범위 선택은 노드를 움직이지 않는다",
      (g.node(na)["ui"]["x"], g.node(na)["ui"]["y"]) == (0, 0))

# Ctrl + 클릭 = 추가
cv._press_on_node(FakeEvent(*cv._input_anchor(g.node(nfar))), nfar,
                  node_canvas.SELECT_ADD)
cv._on_release(FakeEvent(*cv._input_anchor(g.node(nfar))))
check(u"Ctrl+클릭은 선택에 추가", cv.selected_nodes == {na, nb, nfar},
      u"%r" % (sorted(cv.selected_nodes),))
check(u"Ctrl+클릭한 노드가 활성이 된다", cv.selected_node == nfar)

# Alt + 클릭 = 제외
cv._press_on_node(FakeEvent(*cv._input_anchor(g.node(nb))), nb,
                  node_canvas.SELECT_REMOVE)
cv._on_release(FakeEvent(*cv._input_anchor(g.node(nb))))
check(u"Alt+클릭은 선택에서 제외", cv.selected_nodes == {na, nfar},
      u"%r" % (sorted(cv.selected_nodes),))
check(u"제외된 노드는 활성이 아니다", cv.selected_node != nb)

# Alt+클릭으로 뺀 노드는 끌려다니지 않아야 한다
before = (g.node(nb)["ui"]["x"], g.node(nb)["ui"]["y"])
cv._on_drag(FakeEvent(500, 500))
check(u"Alt+클릭 뒤에는 이동이 시작되지 않는다",
      (g.node(nb)["ui"]["x"], g.node(nb)["ui"]["y"]) == before)

# 그룹 이동: 선택된 것 중 하나를 잡고 끌면 전부 같은 만큼 움직인다
cv.set_selection([na, nfar], active=na)
start = {i: (g.node(i)["ui"]["x"], g.node(i)["ui"]["y"]) for i in (na, nfar, nb)}
grab = FakeEvent(*cv.to_screen(*cv._pos(g.node(na))))
cv._press_on_node(grab, na, node_canvas.SELECT_REPLACE)
cv._on_drag(FakeEvent(grab.x + 70, grab.y + 40))
cv._on_release(FakeEvent(grab.x + 70, grab.y + 40))
moved = {i: (g.node(i)["ui"]["x"], g.node(i)["ui"]["y"]) for i in (na, nfar, nb)}
check(u"선택한 노드가 함께 이동",
      moved[na] == (start[na][0] + 70, start[na][1] + 40)
      and moved[nfar] == (start[nfar][0] + 70, start[nfar][1] + 40),
      u"%r -> %r" % (start, moved))
check(u"선택 안 된 노드는 제자리", moved[nb] == start[nb])
check(u"그룹 이동 뒤에도 선택이 유지된다", cv.selected_nodes == {na, nfar})

# 여러 개를 고른 채 그중 하나를 그냥 클릭하면 그 하나만 남는다
click = FakeEvent(*cv.to_screen(*cv._pos(g.node(na))))
cv._press_on_node(click, na, node_canvas.SELECT_REPLACE)
check(u"누른 직후에는 선택이 유지된다(그룹 이동을 위해)",
      cv.selected_nodes == {na, nfar})
cv._on_release(click)
check(u"끌지 않고 떼면 하나로 줄어든다", cv.selected_nodes == {na},
      u"%r" % (sorted(cv.selected_nodes),))

# 빈 곳 클릭은 선택 해제
marquee(5, 5, 5, 5)
check(u"빈 곳 클릭은 선택 해제", cv.selected_nodes == set()
      and cv.selected_node is None)

# 범위 선택 모드 - 추가와 제외
marquee(*box)
rf = cv.node_rect(g.node(nfar))
marquee(rf[0] - 10, rf[1] - 10, rf[2] + 10, rf[3] + 10,
        node_canvas.SELECT_ADD)
check(u"Ctrl+범위 선택은 기존 선택에 더한다",
      nfar in cv.selected_nodes and nb in cv.selected_nodes,
      u"%r" % (sorted(cv.selected_nodes),))
marquee(rf[0] - 10, rf[1] - 10, rf[2] + 10, rf[3] + 10,
        node_canvas.SELECT_REMOVE)
check(u"Alt+범위 선택은 기존 선택에서 뺀다",
      nfar not in cv.selected_nodes and nb in cv.selected_nodes,
      u"%r" % (sorted(cv.selected_nodes),))

# selected_node 에 그냥 대입하면 선택이 하나로 초기화된다 (예전 코드 호환)
cv.selected_node = nb
check(u"selected_node 대입은 선택을 하나로 초기화", cv.selected_nodes == {nb})
cv.selected_node = None
check(u"selected_node = None 은 선택을 비운다", cv.selected_nodes == set())

# Delete 는 고른 노드를 전부 지운다
cv.set_selection([na, nb])
g.connect(na, "next", nb)
cv.delete_selection()
check(u"Delete 는 선택한 노드를 전부 삭제",
      g.node(na) is None and g.node(nb) is None)
check(u"삭제 뒤 선택이 비워진다",
      cv.selected_nodes == set() and cv.selected_node is None)
check(u"삭제된 노드의 연결도 사라진다",
      all(l["from"] not in (na, nb) and l["to"] not in (na, nb) for l in g.links))
check(u"삭제되지 않은 노드는 남는다", g.node(nfar) is not None)

# 실제 Tk 바인딩이 걸려 있는지. 위 검사들은 핸들러를 직접 부르므로
# 바인딩이 빠져도 통과해 버린다.
for pattern in ("<Button-1>", "<Control-Button-1>", "<Alt-Button-1>",
                "<B1-Motion>", "<ButtonRelease-1>"):
    check(u"바인딩 %s" % pattern, bool(cv.canvas.bind(pattern)))

# 수정 키 전용 바인딩이 오지 않는 환경을 대비한 보조 판정
check(u"state 비트로 Ctrl 판정",
      cv._mode_from_state(FakeEvent(0, 0, node_canvas.STATE_CTRL),
                          node_canvas.SELECT_REPLACE) == node_canvas.SELECT_ADD)
check(u"state 비트로 Alt 판정",
      cv._mode_from_state(FakeEvent(0, 0, node_canvas.STATE_ALT),
                          node_canvas.SELECT_REPLACE) == node_canvas.SELECT_REMOVE)
check(u"수정 키가 없으면 그대로",
      cv._mode_from_state(FakeEvent(0, 0, 0),
                          node_canvas.SELECT_REPLACE) == node_canvas.SELECT_REPLACE)

# 선택 사각형이 실제로 그려지는지 (stipple 같은 인자는 여기서만 검증된다)
try:
    cv._marquee = (10, 10, 120, 90)
    cv._draw_marquee()
    root.update_idletasks()
    check(u"선택 사각형 그리기", True)
except Exception as exc:
    check(u"선택 사각형 그리기", False, u"%s: %s" % (type(exc).__name__, exc))
cv._marquee = None

cv.reset_view()


section("매크로 호출 (라이브러리)")

app.macro = model.Macro(graph_model.blank(u"호출 테스트"))
app.current_path = None
app.apply_mode()

lib = app.available_macros()
check("라이브러리가 Macros 폴더를 읽음", isinstance(lib, list), u"%d개" % len(lib))
app.refresh_library()
check("라이브러리 목록 위젯이 채워짐", app.library_list.size() > 0,
      u"%d줄" % app.library_list.size())

node = app.canvas_view.add_node("call", 0, 0)
node["macro"] = "Example"
app.on_node_selected(node["id"])
root.update_idletasks()
check("호출 노드 속성 폼 생성", len(app.prop_frame.winfo_children()) > 0)
check("호출 노드 요약에 대상이 보임",
      "Example" in schema.summarize(node), schema.summarize(node))
check("호출 노드는 next + fail 핀",
      graph_model.pin_names("call") == ["next", "fail"],
      u"%r" % (graph_model.pin_names("call"),))

node["macro"] = "존재하지않는매크로"
problems = app.check_call_targets()
check("없는 호출 대상을 검사가 잡음",
      any(u"찾을 수 없습니다" in p for p in problems), u"%r" % (problems,))

node["macro"] = "Example"
problems = app.check_call_targets()
check("있는 호출 대상은 통과", not problems, u"%r" % (problems,))

check("참조 표시 형식", app._ref_label("A", "A") == "A")
check("이름이 다르면 함께 표시", u"—" in app._ref_label("A", u"가나다"))


section("트리 -> 그래프 변환 (편집기 경로)")

tree = model.Macro(model.Macro.blank(u"변환 대상"))
tree.append(None, None, dict(schema.new_step("log"), message="a"))
rep = tree.append(None, None, schema.new_step("repeat"))
tree.append(rep, "steps", dict(schema.new_step("log"), message="b"))
app.macro = tree
app.apply_mode()
check("트리 매크로는 트리 모드", app.mode == "tree", app.mode)
before = app.macro.count()

import tkinter.messagebox as mb
_orig_ask, _orig_info = mb.askyesno, mb.showinfo
mb.askyesno = lambda *a, **k: True
mb.showinfo = lambda *a, **k: None
try:
    app.convert_to_graph()
finally:
    mb.askyesno, mb.showinfo = _orig_ask, _orig_info

check("변환 후 그래프 모드", app.mode == "graph", app.mode)
check("노드 수가 단계 수와 같음", app.macro.count() == before,
      u"%d -> %d" % (before, app.macro.count()))
errors, _w = app.canvas_view.graph.validate()
check("변환 결과에 정의 오류 없음", not errors, u"%r" % (errors,))


section("다크 테마")

from tkinter import ttk as _ttk
_style = _ttk.Style(root)
check("clam 테마 사용", _style.theme_use() == "clam", _style.theme_use())
check("기본 배경이 어둡게 지정됨",
      _style.lookup("TFrame", "background") == theme.BG,
      _style.lookup("TFrame", "background"))
check("Treeview 배경 지정",
      _style.lookup("Treeview", "background") == theme.BG_LIGHT)
check("리스트박스에 다크 색 적용",
      app.library_list.cget("background") == theme.BG_LIGHT,
      app.library_list.cget("background"))
check("로그 창에 다크 색 적용",
      app.log.cget("background") == theme.BG_DARKEST)
check("노드 캔버스 배경",
      app.canvas_view.canvas.cget("background") == node_canvas.BG)


section("핀 타입 표시")

check("출력 핀 타입 조회", graph_model.pin_type("if", "true") == "exec")
check("입력 핀 타입 조회", graph_model.input_pin_type("log") == "exec")
check("타입 표시 이름", graph_model.pin_type_label("exec") == u"Exec")
check("타입 색 정의됨", graph_model.pin_type_color("exec").startswith("#"))


section("이미지 썸네일")

import imagecache
sample = os.path.join(PROJECT_ROOT, "Macros", "Example", "never_matches.png")
if os.path.isfile(sample):
    thumb = imagecache.thumbnail(sample, 120, 64)
    check("PNG 썸네일 생성 (외부 라이브러리 없이)", thumb is not None)
    if thumb is not None:
        check("썸네일이 지정 크기 안에 들어감",
              thumb.width() <= 120 and thumb.height() <= 64,
              u"%dx%d" % (thumb.width(), thumb.height()))
    check("같은 요청은 캐시에서 재사용",
          imagecache.thumbnail(sample, 120, 64) is thumb)
    check("원본 크기 조회", imagecache.size_of(sample) == (120, 60),
          u"%r" % (imagecache.size_of(sample),))
else:
    check("샘플 이미지 존재", False, sample)

check("없는 파일은 None", imagecache.thumbnail("nope.png") is None)

# 확대/축소 대응: 정수 배율 조합으로 임의 배율을 근사한다
if os.path.isfile(sample):
    _small = imagecache.scaled(sample, 40, 24)
    _large = imagecache.scaled(sample, 300, 160)
    check("축소 요청", _small is not None and
          _small.width() <= 40 and _small.height() <= 24,
          u"%dx%d" % (_small.width(), _small.height()) if _small else u"None")
    check("확대 요청 (zoom 사용)", _large is not None and _large.width() > 120,
          u"%dx%d" % (_large.width(), _large.height()) if _large else u"None")
    check("확대해도 요청 범위를 넘지 않음",
          _large.width() <= 300 and _large.height() <= 160)
    check("서로 다른 크기는 다른 이미지", _small is not _large)
    check("같은 요청은 캐시 재사용",
          imagecache.scaled(sample, 300, 160) is _large)
    _box = imagecache.fitted_box(sample, 120, 64)
    check("월드 좌표 상자 계산", _box == (120, 60), u"%r" % (_box,))
    check("원본 크기 캐시", imagecache.size_of(sample) == (120, 60))

    # 아주 작게 요청해도 크기 제한을 넘으면 안 된다 (후보 범위 밖 경계)
    _tiny = imagecache.scaled(sample, 6, 4)
    check("아주 작은 요청도 제한을 지킴",
          _tiny is not None and _tiny.width() <= 6 and _tiny.height() <= 4,
          u"%dx%d" % (_tiny.width(), _tiny.height()) if _tiny else u"None")
    check("배율 계산 - 맞는 조합이 없으면 더 줄임",
          imagecache._best_ratio(120, 60, 6, 4) == (1, 20),
          u"%r" % (imagecache._best_ratio(120, 60, 6, 4),))

# 이미지가 붙은 노드는 더 높아져야 한다
app.macro = model.Macro(graph_model.blank(u"썸네일"))
app.apply_mode()
app.macro.path = os.path.join(PROJECT_ROOT, "Macros", "Example", "macro.json")
app.canvas_view.base_dir = os.path.join(PROJECT_ROOT, "Macros", "Example")
plain = app.canvas_view.add_node("waitImage", 0, 0)
h_plain = app.canvas_view.node_height(plain)
plain["image"] = "never_matches.png"
h_image = app.canvas_view.node_height(plain)
check("이미지가 있으면 노드가 더 높아짐", h_image > h_plain,
      u"%d -> %d" % (h_plain, h_image))
check("노드 이미지 경로 해석",
      app.canvas_view.node_image_path(plain) is not None)

# 노드 높이는 월드 좌표다 - 확대율에 따라 흔들리면 안 된다
app.canvas_view.zoom = 1.0
_h1 = app.canvas_view.node_height(plain)
app.canvas_view.zoom = 2.4
_h2 = app.canvas_view.node_height(plain)
app.canvas_view.zoom = 0.4
_h3 = app.canvas_view.node_height(plain)
check("노드 높이는 확대율과 무관", _h1 == _h2 == _h3,
      u"%d / %d / %d" % (_h1, _h2, _h3))

# 썸네일 자체는 확대율을 따라가야 한다
app.canvas_view.zoom = 0.5
_t_small = app.canvas_view.node_thumb(plain)
app.canvas_view.zoom = 2.4
_t_big = app.canvas_view.node_thumb(plain)
check("확대하면 썸네일도 커짐",
      _t_small is not None and _t_big is not None and
      _t_big.width() > _t_small.width(),
      u"%d -> %d" % (_t_small.width() if _t_small else -1,
                     _t_big.width() if _t_big else -1))

app.canvas_view.zoom = 1.0
app.canvas_view.redraw()
root.update_idletasks()
check("썸네일 참조를 붙들고 있음", len(app.canvas_view._thumb_refs) >= 1,
      u"%d개" % len(app.canvas_view._thumb_refs))

# 확대율을 바꿔가며 그려도 죽지 않아야 한다
_crashed = None
for _z in (0.35, 0.7, 1.0, 1.6, 2.5):
    try:
        app.canvas_view.zoom = _z
        app.canvas_view.redraw()
        root.update_idletasks()
    except Exception as exc:
        _crashed = (_z, exc)
        break
app.canvas_view.zoom = 1.0
check("모든 확대율에서 그리기 성공", _crashed is None, u"%r" % (_crashed,))


section("이미지 선택 (기존 파일 사용)")

import imagepicker

_img_tmp = tempfile.mkdtemp(prefix="imgpick_")
_macros2 = os.path.join(_img_tmp, "Macros")
_mine = os.path.join(_macros2, "Mine")
_theirs = os.path.join(_macros2, "Theirs")
os.makedirs(_mine)
os.makedirs(_theirs)
_src = os.path.join(PROJECT_ROOT, "Macros", "Example", "never_matches.png")
shutil.copyfile(_src, os.path.join(_mine, "own_a.png"))
shutil.copyfile(_src, os.path.join(_mine, "own_b.png"))
shutil.copyfile(_src, os.path.join(_theirs, "shared.png"))
_outside = os.path.join(_img_tmp, "outside.png")
shutil.copyfile(_src, _outside)
with open(os.path.join(_mine, "notes.txt"), "wb") as f:
    f.write(b"not an image")

_entries = imagepicker.scan_images(_mine, _macros2)
_here = [(k, n) for k, n, _p in _entries if k == "here"]
_other = [(k, n) for k, n, _p in _entries if k == "other"]
check("내 폴더 이미지 목록", sorted(n for _k, n in _here) == ["own_a.png", "own_b.png"],
      u"%r" % (_here,))
check("이미지가 아닌 파일은 제외", "notes.txt" not in [n for _k, n in _here])
check("다른 매크로 이미지도 훑음",
      any(n.endswith("shared.png") for _k, n in _other), u"%r" % (_other,))
check("내 폴더가 먼저 나옴", _entries[0][0] == "here")
check("이미지 판정", imagepicker._is_image("a.PNG") and
      not imagepicker._is_image("a.txt"))

# 바깥 파일은 복사되어야 한다 (절대 경로로 참조하면 매크로가 깨진다)
_copied = imagepicker.copy_into_folder(root, _mine, _outside)
check("바깥 파일을 매크로 폴더로 복사", _copied == "outside.png", u"%r" % (_copied,))
check("복사본이 실제로 생김", os.path.isfile(os.path.join(_mine, "outside.png")))

# 이미 그 폴더에 있는 파일을 다시 복사하려 하면 이름만 돌려준다 (대화상자 없음)
_same = imagepicker.copy_into_folder(root, _mine, os.path.join(_mine, "own_a.png"))
check("같은 폴더 파일은 그대로 이름 반환", _same == "own_a.png", u"%r" % (_same,))

check("저장 안 된 매크로는 복사 거부",
      imagepicker.copy_into_folder(root, None, _outside) is None)

# 선택 창이 실제로 만들어지는지
try:
    _dialog = imagepicker.ImagePickerDialog(root, _mine, _macros2, current="own_b.png")
    root.update_idletasks()
    _rows = [v for v in _dialog._rows.values() if v]
    _ok = len(_rows) >= 3
    _sel = _dialog._selected()
    _dialog.destroy()
    check("선택 창 생성 + 목록 채움", _ok, u"항목 %d개" % len(_rows))
    check("현재 값이 선택된 상태로 열림",
          _sel is not None and _sel[1] == "own_b.png", u"%r" % (_sel,))
except Exception as exc:
    check("선택 창 생성", False, u"%s: %s" % (type(exc).__name__, exc))

shutil.rmtree(_img_tmp, ignore_errors=True)


section("프로젝트 패널")

check("패널 생성됨", app.project is not None)
app.project.refresh()
root.update_idletasks()
items = list(app.project.paths.values())
check("Macros 폴더 내용을 훑음", len(items) > 0, u"%d개 항목" % len(items))
check("macro.json 을 찾음",
      any(os.path.basename(p).lower() == "macro.json" for p in items))
check("이미지 파일을 찾음",
      any(p.lower().endswith(".png") for p in items))
if os.path.isfile(sample):
    check("경로로 선택 가능", app.project.select_path(sample) is True)
    app.project._on_select()
    root.update_idletasks()
    check("이미지 선택 시 정보 표시",
          "120 x 60" in app.project.info.cget("text"),
          app.project.info.cget("text"))


section("이미지 참조 추적")

if os.path.isfile(sample):
    users = app.find_image_users(sample)
    check("이 이미지를 쓰는 단계를 찾음", len(users) > 0, u"%d곳" % len(users))
check("없는 이미지는 사용처 없음",
      app.find_image_users(os.path.join(PROJECT_ROOT, "Macros", "nope.png")) == [])

callers = app.find_macro_callers("Common/ClosePopup")
check("호출하는 매크로를 찾음 (CallDemo)",
      any(ref == "CallDemo" for ref, _n, _p in callers), u"%r" % (callers,))
check("아무도 안 부르는 매크로", app.find_macro_callers("Example") == [])


section("라이브러리 끌어다 놓기")

app.macro = model.Macro(graph_model.blank(u"드롭 테스트"))
app.apply_mode()
before = len(app.canvas_view.graph.nodes)
app.canvas_view.canvas.update_idletasks()
rx = app.canvas_view.canvas.winfo_rootx() + 150
ry = app.canvas_view.canvas.winfo_rooty() + 90
node = app.canvas_view.drop_call_node("Example", rx, ry)
check("드롭으로 호출 노드 생성", node is not None and
      len(app.canvas_view.graph.nodes) == before + 1)
if node:
    check("드롭한 노드가 call 타입", node.get("type") == "call")
    check("호출 대상이 설정됨", node.get("macro") == "Example")
    check("라벨이 채워짐", node.get("label") == "Example")
    check("드롭 위치에 놓임", "ui" in node and isinstance(node["ui"].get("x"), int),
          u"%r" % (node.get("ui"),))

check("자기 자신 참조 판정", app._is_self_reference("Example") is False)


section("라이브러리 인식 규칙")

_lib_tmp = tempfile.mkdtemp(prefix="libscan_")
_macros = os.path.join(_lib_tmp, "Macros")
os.makedirs(os.path.join(_macros, "Folded"))
with open(os.path.join(_macros, "Folded", "macro.json"), "wb") as f:
    f.write(json.dumps({"name": u"폴더형", "nodes": [], "links": []},
                       ensure_ascii=False).encode("utf-8"))
with open(os.path.join(_macros, "Loose.json"), "wb") as f:
    f.write(json.dumps({"name": u"파일형", "nodes": [], "links": []},
                       ensure_ascii=False).encode("utf-8"))
with open(os.path.join(_macros, "NotAMacro.json"), "wb") as f:
    f.write(json.dumps({"hello": "world"}).encode("utf-8"))
with open(os.path.join(_macros, "broken.json"), "wb") as f:
    f.write(b"{ this is not json")
os.makedirs(os.path.join(_macros, "Empty"))

_found = graph_model.list_macros(_macros)
_refs = sorted(r for r, _n, _p in _found)
check("폴더형 인식", "Folded" in _refs, u"%r" % (_refs,))
check("파일 하나짜리도 인식", "Loose.json" in _refs, u"%r" % (_refs,))
check("매크로가 아닌 json 은 제외", "NotAMacro.json" not in _refs)
check("깨진 json 은 제외", "broken.json" not in _refs)
check("macro.json 없는 빈 폴더는 제외", "Empty" not in _refs)
check("이름을 파일에서 읽어옴",
      dict((r, n) for r, n, _p in _found).get("Loose.json") == u"파일형")

check("파일형 판정", graph_model.is_standalone_ref("Loose.json") is True)
check("폴더형 판정", graph_model.is_standalone_ref("Folded") is False)
check("매크로 파일 읽기 - 정상",
      graph_model.read_macro_file(os.path.join(_macros, "Loose.json")) is not None)
check("매크로 파일 읽기 - 형식 아님",
      graph_model.read_macro_file(os.path.join(_macros, "NotAMacro.json")) is None)
check("파일형 참조가 경로로 풀림",
      graph_model.resolve_macro_ref("Loose.json", _macros) is not None)
shutil.rmtree(_lib_tmp, ignore_errors=True)

check("폴더형 경로 해석", os.path.isfile(app._macro_path("Example")))

# 실제 프로젝트의 매크로가 전부 경로로 풀리는지 (사용자 데이터에 의존하지 않는 검사)
_real = graph_model.list_macros(MACROS_REAL)
_unresolved = [r for r, _n, _p in _real if not os.path.isfile(app._macro_path(r))]
check("목록의 모든 매크로가 경로로 풀림", not _unresolved, u"%r" % (_unresolved,))

# 루트에 놓인 것만 경고 대상이다. 자기 폴더 안이면 이름이 macro.json 이 아니어도 정상.
_loose_tmp = tempfile.mkdtemp(prefix="loose_")
_lm = os.path.join(_loose_tmp, "Macros")
os.makedirs(os.path.join(_lm, "Sub"))
for _p in (os.path.join(_lm, "Root.json"), os.path.join(_lm, "Sub", "Inner.json")):
    with open(_p, "wb") as f:
        f.write(json.dumps({"name": "x", "nodes": [], "links": []}).encode("utf-8"))
_saved_dir = macro_editor.MACROS_DIR
macro_editor.MACROS_DIR = _lm
try:
    check("루트에 놓인 파일은 경고 대상", app._is_loose_in_root("Root.json") is True)
    check("하위 폴더 안의 파일은 경고 아님",
          app._is_loose_in_root("Sub/Inner.json") is False)
    check("폴더형은 경고 아님", app._is_loose_in_root("Sub") is False)
finally:
    macro_editor.MACROS_DIR = _saved_dir
    shutil.rmtree(_loose_tmp, ignore_errors=True)


section("시작 노드 오지정 감지")

_g = graph_model.Graph(graph_model.blank(u"시작 잘못"))
_a = _g.add_node({"type": "log", "message": "a"}, 0, 0)      # 첫 노드라 entry 가 됨
_b = _g.add_node({"type": "log", "message": "b"}, 200, 0)
_c = _g.add_node({"type": "log", "message": "c"}, 400, 0)
_g.connect(_c["id"], "next", _b["id"])
_g.connect(_b["id"], "next", _a["id"])                        # 흐름은 c -> b -> a
_errors, _warnings = _g.validate()
check("시작 노드가 연결을 받으면 경고",
      any(u"실제 시작은" in w for w in _warnings), u"%r" % (_warnings,))
check("올바른 시작 후보를 짚어줌",
      any(_c["id"] in w for w in _warnings if u"실제 시작은" in w))

_g.entry = _c["id"]
_errors, _warnings = _g.validate()
check("시작 노드를 고치면 경고 사라짐",
      not any(u"실제 시작은" in w for w in _warnings), u"%r" % (_warnings,))
check("정상 그래프에 오류 없음", _errors == [], u"%r" % (_errors,))


section("특수키 선택")

import keypicker

check("키 목록이 60개", len(keypicker.ALL_KEYS) == 60,
      u"%d개" % len(keypicker.ALL_KEYS))
check("목록에 중복 없음", len(set(keypicker.ALL_KEYS)) == len(keypicker.ALL_KEYS))
check("내부값이 섞이지 않음",
      not ({"cMax", "cMin", "keyboardUS"} & set(keypicker.ALL_KEYS)))

# OculiX 에서 실제로 뽑은 60개와 정확히 일치해야 한다
_verified = set("""ADD ALT ALTGR BACKSPACE CAPS_LOCK CMD CONTEXT CTRL DECIMAL
DELETE DIVIDE DOWN END ENTER ESC F1 F10 F11 F12 F13 F14 F15 F2 F3 F4 F5 F6 F7
F8 F9 HOME INSERT LEFT META MINUS MULTIPLY NEXT NUM0 NUM1 NUM2 NUM3 NUM4 NUM5
NUM6 NUM7 NUM8 NUM9 NUM_LOCK PAGE_DOWN PAGE_UP PAUSE PRINTSCREEN RIGHT
SCROLL_LOCK SEPARATOR SHIFT SPACE TAB UP WIN""".split())
check("OculiX 실측 상수와 일치", set(keypicker.ALL_KEYS) == _verified,
      u"차이: %r" % (set(keypicker.ALL_KEYS) ^ _verified,))

check("keysym 매핑: Return -> ENTER",
      keypicker.keysym_to_key("Return", "\r") == "ENTER")
check("keysym 매핑: Prior -> PAGE_UP",
      keypicker.keysym_to_key("Prior", "") == "PAGE_UP")
check("keysym 매핑: KP_3 -> NUM3",
      keypicker.keysym_to_key("KP_3", "3") == "NUM3")
check("keysym 매핑: F7 -> F7", keypicker.keysym_to_key("F7", "") == "F7")
check("일반 문자는 소문자 그대로",
      keypicker.keysym_to_key("S", "S") == "s")
check("모르는 keysym 은 None",
      keypicker.keysym_to_key("Hangul_Jeonja", "") is None)

check("조합 표시", keypicker.describe("ENTER", ["CTRL", "SHIFT"]) == u"Ctrl + Shift + Enter",
      keypicker.describe("ENTER", ["CTRL", "SHIFT"]))
check("키만 있을 때", keypicker.describe("F5", []) == u"F5")
check("비었을 때", keypicker.describe("", []) == u"(지정 안 됨)")
check("수정키는 Win 하나만 노출 (CMD/META 동일값)",
      [m for m, _l in keypicker.MODIFIERS] == ["CTRL", "SHIFT", "ALT", "META"])

# key 노드 폼이 새 필드 타입으로 잘 만들어지는지
app.macro = model.Macro(graph_model.blank(u"키 노드"))
app.apply_mode()
knode = app.canvas_view.add_node("key", 0, 0)
knode["key"] = "ENTER"
knode["modifiers"] = ["CTRL"]
app.on_node_selected(knode["id"])
root.update_idletasks()
check("key 노드 속성 폼 생성", len(app.prop_frame.winfo_children()) > 0)
check("key 필드 타입이 keycombo",
      [f["type"] for f in schema.fields_for("key")] == ["keycombo"],
      u"%r" % ([f["type"] for f in schema.fields_for("key")],))
check("요약에 조합이 보임",
      u"CTRL + ENTER" in schema.summarize(knode), schema.summarize(knode))

# 선택 창 자체가 만들어지는지 (열었다가 바로 닫는다)
try:
    dialog = keypicker.KeyPickerDialog(root, "F5", ["ALT"])
    root.update_idletasks()
    ok_dialog = dialog.key == "F5" and dialog.modifiers == ["ALT"]
    groups = dialog.group_list.size()
    dialog.destroy()
    check("선택 창 생성 + 초기값 반영", ok_dialog, u"그룹 %d개" % groups)
except Exception as exc:
    check("선택 창 생성", False, u"%s: %s" % (type(exc).__name__, exc))


section("패널 도킹")

import docking

check("도킹 매니저 생성", app.dock is not None)
check("패널 6개 등록", sorted(app.dock.panels.keys()) ==
      ["graph", "library", "log", "project", "properties", "submacros"],
      u"%r" % (sorted(app.dock.panels.keys()),))
check("기본 배치 - 그래프는 가운데", app.dock.area_of("graph") == "center",
      app.dock.area_of("graph"))
check("기본 배치 - 로그는 아래", app.dock.area_of("log") == "bottom")
check("기본 배치 - 속성은 오른쪽", app.dock.area_of("properties") == "right")
check("기본 배치 - 하위 매크로는 왼쪽", app.dock.area_of("submacros") == "left",
      app.dock.area_of("submacros"))

app.log_line(u"도킹 전 남긴 줄", "info")
_before_lines = len(app._log_buffer)

app.dock.move_panel("log", "left")
root.update_idletasks()
check("패널 이동", app.dock.area_of("log") == "left", app.dock.area_of("log"))
check("이동 후 로그 위젯이 새로 만들어짐", app.log is not None)
check("이동 후에도 로그 내용 유지",
      u"도킹 전 남긴 줄" in app.log.get("1.0", "end"))
check("로그 버퍼 보존", len(app._log_buffer) >= _before_lines)

check("이동 후 캔버스 재생성", app.canvas_view is not None)
check("이동 후 속성 패널 재생성", app.prop_frame is not None)
check("이동 후 프로젝트 패널 재생성", app.project is not None)

_layout = app.dock.get_layout()
check("레이아웃 직렬화", "areas" in _layout and "sashes" in _layout,
      u"%r" % (sorted(_layout.keys()),))
check("직렬화에 이동 결과 반영", "log" in _layout["areas"]["left"])

app.dock.move_panel("log", "bottom")
root.update_idletasks()
check("되돌리기", app.dock.area_of("log") == "bottom")

app.dock.set_layout(_layout)
root.update_idletasks()
check("저장본 적용", app.dock.area_of("log") == "left")

app.dock.reset()
root.update_idletasks()
check("기본값으로 초기화", app.dock.area_of("log") == "bottom")

# 모르는 패널 이름이 섞여 있어도 무시하고 나머지를 배치해야 한다
app.dock.set_layout({"areas": {"left": ["없는패널", "library"], "center": ["graph"],
                               "right": [], "bottom": []}})
root.update_idletasks()
check("모르는 패널 이름 무시", app.dock.area_of("library") == "left")
check("빠진 패널은 기본 위치로", app.dock.area_of("properties") == "right",
      app.dock.area_of("properties"))
app.dock.reset()
root.update_idletasks()

check("영역 판정 - 창 밖은 None",
      app.dock._area_at(-9999, -9999) is None)

# 창이 안 그려진 상태(테스트는 withdraw 상태다)에서는 분할선을 저장하지 않아야
# 한다. 0 을 저장하면 다음 실행 때 패널이 전부 접힌 채로 뜬다.
check("창이 안 그려졌으면 분할선을 저장하지 않음",
      all(any(v > 1 for v in vals)
          for vals in (app.dock.get_layout()["sashes"] or {}).values()),
      u"%r" % (app.dock.get_layout()["sashes"],))
# 창이 아직 안 그려졌으면 적용을 미뤄야 한다.
# 이걸 안 하면 sashpos 가 0 으로 잘려 패널이 전부 접힌다 - 실제로 났던 버그다.
_scheduled = []
_orig_after = app.dock.master.after
_orig_ready = app.dock._panes_ready
app.dock._panes_ready = lambda: False
app.dock.master.after = lambda ms, fn=None, *a: _scheduled.append(ms)
try:
    app.dock._apply_sashes({"outer": [400]})
finally:
    app.dock.master.after = _orig_after
    app.dock._panes_ready = _orig_ready
check("준비 전에는 적용을 미룸", len(_scheduled) == 1, u"%r" % (_scheduled,))

# 준비된 뒤에는 실제로 값이 들어가야 한다
app.dock._apply_sashes({"outer": [180]})
root.update_idletasks()
_now = (app.dock.get_layout()["sashes"] or {}).get("outer") or []
check("준비되면 분할선이 실제로 적용됨", _now and abs(_now[0] - 180) <= 40,
      u"%r" % (_now,))
check("빈 분할선 정보는 그냥 통과",
      app.dock._apply_sashes(None) is None)


section("설정 저장")

check("테스트가 실제 설정 파일을 건드리지 않음",
      editor_settings.PATH != _real_settings_path)

_cfg_tmp = tempfile.mkdtemp(prefix="cfg_")
_saved_path = editor_settings.PATH
editor_settings.PATH = os.path.join(_cfg_tmp, "layout.json")
try:
    check("기본값 로드", editor_settings.load()["geometry"] is not None)
    _sample = {"geometry": "800x600", "layout": {"areas": {"left": ["library"]}},
               "expanded": [u"Common"], "last_macro": None}
    check("저장 성공", editor_settings.save(_sample) is True)
    _loaded = editor_settings.load()
    check("저장 -> 로드 왕복", _loaded["geometry"] == "800x600" and
          _loaded["expanded"] == [u"Common"], u"%r" % (_loaded,))
    with open(editor_settings.PATH, "wb") as f:
        f.write(b"{ broken")
    check("깨진 설정 파일은 기본값으로", editor_settings.load()["geometry"] is not None)

    # 메모장이나 PowerShell Out-File 로 손대면 BOM 이 붙는다.
    # 그걸 못 읽으면 레이아웃이 말없이 초기화된다.
    with open(editor_settings.PATH, "wb") as f:
        f.write(b"\xef\xbb\xbf" + json.dumps(
            {"geometry": "777x555"}, ensure_ascii=False).encode("utf-8"))
    check("BOM 이 붙은 설정도 읽음",
          editor_settings.load()["geometry"] == "777x555",
          editor_settings.load()["geometry"])
finally:
    editor_settings.PATH = _saved_path
    shutil.rmtree(_cfg_tmp, ignore_errors=True)

# 앱의 저장 경로가 실제 파일을 건드리지 않는지만 확인 (쓰지는 않는다)
check("설정 경로가 편집기 폴더", editor_settings.PATH.endswith("layout.json"))


section("프로젝트 트리 펼침 상태")

app.project.refresh()
root.update_idletasks()
_all_dirs = [os.path.relpath(p, MACROS_REAL).replace("\\", "/")
             for p in app.project.paths.values() if os.path.isdir(p)]
check("폴더가 존재", len(_all_dirs) > 0, u"%d개" % len(_all_dirs))

app.project.set_expanded([])
app.project.refresh()
root.update_idletasks()
check("전부 접기", app.project.get_expanded() == [], u"%r" % (app.project.get_expanded(),))

if _all_dirs:
    _target = sorted(_all_dirs)[0]
    app.project.set_expanded([_target])
    app.project.refresh()
    root.update_idletasks()
    check("지정한 폴더만 펼침", app.project.get_expanded() == [_target],
          u"%r" % (app.project.get_expanded(),))
    app.project.refresh()
    root.update_idletasks()
    check("새로고침해도 펼침 유지", app.project.get_expanded() == [_target])


section("툴바 / 라이브러리 동작 변경")

_toolbar_texts = []
for child in app.root.winfo_children():
    for widget in child.winfo_children() if hasattr(child, "winfo_children") else []:
        try:
            _toolbar_texts.append(widget.cget("text"))
        except Exception:
            pass
check("삭제 버튼 제거", u"삭제" not in _toolbar_texts, u"%r" % (_toolbar_texts,))
check("위로 버튼 제거", u"위로" not in _toolbar_texts)
check("아래로 버튼 제거", u"아래로" not in _toolbar_texts)
check("실행 버튼은 남음", any(u"실행" in t for t in _toolbar_texts if t))

_bindings = app.library_list.bind("<Double-Button-1>")
check("라이브러리 더블클릭 바인딩 존재", bool(_bindings))
check("트리 우클릭 메뉴 바인딩", bool(app.tree.bind("<Button-3>")))
check("트리 Delete 키 바인딩", bool(app.tree.bind("<Delete>")))


section("화면 선택 중 창 상태 보존")

# withdraw/deiconify 로 창을 숨겼다 되돌리면 최대화가 풀리고 크기가 초기화된다.
# 캡처 기능을 쓸 때마다 창이 튀던 문제라 헬퍼가 상태를 되돌려야 한다.
_calls = []
_ret = app.run_with_window_hidden(lambda: _calls.append("ran") or "결과")
check("숨긴 채로 함수 실행", _calls == ["ran"] and _ret == u"결과",
      u"%r / %r" % (_calls, _ret))
check("원래 숨어 있던 창은 그대로 숨김 유지",
      app.root.state() == "withdrawn", app.root.state())

# 예외가 나도 창 상태를 되돌려야 한다
def _boom():
    raise RuntimeError("boom")
try:
    app.run_with_window_hidden(_boom)
    check("예외를 그대로 올려보냄", False)
except RuntimeError:
    check("예외를 그대로 올려보냄", True)
check("예외 뒤에도 창 상태 유지", app.root.state() == "withdrawn",
      app.root.state())

# 실제 창을 띄워 기하 정보와 최대화 상태가 보존되는지 본다
_probe = tk.Toplevel(root)
_probe.geometry("640x480+120+90")
_probe.update_idletasks()
_saved_root = app.root
app.root = _probe
try:
    _before = _probe.geometry()
    app.run_with_window_hidden(lambda: None)
    _probe.update_idletasks()
    check("일반 창은 크기/위치가 보존됨", _probe.geometry() == _before,
          u"%s -> %s" % (_before, _probe.geometry()))

    _probe.state("zoomed")
    _probe.update_idletasks()
    if _probe.state() == "zoomed":
        app.run_with_window_hidden(lambda: None)
        _probe.update_idletasks()
        check("최대화 상태가 유지됨", _probe.state() == "zoomed", _probe.state())
    else:
        check("최대화 상태가 유지됨", False, u"창을 최대화하지 못함")
finally:
    app.root = _saved_root
    _probe.destroy()

check("모든 피커가 헬퍼를 거침",
      "self.root.withdraw()" not in
      io.open(os.path.join(os.path.dirname(os.path.abspath(macro_editor.__file__)),
                           "macro_editor.py"), encoding="utf-8")
      .read().split("def run_with_window_hidden")[1].split("def _pick_point")[1])


section(u"화면 캡처 - 편집기 창이 찍히면 안 된다")

# 실제로 났던 버그: 영역 선택과 캡처가 따로 놀아서, OculiX 가 찍을 때는
# 편집기 창이 이미 화면에 돌아와 있었다. 게다가 capture_region 이 GUI
# 스레드를 붙잡아 창이 다시 그려지지도 못해, 흰 사각형만 저장됐다.
import pickers as pickers_module
import runner as runner_module

_cap_tmp = tempfile.mkdtemp(prefix="capture_")
app.macro = model.Macro(model.Macro.blank(u"캡처 테스트"))
app.current_path = None
app.refresh_tree()
app.macro.save(os.path.join(_cap_tmp, "CapTest", "macro.json"))

_probe = tk.Toplevel(root)
_probe.geometry("500x400+100+100")
_probe.deiconify()
_probe.update_idletasks()
_saved_root = app.root
app.root = _probe

_seen = {}
_orig_pick = pickers_module.pick_region
_orig_capture = runner_module.capture_region
_orig_ask = macro_editor.simpledialog.askstring


def _fake_pick(_parent):
    _seen["pick_state"] = _probe.state()
    return (10, 20, 30, 40)


def _fake_capture(x, y, w, h, dest_png, on_line=None):
    _seen["capture_state"] = _probe.state()
    _seen["region"] = (x, y, w, h)
    _seen["dest"] = dest_png
    io.open(dest_png, "wb").close()
    return True, dest_png


pickers_module.pick_region = _fake_pick
runner_module.capture_region = _fake_capture
macro_editor.simpledialog.askstring = lambda *a, **k: u"captured.png"

_var = tk.StringVar(value="")
_committed = []
try:
    app._capture_image(None, "image", _var, lambda: _committed.append(1))

    check(u"영역 선택 중에는 편집기가 숨겨진다",
          _seen.get("pick_state") == "withdrawn", u"%r" % (_seen.get("pick_state"),))
    check(u"캡처하는 순간에도 편집기가 숨겨져 있다",
          _seen.get("capture_state") == "withdrawn",
          u"%r" % (_seen.get("capture_state"),))
    check(u"고른 영역이 그대로 전달된다", _seen.get("region") == (10, 20, 30, 40),
          u"%r" % (_seen.get("region"),))
    check(u"매크로 폴더에 저장된다",
          _seen.get("dest") == os.path.join(app.macro.folder, "captured.png"),
          u"%r" % (_seen.get("dest"),))
    check(u"성공하면 값이 반영된다",
          _var.get() == "captured.png" and _committed == [1],
          u"%r / %r" % (_var.get(), _committed))
    check(u"캡처가 끝나면 창이 돌아온다", _probe.state() == "normal",
          _probe.state())

    # 영역 선택을 취소하면 캡처를 시도하지 않아야 한다
    _seen.clear()
    _var.set("")
    del _committed[:]
    pickers_module.pick_region = lambda _p: None
    app._capture_image(None, "image", _var, lambda: _committed.append(1))
    check(u"영역 선택을 취소하면 캡처하지 않는다", "capture_state" not in _seen,
          u"%r" % (sorted(_seen.keys()),))
    check(u"취소했으면 값도 바뀌지 않는다",
          _var.get() == "" and _committed == [], u"%r" % (_var.get(),))
    check(u"취소 뒤에도 창이 돌아온다", _probe.state() == "normal", _probe.state())
finally:
    pickers_module.pick_region = _orig_pick
    runner_module.capture_region = _orig_capture
    macro_editor.simpledialog.askstring = _orig_ask
    app.root = _saved_root
    _probe.destroy()
    shutil.rmtree(_cap_tmp, ignore_errors=True)

# 오버레이를 치운 뒤 화면이 다시 그려질 시간을 실제로 기다리는지
check(u"캡처 전 대기 시간이 설정되어 있다",
      getattr(macro_editor, "CAPTURE_SETTLE_SEC", 0) > 0,
      u"%r" % (getattr(macro_editor, "CAPTURE_SETTLE_SEC", None),))


section("로그 패널")

app.log_line(u"테스트 줄 ✓", "ok")
content = app.log.get("1.0", "end")
check("로그 출력", u"테스트 줄" in content)


section(u"매크로 설정 대화상자")

# 대화상자는 grab_set() 으로 모달이 된다. 테스트에서 열면 그대로 멈추므로
# 위젯만 만들고 바로 닫는다. 목적은 "여는 순간 죽지 않는가" 와
# "입력한 값이 매크로에 들어가는가" 둘이다.
app.macro.data.setdefault("settings", {})["ocrLanguage"] = "kor"
_before = list(app.root.winfo_children())
app.edit_settings()
_dialogs = [w for w in app.root.winfo_children()
            if w not in _before and isinstance(w, tk.Toplevel)]
check(u"설정 대화상자가 열린다", len(_dialogs) == 1, u"%d개" % len(_dialogs))

if _dialogs:
    _dlg = _dialogs[0]
    _dlg.grab_release()

    def _walk(widget):
        yield widget
        for child in widget.winfo_children():
            for item in _walk(child):
                yield item

    _labels = []
    _combos = []
    for w in _walk(_dlg):
        if isinstance(w, ttk_module.Label):
            try:
                _labels.append(w.cget("text"))
            except Exception:
                pass
        if isinstance(w, ttk_module.Combobox) \
                and "eng" in list(w.cget("values")):
            _combos.append(w)
    check(u"인식 언어 칸이 있다", u"글자 인식 언어" in _labels,
          u"%r" % (_labels,))
    check(u"인식 언어는 목록에서 고른다", len(_combos) == 1,
          u"콤보 %d개" % len(_combos))
    if _combos:
        _values = list(_combos[0].cget("values"))
        check(u"설치된 언어가 목록에 있다",
              "kor" in _values and "eng" in _values, u"%r" % (_values,))
        check(u"현재 값이 표시된다", _combos[0].get() == "kor",
              u"%r" % (_combos[0].get(),))
    # 기본 검색 영역 칸이 언어 칸에 밀려 사라지지 않았는지 본다.
    check(u"기본 검색 영역 칸이 남아 있다", u"기본 검색 영역" in _labels)
    _dlg.destroy()
app.macro.data["settings"].pop("ocrLanguage", None)

# 매개변수 선언 편집기도 같은 이유로 열어 본다 - 위젯을 만들다 죽는 경로가
# 가장 흔한 사고다. 여는 것만으로는 부족해서 추가/삭제까지 눌러 본다.
app.macro.data["params"] = [{"name": "count", "type": "int", "default": 3}]
_before = list(app.root.winfo_children())
app.edit_settings()
_dialogs = [w for w in app.root.winfo_children()
            if w not in _before and isinstance(w, tk.Toplevel)]
check(u"매개변수가 선언돼 있어도 설정이 열린다", len(_dialogs) == 1,
      u"%d개" % len(_dialogs))
if _dialogs:
    _dlg = _dialogs[0]
    _dlg.grab_release()
    _ptexts = _all_labels(_dlg)
    # LabelFrame 의 제목은 Label 위젯이 아니라 옵션이라 따로 봐야 한다
    _frames = []
    for w in _walk(_dlg):
        if isinstance(w, ttk_module.LabelFrame):
            try:
                _frames.append(w.cget("text"))
            except Exception:
                pass
    check(u"매개변수 편집기 틀이 있다",
          any(u"매개변수" in t for t in _frames), u"%r" % (_frames,))
    check(u"이름/타입/기본값 칸이 있다",
          u"타입" in _ptexts and u"기본값" in _ptexts, u"%r" % (_ptexts,))

    _buttons = [w for w in _walk(_dlg) if isinstance(w, ttk_module.Button)]

    def _button(text):
        for b in _buttons:
            try:
                if text in b.cget("text"):
                    return b
            except Exception:
                pass
        return None

    _add = _button(u"매개변수 추가")
    check(u"추가 버튼이 있다", _add is not None)
    if _add is not None:
        _add.invoke()
        root.update_idletasks()
        check(u"누르면 선언이 하나 늘어난다",
              len(app.macro.data["params"]) == 2,
              u"%r" % (app.macro.data["params"],))
        check(u"이름이 겹치지 않게 붙는다",
              len(set(graph_model.param_names(app.macro.data))) == 2,
              u"%r" % (graph_model.param_names(app.macro.data),))

        # 새로 그려진 뒤의 삭제 버튼을 다시 찾는다
        _buttons = [w for w in _walk(_dlg) if isinstance(w, ttk_module.Button)]
        _del = _button(u"삭제")
        if _del is not None:
            _del.invoke()
            root.update_idletasks()
            check(u"삭제 버튼이 선언을 지운다",
                  len(app.macro.data["params"]) == 1,
                  u"%r" % (app.macro.data["params"],))
        else:
            check(u"삭제 버튼이 선언을 지운다", False, u"삭제 버튼을 못 찾음")
    _dlg.destroy()
app.macro.data.pop("params", None)

section(u"반복 - 횟수와 조건은 한쪽만")

# 새 반복 노드에는 기본값 times 가 들어 있다. 조건을 골랐는데 times 가 남으면
# 실행기가 times 를 먼저 보고 조건을 한 번도 평가하지 않는다 (times=0 이면
# 본문 없이 곧장 완료로 나갔다). 조건을 고르는 순간 횟수를 치워야 한다.
_rstep = schema.new_step("repeat")
check(u"새 반복은 횟수 방식이 기본", "times" in _rstep, u"%r" % (_rstep,))
app._set_step_value(_rstep, "while",
                    {"type": "imageMissing", "image": "a.png"})
check(u"조건을 넣으면 횟수가 빠진다", "times" not in _rstep, u"%r" % (_rstep,))
check(u"조건을 넣으면 최대 반복이 채워진다", _rstep.get("maxIterations"),
      u"%r" % (_rstep.get("maxIterations"),))

# 반대 방향. 횟수 칸에 값을 넣으면 조건이 빠진다. 다만 값이 그대로면
# (칸을 지나치기만 한 경우) 아무것도 지우지 않아야 한다.
app.macro = model.Macro(graph_model.blank(u"반복 모드"))
app.current_path = None
app.apply_mode()
_node = app.canvas_view.add_node("repeat")
app._set_step_value(_node, "while",
                    {"type": "imageMissing", "image": "a.png"})
root.update_idletasks()
app.on_node_selected(_node["id"])
app.build_properties()
root.update_idletasks()


def _walk_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        for item in _walk_widgets(child):
            yield item


_times_entry = None
_seen_label = None
for _w in _walk_widgets(app.prop_frame):
    if isinstance(_w, ttk_module.Label):
        try:
            _seen_label = _w.cget("text")
        except Exception:
            pass
    elif isinstance(_w, ttk_module.Entry) and _seen_label == u"반복 횟수":
        _times_entry = _w
        break

if _times_entry is None:
    check(u"반복 횟수 칸을 찾음", False, u"못 찾음")
else:
    check(u"반복 횟수 칸을 찾음", True)
    _times_entry.event_generate("<FocusOut>")
    root.update_idletasks()
    check(u"빈 칸을 지나쳐도 조건이 남는다", "while" in _node, u"%r" % (_node,))
    # <Return> 은 event_generate 로 전달되지 않는다 (키 이벤트는 포커스를 탄다).
    # 실제 사용에서도 칸을 벗어나면 같은 commit 이 돈다.
    _times_entry.insert(0, "3")
    _times_entry.event_generate("<FocusOut>")
    root.update_idletasks()
    check(u"횟수를 넣으면 조건이 빠진다",
          _node.get("times") == 3 and "while" not in _node, u"%r" % (_node,))

# 실행기와 검사기도 같은 규칙을 지켜야 한다.
_cg = graph_model.Graph(graph_model.blank(u"충돌"))
_cg.add_node({"type": "repeat", "times": 0,
              "while": {"type": "imageMissing", "image": "a.png"},
              "maxIterations": 10}, 0, 0)
_ce, _cw = _cg.validate()
check(u"검사가 횟수+조건 충돌을 잡는다",
      any(u"하나만 골라야" in e for e in _ce), u"%r" % (_ce,))

section(u"값 목록 반복 (forEach)")

# 값이 채워진 상태로 폼을 그린다. 빈 상태는 '모든 단계 종류'가 이미 본다 -
# 여기서 보는 건 저장된 값을 다시 열었을 때 위젯이 죽지 않는가다.
app.macro = model.Macro(graph_model.blank(u"값 반복 폼"))
app.current_path = None
app.apply_mode()
_fe = app.canvas_view.add_node("repeat")
_fe.pop("times", None)
_fe["forEach"] = {"param": "charNo", "type": "int", "values": [2, 3, 4]}
app.on_node_selected(_fe["id"])
try:
    app.build_properties()
    root.update_idletasks()
    check(u"값 반복 속성 폼이 만들어진다",
          len(app.prop_frame.winfo_children()) > 0)
except Exception as _exc:
    check(u"값 반복 속성 폼이 만들어진다", False,
          u"%s: %s" % (type(_exc).__name__, _exc))

_texts = []
for _w in _walk_widgets(app.prop_frame):
    if isinstance(_w, ttk_module.Label):
        try:
            _texts.append(_w.cget("text"))
        except Exception:
            pass
check(u"폼에 변수 이름 칸이 있다", any(u"변수 이름" in t for t in _texts),
      u"%r" % (_texts[-6:],))
check(u"$이름 사용법을 안내한다",
      any(u"$charNo" in t for t in _texts), u"%r" % (_texts[-6:],))

# 반복 변수는 조건의 매개변수 목록에도 나와야 한다
check(u"조건 목록에 반복 변수가 보인다",
      "charNo" in graph_model.scope_param_names(app.macro.data),
      u"%r" % (graph_model.scope_param_names(app.macro.data),))

# 방식 전환: 값 목록이 있는데 조건을 넣으면 값 목록이 빠진다
_sw = schema.new_step("repeat")
_sw.pop("times", None)
_sw["forEach"] = {"param": "n", "type": "int", "values": [1, 2]}
app._set_step_value(_sw, "while", {"type": "imageMissing", "image": "a.png"})
check(u"조건을 넣으면 값 목록이 빠진다", "forEach" not in _sw, u"%r" % (_sw,))

# 실행기와 검사기가 같은 규칙을 지킨다
_cg2 = graph_model.Graph(graph_model.blank(u"값+횟수 충돌"))
_cg2.add_node({"type": "repeat", "times": 2,
               "forEach": {"param": "n", "type": "int", "values": [1]}}, 0, 0)
_ce2, _cw2 = _cg2.validate()
check(u"검사가 횟수+값목록 충돌을 잡는다",
      any(u"하나만 골라야" in e for e in _ce2), u"%r" % (_ce2,))

# 참조를 되읽으면 $이름 으로 보인다
check(u"참조가 $이름 으로 표시된다",
      app._value_to_text(graph_model.param_ref("charNo")) == "$charNo",
      u"%r" % (app._value_to_text(graph_model.param_ref("charNo")),))


section(u"노드 복사 / 붙여넣기")

# 진짜 클립보드를 쓴다. 사용자의 클립보드를 되돌려 주려고 먼저 챙겨 둔다
# (글자가 아니었다면 되돌릴 방법이 없어서 노드 꾸러미가 남는다).
try:
    _clip_before = root.clipboard_get()
except tk.TclError:
    _clip_before = None

import nodeclip

_clip_tmp = tempfile.mkdtemp(prefix="nodeclip_")
_clip_macros = os.path.join(_clip_tmp, "Macros")


def _blank_macro(folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "macro.json")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(graph_model.blank(name), ensure_ascii=False, indent=2))
    return path


def _open_macro(path):
    app.macro = model.Macro.load(path)
    app.apply_mode()
    return app.canvas_view


_src_dir = os.path.join(_clip_macros, "SrcMacro")
_dst_dir = os.path.join(_clip_macros, "DstMacro")
_clash_dir = os.path.join(_clip_macros, "ClashMacro")
_src_json = _blank_macro(_src_dir, u"원본 매크로")
_dst_json = _blank_macro(_dst_dir, u"대상 매크로")
_clash_json = _blank_macro(_clash_dir, u"이름 겹침")
shutil.copyfile(os.path.join(MACROS_REAL, "Example", "never_matches.png"),
                os.path.join(_src_dir, "t.png"))
# 같은 이름 다른 그림. 붙여넣기가 남의 그림을 덮어쓰면 안 된다.
_other_png = tk.PhotoImage(width=4, height=4)
_other_png.put("#ff0000", to=(0, 0, 4, 4))
_other_png.write(os.path.join(_clash_dir, "t.png"), format="png")
_clash_bytes = io.open(os.path.join(_clash_dir, "t.png"), "rb").read()

_cv = _open_macro(_src_json)
_cv.canvas.configure(width=900, height=700)
_p1 = _cv.add_node("waitImage", 100, 100)
_p1["image"] = "t.png"
_p2 = _cv.add_node("click", 340, 100)
_p3 = _cv.add_node("log", 580, 100)
_cv.graph.connect(_p1["id"], "next", _p2["id"])
_cv.graph.connect(_p2["id"], "next", _p3["id"])

_cv.set_selection([_p1["id"], _p2["id"]])
check(u"고른 노드를 복사한다", _cv.copy_selection() == 2)

_packed = nodeclip.loads(root.clipboard_get())
check(u"클립보드가 노드 꾸러미로 읽힌다", _packed is not None)
check(u"고른 노드만 담긴다", len(_packed["nodes"]) == 2,
      u"%r" % ([n["type"] for n in _packed["nodes"]],))
check(u"선택 밖으로 나가는 연결은 빠진다", len(_packed["links"]) == 1,
      u"%r" % (_packed["links"],))
check(u"원본 폴더를 함께 담는다",
      os.path.normcase(_packed["sourceDir"]) == os.path.normcase(_src_dir),
      u"%s" % (_packed["sourceDir"],))

# --- 같은 매크로 안에 붙여넣기
_entry_before = _cv.graph.entry
_new = _cv.paste_clipboard(at=(600, 400))
check(u"같은 매크로에 붙여넣기", len(_new) == 2, u"%r" % (_new,))
check(u"새 id 를 발급한다",
      not (set(_new) & {_p1["id"], _p2["id"], _p3["id"]}), u"%r" % (_new,))
check(u"노드가 늘어난다", len(_cv.graph.nodes) == 5, u"%d" % len(_cv.graph.nodes))
check(u"꾸러미 안의 연결도 새 id 로 이어진다",
      _cv.graph.target(_new[0], "next") == _new[1],
      u"%r" % (_cv.graph.links,))
check(u"놓은 자리에 붙는다",
      min(int(_cv.graph.node(i)["ui"]["x"]) for i in _new) == 600,
      u"%r" % ([_cv.graph.node(i)["ui"] for i in _new],))
check(u"붙여넣은 노드가 선택된다", _cv.selected_nodes == set(_new))
check(u"시작 노드는 그대로", _cv.graph.entry == _entry_before)
check(u"같은 폴더면 이미지를 건드리지 않는다",
      _cv.graph.node(_new[0])["image"] == "t.png"
      and sorted(os.listdir(_src_dir)) == ["macro.json", "t.png"],
      u"%r" % (sorted(os.listdir(_src_dir)),))

# --- 다른 매크로에 붙여넣기: 이미지가 따라온다
_cv = _open_macro(_dst_json)
_new_b = _cv.paste_clipboard(at=(50, 50))
check(u"다른 매크로에 붙여넣기", len(_new_b) == 2, u"%r" % (_new_b,))
check(u"빈 그래프면 붙여넣은 첫 노드가 시작 노드",
      _cv.graph.entry == _new_b[0], u"%r" % (_cv.graph.entry,))
check(u"이미지가 대상 폴더로 따라온다",
      os.path.isfile(os.path.join(_dst_dir, "t.png")))
check(u"이미지 참조는 그대로",
      _cv.graph.node(_new_b[0])["image"] == "t.png")

# --- 이름이 겹치고 내용이 다르면 덮어쓰지 않는다
_cv = _open_macro(_clash_json)
_new_c = _cv.paste_clipboard(at=(50, 50))
check(u"이름이 겹쳐도 원본 그림은 그대로",
      io.open(os.path.join(_clash_dir, "t.png"), "rb").read() == _clash_bytes)
check(u"겹치면 다른 이름으로 가져온다",
      os.path.isfile(os.path.join(_clash_dir, "t (2).png")),
      u"%r" % (sorted(os.listdir(_clash_dir)),))
check(u"노드 참조도 새 이름으로 바뀐다",
      _cv.graph.node(_new_c[0])["image"] == "t (2).png",
      u"%r" % (_cv.graph.node(_new_c[0])["image"],))

# --- 내용이 같으면 두 번 복사하지 않는다
_cv = _open_macro(_dst_json)
_again = _cv.paste_clipboard(at=(400, 400))
check(u"같은 그림이 이미 있으면 다시 만들지 않는다",
      not os.path.isfile(os.path.join(_dst_dir, "t (2).png"))
      and _cv.graph.node(_again[0])["image"] == "t.png",
      u"%r" % (sorted(os.listdir(_dst_dir)),))

# --- 클립보드에 엉뚱한 것이 들어 있을 때
check(u"아무 글자나 꾸러미로 읽지 않는다", nodeclip.loads(u"그냥 글자") is None)
check(u"다른 JSON 도 거른다",
      nodeclip.loads(json.dumps({"nodes": [{"type": "log"}]})) is None)
root.clipboard_clear()
root.clipboard_append(u"복사해 둔 평범한 글자")
_before_count = len(_cv.graph.nodes)
check(u"엉뚱한 클립보드로는 아무 일도 없다",
      _cv.paste_clipboard() == [] and len(_cv.graph.nodes) == _before_count)

# --- './' 하위 매크로 참조는 가족을 벗어나면 깨진다. 몰래 고치지 않고 알린다.
_fam_dir = os.path.join(_clip_macros, "FamMacro")
_fam_json = _blank_macro(_fam_dir, u"가족 부모")
_blank_macro(os.path.join(_fam_dir, "Sub"), u"하위")
_cv = _open_macro(_fam_json)
_call = _cv.add_node("call", 0, 0)
_call["macro"] = "./Sub"
_cv.set_selection([_call["id"]])
_cv.copy_selection()
check(u"가족 안에서는 './' 참조가 멀쩡하다",
      app.check_call_targets(only={_call["id"]}) == [],
      u"%r" % (app.check_call_targets(only={_call["id"]}),))

_cv = _open_macro(_dst_json)
_broken = _cv.add_node("call", 700, 700)
_broken["macro"] = "없는매크로"
_pasted_call = _cv.paste_clipboard(at=(300, 300))
_scoped = app.check_call_targets(only=set(_pasted_call))
check(u"가족 밖에 붙인 './' 참조를 짚어 준다",
      len(_scoped) == 1 and u"찾을 수 없습니다" in _scoped[0], u"%r" % (_scoped,))
check(u"only 로 준 노드만 본다",
      all(_broken["id"] not in line for line in _scoped)
      and len(app.check_call_targets()) == 2,
      u"%r" % (app.check_call_targets(),))

# --- 조건 안에 든 이미지도 함께 바뀐다
_cond_node = {"type": "if", "image": "a.png",
              "condition": {"type": "all", "conditions": [
                  {"type": "imageFound", "image": "b.png"},
                  {"type": "not", "condition": {"type": "imageFound",
                                                "image": "a.png"}}]}}
schema.rewrite_images(_cond_node, {"a.png": "z.png"})
check(u"조건 안쪽 이미지 이름까지 갈아 끼운다",
      _cond_node["image"] == "z.png"
      and _cond_node["condition"]["conditions"][1]["condition"]["image"] == "z.png"
      and _cond_node["condition"]["conditions"][0]["image"] == "b.png",
      u"%r" % (_cond_node,))

# --- 키가 실제로 이 동작에 걸려 있는가. 메서드만 맞고 바인딩이 빠지면
#     테스트는 통과하는데 편집기에서는 아무 일도 일어나지 않는다.
#     키 이벤트는 event_generate 로 전달되지 않으므로(포커스를 탄다)
#     바인딩 목록과 처리기를 나눠서 본다.
_bound = _cv.canvas.bind()
check(u"Ctrl+C / Ctrl+V 가 캔버스에 걸려 있다",
      any("Control-Key-c" in b for b in _bound)
      and any("Control-Key-v" in b for b in _bound), u"%r" % (_bound,))
check(u"다른 위젯의 Ctrl+C 를 가로채지 않는다 (캔버스 위젯에만 건다)",
      not any("Control-Key-c" in b for b in root.bind()), u"%r" % (root.bind(),))

_cv = _open_macro(_src_json)
_k1 = _cv.add_node("log", 40, 40)
_cv.set_selection([_k1["id"]])
root.clipboard_clear()
root.clipboard_append(u"덮어쓸 평범한 글자")
check(u"Ctrl+C 처리기가 복사를 한다",
      _cv._on_copy() == "break"
      and (nodeclip.loads(root.clipboard_get()) or {}).get("nodes") is not None)
_before_keys = len(_cv.graph.nodes)
check(u"Ctrl+V 처리기가 붙여넣기를 한다",
      _cv._on_paste() == "break"
      and len(_cv.graph.nodes) == _before_keys + 1, u"%d" % len(_cv.graph.nodes))

# --- Ctrl+D 복제. 하나면 그 노드만, 여럿이면 노드 사이 연결까지 함께.
_cv = _open_macro(_src_json)
_d1 = _cv.add_node("log", 40, 40)
_d1["message"] = u"원본"
_cv.set_selection([_d1["id"]])
_made = _cv.duplicate_selection()
check(u"하나 고르면 그 노드만 복제한다",
      len(_made) == 1 and len(_cv.graph.nodes) == 2
      and _cv.graph.node(_made[0])["message"] == u"원본", u"%r" % (_made,))
check(u"복제본이 선택되고 속성 패널이 그쪽을 본다",
      _cv.selected_nodes == set(_made)
      and app.current_step_obj is _cv.graph.node(_made[0]))

_cv = _open_macro(_src_json)
_d1 = _cv.add_node("log", 40, 40)
_d2 = _cv.add_node("click", 300, 40)
_d3 = _cv.add_node("log", 560, 40)
_cv.graph.connect(_d1["id"], "next", _d2["id"])
_cv.graph.connect(_d2["id"], "next", _d3["id"])
_cv.set_selection([_d1["id"], _d2["id"]])
_made = _cv.duplicate_selection()
check(u"여럿 고르면 전부 복제한다",
      len(_made) == 2 and len(_cv.graph.nodes) == 5, u"%r" % (_made,))
check(u"복제본끼리의 연결이 살아 있다",
      _cv.graph.target(_made[0], "next") == _made[1],
      u"%r" % (_cv.graph.links,))
check(u"선택 밖으로 나가던 연결은 따라오지 않는다",
      _cv.graph.target(_made[1], "next") is None)

_cv.set_selection([])
_before = len(_cv.graph.nodes)
check(u"아무것도 안 골랐으면 복제하지 않는다",
      _cv.duplicate_selection() == [] and len(_cv.graph.nodes) == _before)

_bound = _cv.canvas.bind()
check(u"Ctrl+D 가 캔버스에 걸려 있다",
      any("Control-Key-d" in b for b in _bound), u"%r" % (_bound,))
check(u"Ctrl+D 를 루트에 걸지 않는다 (속성칸 타이핑을 방해하지 않게)",
      not any("Control-Key-d" in b for b in root.bind()), u"%r" % (root.bind(),))
_cv.set_selection([_d3["id"]])
_before = len(_cv.graph.nodes)
check(u"Ctrl+D 처리기가 복제를 한다",
      _cv._on_duplicate() == "break"
      and len(_cv.graph.nodes) == _before + 1, u"%d" % len(_cv.graph.nodes))

shutil.rmtree(_clip_tmp, ignore_errors=True)
root.clipboard_clear()
if _clip_before is not None:
    root.clipboard_append(_clip_before)


section(u"이어서 실행 (실패한 노드부터)")

# 엔진 쪽 동작은 graphtest.py 의 31절이 실제 OculiX 로 본다.
# 여기서는 편집기가 그 기록을 제대로 읽고 버튼을 켜는지만 확인한다.
_rs_tmp = tempfile.mkdtemp(prefix="resume_")
_rs_dir = os.path.join(_rs_tmp, "Macros", "Resume")
_rs_json = _blank_macro(_rs_dir, u"이어서")
_other_json = _blank_macro(os.path.join(_rs_tmp, "Macros", "Other"), u"다른 것")

_rs_saved_file = runner_module.RESUME_FILE
_rs_backup = None
if os.path.exists(_rs_saved_file):
    with io.open(_rs_saved_file, encoding="utf-8") as fh:
        _rs_backup = fh.read()

# 부모 반복 > 하위 호출 > 하위 안의 반복 > 실패 노드. 실제 기록과 같은 모양.
_NESTED = [
    {"macro": u"MBM_Daily", "node": "L", "enter": "loop",
     "mode": "forEach", "done": 1},
    {"macro": u"MBM_Daily", "node": "n5", "enter": "call",
     "ref": "./Core_Daily_HomeWork"},
    {"macro": u"Core_Daily_HomeWork", "node": "n7", "enter": "loop",
     "mode": "times", "done": 2},
    {"macro": u"Core_Daily_HomeWork", "node": "n3", "enter": "call",
     "ref": "./NPC_Rona"},
    {"macro": u"NPC_Rona", "node": "n12", "enter": None},
]


def _write_resume(macro_path, failed=True):
    payload = {"macro": macro_path, "macroName": u"이어서",
               "savedAt": "2026-10-06 09:51:52", "reason": u"단계 실패",
               "failedName": u"나침반 대기",
               "failedAt": _NESTED if failed else None}
    os.makedirs(os.path.dirname(_rs_saved_file), exist_ok=True)
    with io.open(_rs_saved_file, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False))


try:
    check(u"체크포인트 속성은 더 이상 없다 (실패한 노드 기준으로 바뀜)",
          not any(f["name"] == "checkpoint" for f in schema.COMMON_FIELDS))

    _cv = _open_macro(_rs_json)
    runner_module.clear_resume()
    app.refresh_resume_button()
    check(u"기록이 없으면 [이어서 실행] 이 꺼져 있다",
          str(app.resume_button.cget("state")) == "disabled",
          app.resume_button.cget("state"))

    _write_resume(_rs_json)
    app.refresh_resume_button()
    check(u"실패 기록이 있으면 켜진다",
          str(app.resume_button.cget("state")) == "normal",
          app.resume_button.cget("state"))
    check(u"버튼에 실패한 노드 이름이 보인다",
          u"나침반 대기" in app.resume_button.cget("text"),
          app.resume_button.cget("text"))

    _where = runner_module.describe_resume(runner_module.read_resume(_rs_json))
    check(u"여러 겹 반복의 회차가 모두 보인다",
          u"MBM_Daily 반복(L) 2회째" in _where
          and u"Core_Daily_HomeWork 반복(n7) 3회째" in _where, _where)
    check(u"호출 사슬과 실패 노드가 순서대로 보인다",
          _where.index(u"./Core_Daily_HomeWork") < _where.index(u"./NPC_Rona")
          < _where.index(u"나침반 대기 (n12)"), _where)

    # 다른 매크로의 기록으로는 켜지지 않는다 - 엉뚱한 노드를 돌게 된다
    _write_resume(_other_json)
    app.refresh_resume_button()
    check(u"다른 매크로의 기록으로는 켜지지 않는다",
          str(app.resume_button.cget("state")) == "disabled",
          app.resume_button.cget("state"))
    check(u"read_resume 가 이 매크로 것만 돌려준다",
          runner_module.read_resume(_rs_json) is None)

    # 위치가 빠진 기록은 쓸 수 없다
    _write_resume(_rs_json, failed=False)
    app.refresh_resume_button()
    check(u"실패 위치가 없는 기록은 쓸 수 없다",
          str(app.resume_button.cget("state")) == "disabled",
          app.resume_button.cget("state"))
    app.resume_macro()
    check(u"그때 Ctrl+F5 를 누르면 상태줄로 알린다",
          u"이어서 실행할 위치가 없습니다" in app.status.get(),
          app.status.get())

    # 매크로를 열면 그 매크로 기준으로 다시 본다
    _write_resume(_rs_json)
    _open_macro(_other_json)
    check(u"다른 매크로를 열면 꺼진다",
          str(app.resume_button.cget("state")) == "disabled",
          app.resume_button.cget("state"))
    _open_macro(_rs_json)
    check(u"돌아오면 다시 켜진다",
          str(app.resume_button.cget("state")) == "normal",
          app.resume_button.cget("state"))

    check(u"Ctrl+F5 가 걸려 있다", bool(app.root.bind("<Control-F5>")))

    # 처음부터 도는 실행은 낡은 기록을 지운다
    _rs_calls = []
    _rs_orig = runner_module.run_macro
    # run_macro 는 검사에 걸리면 modal 대화상자를 띄운다. 테스트에서는
    # 거기서 영원히 멈추므로 검사를 통과한 것으로 둔다.
    _rs_orig_validate = app.validate_macro
    app.validate_macro = lambda: True
    runner_module.run_macro = (
        lambda path, on_line, on_done, start_node=None, resume=False:
        _rs_calls.append(resume) or type(
            "FakeJob", (), {"is_running": lambda self: False,
                            "stop": lambda self: None,
                            "cancelled": False})())
    try:
        app.job = None
        app.run_macro()
        check(u"처음부터 실행하면 resume=False 로 부른다", _rs_calls == [False],
              u"%r" % (_rs_calls,))
        check(u"처음부터 실행하면 낡은 기록을 지운다",
              runner_module.read_resume(_rs_json) is None)

        _write_resume(_rs_json)
        del _rs_calls[:]
        app.job = None
        app.run_macro(resume=True)
        check(u"이어서 실행하면 resume=True 로 부른다", _rs_calls == [True],
              u"%r" % (_rs_calls,))
        check(u"이어서 실행은 시작할 때 기록을 지우지 않는다",
              runner_module.read_resume(_rs_json) is not None)
    finally:
        runner_module.run_macro = _rs_orig
        app.validate_macro = _rs_orig_validate
        app.job = None
finally:
    runner_module.clear_resume()
    if _rs_backup is not None:
        with io.open(_rs_saved_file, "w", encoding="utf-8") as fh:
            fh.write(_rs_backup)
    shutil.rmtree(_rs_tmp, ignore_errors=True)


section(u"멈춤 확인 (settleFor)")

# 스크롤이 끝나기 전에 집으면 마우스가 도착할 때쯤 목록이 밀려서 옆 항목을
# 누른다. 엔진 쪽 동작은 Scripts\Tests\SettleProbe.sikuli 가 본다.
# 여기서는 편집기에서 그 값을 넣고 뺄 수 있는지만 확인한다.
_st_names = [f["name"] for f in schema.fields_for("click")]
check(u"클릭 계열에 '멈춤 확인' 칸이 있다", "settleFor" in _st_names,
      u"%r" % (_st_names,))
for _t in ("click", "doubleClick", "rightClick", "hover"):
    if "settleFor" not in [f["name"] for f in schema.fields_for(_t)]:
        check(u"%s 에도 있다" % _t, False)
        break
else:
    check(u"클릭/더블/우클릭/호버 모두에 있다", True)

_st_tmp = tempfile.mkdtemp(prefix="settle_")
_st_dir = os.path.join(_st_tmp, "Macros", "Settle")
_st_json = _blank_macro(_st_dir, u"멈춤 확인")
_cv = _open_macro(_st_json)
_n_click = _cv.add_node("click", 40, 40)
_n_click["image"] = "btn.png"
app.on_node_selected(_n_click["id"])
_settle_entry = _field_entry(app.prop_frame, u"멈춤 확인(초)")
check(u"속성 패널에 칸이 만들어진다", _settle_entry is not None)
_settle_entry.delete(0, "end")
_settle_entry.insert(0, "0.4")
app.flush_property_edits()
check(u"값이 숫자로 들어간다", _n_click.get("settleFor") == 0.4,
      u"%r" % (_n_click.get("settleFor"),))
_settle_entry.delete(0, "end")
app.flush_property_edits()
check(u"비우면 키가 사라진다 (매크로 기본값을 쓴다)",
      "settleFor" not in _n_click, u"%r" % (_n_click,))

_errs, _warns = _cv.graph.validate()
check(u"멈춤 확인을 넣어도 검사를 통과한다",
      not any(u"settleFor" in e for e in _errs), u"%r" % (_errs,))

shutil.rmtree(_st_tmp, ignore_errors=True)


section(u"AND/OR 조건 목록에 조건 추가")

# 실제로 났던 사고: 'AND 조건들' 에 이미지 조건을 넣으면 목록에 'None' 으로
# 들어가고 실행하면 'unknown condition type: None' 으로 죽었다.
# 원인은 _edit_dialog 의 confirm() 이 같은 dict 를 clear 한 뒤 자기 자신으로
# update 한 것. 종류를 바꾸면 새 dict 가 들어와서 멀쩡했던 탓에, 기본값
# (이미지가 있으면) 그대로 확인을 누를 때만 터졌다.
_cl_tmp = tempfile.mkdtemp(prefix="condlist_")
_cl_dir = os.path.join(_cl_tmp, "Macros", "CondList")
_cl_json = _blank_macro(_cl_dir, u"조건 목록")
_cv = _open_macro(_cl_json)
_n_all = _cv.add_node("if", 40, 40)
_n_all["condition"] = {"type": "all", "conditions": []}
app.on_node_selected(_n_all["id"])


def _add_to_list(node, filled, keep_type=True):
    """조건 목록의 [추가] 버튼과 편집 창을 코드로 재현한다.

    창을 실제로 띄우면 wait_window 에서 멈춘다. _edit_dialog 가 하는 일
    (홀더에 담기 -> 사용자가 채우기 -> confirm) 만 그대로 따라 한다.
    """
    new = schema.new_condition("imageExists")
    holder = {"cond": new}
    if not keep_type:
        # 사용자가 종류 콤보를 바꾼 경우. set_cond 가 새 dict 로 갈아 끼운다.
        holder["cond"] = schema.new_condition("textExists")
    holder["cond"].update(filled)
    # ---- confirm() 과 같은 처리
    picked = dict(holder["cond"])
    new.clear()
    new.update(picked)
    node["condition"]["conditions"].append(new)
    return new


_first = _add_to_list(_n_all, {"image": "a.png"})
check(u"기본 종류 그대로 넣어도 type 이 남는다",
      _first.get("type") == "imageExists" and _first.get("image") == "a.png",
      u"%r" % (_first,))
check(u"목록에 'None' 으로 보이지 않는다",
      schema.describe_condition(_first) != u"None",
      schema.describe_condition(_first))

_second = _add_to_list(_n_all, {"image": "b.png", "type": "imageMissing"})
check(u"두 번째 조건도 멀쩡하다",
      _second.get("type") == "imageMissing", u"%r" % (_second,))

_third = _add_to_list(_n_all, {"text": u"확인"}, keep_type=False)
check(u"종류를 바꾼 경우도 그대로 (예전에도 되던 길)",
      _third.get("type") == "textExists", u"%r" % (_third,))

check(u"AND 요약이 세 조건을 모두 보여 준다",
      schema.describe_condition(_n_all["condition"])
      == u"(a.png 있으면 AND b.png 없으면 AND 글자 \"확인\" 보이면)",
      schema.describe_condition(_n_all["condition"]))

# 검사가 종류 없는 조건을 잡아내야 한다. 이 사고가 다시 나더라도
# 실행하기 전에 알 수 있다.
_n_all["condition"]["conditions"].append({"image": "c.png"})
_errs, _warns = _cv.graph.validate()
check(u"종류 없는 조건을 검사가 잡는다",
      any(u"조건의 종류가 잘못됐습니다" in e for e in _errs), u"%r" % (_errs,))
_n_all["condition"]["conditions"].pop()
_errs, _warns = _cv.graph.validate()
check(u"멀쩡한 조건은 잡지 않는다",
      not any(u"조건의 종류" in e for e in _errs), u"%r" % (_errs,))

check(u"엔진과 편집기의 조건 종류가 일치한다",
      set(schema.CONDITION_TYPES.keys()) == set(graph_model.CONDITION_TYPES),
      u"%r" % (sorted(set(schema.CONDITION_TYPES.keys())
                      ^ set(graph_model.CONDITION_TYPES)),))

shutil.rmtree(_cl_tmp, ignore_errors=True)


section(u"속성칸을 Enter 없이 빠져나가도 값이 남는가")

# Enter 를 치지 않고 다른 노드를 클릭하면 Tk 의 <FocusOut> 이 오기 전에
# 속성 패널이 다시 지어져 입력칸이 파괴된다. 그래서 값이 사라졌다.
# 여기서 보는 것은 "패널을 다시 짓기 전에 반영하는가" 다.
_pf_tmp = tempfile.mkdtemp(prefix="propflush_")
_pf_dir = os.path.join(_pf_tmp, "Macros", "PropFlush")
_pf_json = _blank_macro(_pf_dir, u"속성 반영")
_cv = _open_macro(_pf_json)
_n_a = _cv.add_node("wait", 40, 40)        # 초 (숫자 칸)
_n_b = _cv.add_node("type", 320, 40)       # 내용 (여러 줄 글자 칸)

app.on_node_selected(_n_a["id"])
_seconds = _field_entry(app.prop_frame, u"초")
check(u"숫자 칸을 찾았다", _seconds is not None)

_seconds.delete(0, "end")
_seconds.insert(0, "2.5")
check(u"Enter 전에는 아직 반영되지 않는다", _n_a.get("seconds") != 2.5,
      u"%r" % (_n_a,))

# 다른 노드를 고른다 = 편집기에서 노드를 클릭한 것과 같은 경로
app.macro.dirty = False
app.on_node_selected(_n_b["id"])
check(u"노드를 바꾸면 방금 친 값이 들어간다", _n_a.get("seconds") == 2.5,
      u"%r" % (_n_a,))
check(u"바꾼 뒤에는 dirty 로 표시된다", app.macro.dirty)

# 여러 줄 글자 칸도 같아야 한다
_body = _field_text(app.prop_frame, u"내용")
check(u"글자 칸을 찾았다", _body is not None)
_body.delete("1.0", "end")
_body.insert("1.0", u"안 친 채로 나감")
app.on_node_selected(_n_a["id"])
check(u"글자 칸도 노드를 바꾸면 들어간다",
      _n_b.get("text") == u"안 친 채로 나감", u"%r" % (_n_b,))

# 저장/실행 직전에도 반영되어야 한다. dirty 가 아니면 저장을 건너뛰므로
# 옛 파일이 실행된다.
_seconds = _field_entry(app.prop_frame, u"초")
_seconds.delete(0, "end")
_seconds.insert(0, "7")
app.macro.dirty = False
app.flush_property_edits()
check(u"flush 만으로도 값이 들어간다", _n_a.get("seconds") == 7.0, u"%r" % (_n_a,))
check(u"flush 가 dirty 를 세운다", app.macro.dirty)

# 한 번 반영한 값을 두 번 쓰지 않는다 - 반복해서 부를 수 있어야 한다
app.macro.dirty = False
app.flush_property_edits()
check(u"건드리지 않았으면 flush 가 아무 일도 하지 않는다", not app.macro.dirty)

# 건드리지 않은 칸은 다시 쓰지 않는다. 반복 노드의 횟수/조건처럼 서로를
# 지우는 필드가 있어서, 지나치기만 해도 commit 이 돌면 조건이 날아간다.
_n_r = _cv.add_node("repeat", 600, 40)
_n_r["while"] = {"type": "imageExists", "image": "x.png"}
_n_r["maxIterations"] = 5
app.on_node_selected(_n_r["id"])
app.flush_property_edits()
check(u"건드리지 않은 칸은 조건을 지우지 않는다", "while" in _n_r, u"%r" % (_n_r,))

# 조건 편집기 안의 칸도 같은 길을 지난다. 조건 종류를 바꾸면 아래 칸들이
# 통째로 갈리므로, 거기서도 먼저 반영해야 한다.
_n_if = _cv.add_node("if", 900, 40)
_n_if["condition"] = {"type": "textExists", "text": u"옛 글자"}
app.on_node_selected(_n_if["id"])
_text_entry = _field_entry(app.prop_frame, u"찾을 글자")
check(u"조건 안의 칸을 찾았다", _text_entry is not None)
_text_entry.delete(0, "end")
_text_entry.insert(0, u"새 글자")
app.on_node_selected(_n_a["id"])
check(u"조건 안의 칸도 노드를 바꾸면 들어간다",
      _n_if["condition"].get("text") == u"새 글자", u"%r" % (_n_if,))

# 저장 경로에도 걸려 있어야 한다
app.on_node_selected(_n_a["id"])
_field_entry(app.prop_frame, u"초").delete(0, "end")
_field_entry(app.prop_frame, u"초").insert(0, "3")
app.macro.dirty = False
app.save_macro()
_saved = json.loads(io.open(_pf_json, encoding="utf-8-sig").read())
check(u"Ctrl+S 도 안 들어간 값을 먼저 반영한다",
      any(n.get("seconds") == 3.0 for n in _saved.get("nodes", [])),
      u"%r" % (_saved.get("nodes"),))

shutil.rmtree(_pf_tmp, ignore_errors=True)


section(u"실행 종료 알림")

check(u"알림 켜기가 기본값", app.notify_var.get())
_notified = []
_orig_notify = notify.notify
notify.notify = lambda title, message, on_error=None: (
    _notified.append((title, message)) or True)
try:
    app.job = None
    app.macro.data["name"] = u"알림 매크로"
    app._notify_run_done(0, False)
    check(u"정상 종료를 알린다",
          len(_notified) == 1 and u"알림 매크로" in _notified[0][0]
          and _notified[0][1] == u"정상 종료", u"%r" % (_notified,))
    app._notify_run_done(1, False)
    check(u"실패도 알린다", _notified[-1][1] == u"단계 실패로 중단",
          u"%r" % (_notified[-1],))
    app._notify_run_done(2, True)
    check(u"사용자가 중지한 것은 그렇게 알린다",
          _notified[-1][1] == u"중지했습니다", u"%r" % (_notified[-1],))

    del _notified[:]
    app.notify_var.set(False)
    app._notify_run_done(0, False)
    check(u"꺼 두면 알리지 않는다", _notified == [], u"%r" % (_notified,))
finally:
    notify.notify = _orig_notify
    app.notify_var.set(True)

check(u"이 환경에서 알림을 띄울 수 있다", notify.available())
check(u"XML 특수문자를 막는다",
      notify._escape(u"a'b<c&d") == u"a&apos;b&lt;c&amp;d",
      notify._escape(u"a'b<c&d"))
_multiline = u"위" + chr(10) + u"아래"
check(u"줄바꿈을 한 줄로 줄인다",
      notify._escape(_multiline) == u"위 아래", notify._escape(_multiline))


section(u"일시정지 / 재개")

# 엔진이 정말 멈추는지는 graphtest.py 33절이 본다. 여기서는 버튼·상태줄·단축키가
# 맞게 움직이는지만 확인한다.
import ctypes
import time as _time_mod


class _PauseJob(object):
    def __init__(self):
        self.calls = []
        self.running = True
        self.can_pause = True
        self.cancelled = False

    def is_running(self):
        return self.running

    def stop(self):
        self.running = False

    def pause(self):
        self.calls.append("pause")
        return self.can_pause

    def unpause(self):
        self.calls.append("unpause")


_beeps = []
_orig_beep = macro_editor._beep
macro_editor._beep = _beeps.append
_saved_job = app.job
try:
    _state = lambda: str(app.pause_button.cget("state"))
    _label = lambda: app.pause_button.cget("text")

    # 앞 절의 가짜 실행들은 시작만 하고 끝나지 않았다. 여기서 끝낸 상태로 만든다.
    app._stop_pause_controls()
    app.job = None
    app.toggle_pause()
    check(u"실행 중이 아니면 아무 일도 없다", app.paused is False)
    check(u"F6 이 편집기 창 안에서도 걸려 있다 (전역 등록 실패 대비)",
          bool(app.root.bind("<F6>")))

    _job = _PauseJob()
    app.job = _job
    # 실제 F6 을 잡지 않게 시험용 키로 바꿔 둔다
    app.pause_hotkey = hotkey_module.GlobalHotkey(
        0x87, lambda: None, hotkey_id=71)     # VK_F24
    app._start_pause_controls()
    check(u"실행이 시작되면 버튼이 켜진다", _state() == "normal", _state())
    check(u"실행 중에는 전역 단축키가 등록된다", app.pause_hotkey.active,
          u"%r" % (app.pause_hotkey.error,))

    app.toggle_pause()
    check(u"누르면 일시정지를 요청한다",
          _job.calls == ["pause"] and app.paused, u"%r" % (_job.calls,))
    check(u"버튼이 재개로 바뀐다", u"재개" in _label(), _label())
    check(u"요청 단계에서는 '멈췄다' 고 하지 않는다",
          u"요청" in app.status.get(), app.status.get())

    app.log_queue.put((u"[10:00:00]     | %s 멈췄습니다 - 대기 중"
                       % graph_model.PAUSED_MARK, None))
    app._drain_log()
    check(u"엔진이 멈췄다고 알리면 상태줄이 바뀐다",
          u"일시정지됨" in app.status.get(), app.status.get())
    check(u"멈추면 소리로 알린다", len(_beeps) == 1, u"%r" % (_beeps,))

    del _beeps[:]
    app.log_queue.put((u"%s 주의: 마우스 버튼이 눌린 채입니다 (LEFT)"
                       % graph_model.PAUSED_MARK, None))
    app._drain_log()
    check(u"눌린 버튼 경고로는 소리를 두 번 내지 않는다", _beeps == [],
          u"%r" % (_beeps,))

    app.toggle_pause()
    check(u"다시 누르면 재개를 요청한다",
          _job.calls == ["pause", "unpause"] and not app.paused,
          u"%r" % (_job.calls,))
    check(u"버튼이 일시정지로 돌아온다", u"일시정지" in _label(), _label())
    app.log_queue.put((u"%s 3.0초 멈춰 있었습니다. 이어서 진행합니다"
                       % graph_model.RESUMED_MARK, None))
    app._drain_log()
    check(u"재개되면 상태줄이 돌아온다", u"실행 중" in app.status.get(),
          app.status.get())

    # F6 은 다른 스레드에서 온다. 큐를 거쳐 Tk 스레드에서 처리돼야 한다.
    del _job.calls[:]
    app.log_queue.put((("__PAUSE_KEY__", None), None))
    app._drain_log()
    check(u"단축키 신호가 큐를 거쳐 일시정지로 이어진다",
          _job.calls == ["pause"] and app.paused, u"%r" % (_job.calls,))

    # 일시정지한 채로 끝나도 다음 실행에 상태가 남으면 안 된다
    app._stop_pause_controls()
    check(u"실행이 끝나면 버튼이 꺼지고 초기화된다",
          _state() == "disabled" and not app.paused and u"일시정지" in _label(),
          _label())
    check(u"끝나면 단축키를 돌려준다", not app.pause_hotkey.active)

    _job = _PauseJob()
    _job.can_pause = False
    app.job = _job
    app.pause_button.config(state="normal")
    app.toggle_pause()
    check(u"요청에 실패하면 일시정지 상태가 되지 않는다", app.paused is False,
          app.status.get())
    check(u"실패를 알린다", u"못했습니다" in app.status.get(), app.status.get())
    app.pause_button.config(state="disabled")

    # 키 등록이 실패해도 실행을 막지 않고, 대안을 알려 준다
    _fail_hk = hotkey_module.GlobalHotkey(0x87, lambda: None, hotkey_id=72)
    check(u"시험용 키 등록", _fail_hk.start(), u"%r" % (_fail_hk.error,))
    app.pause_hotkey = hotkey_module.GlobalHotkey(0x87, lambda: None,
                                                  hotkey_id=73)
    _hk_before = len(app._log_buffer)
    app.job = _PauseJob()
    app._start_pause_controls()
    _hk_lines = [t for t, _tag in app._log_buffer[_hk_before:]]
    check(u"키를 선점당하면 이유와 대안을 로그로 알린다",
          any(u"F6" in t and u"다른 프로그램" in t and u"툴바" in t
              for t in _hk_lines), u"%r" % (_hk_lines,))
    check(u"그래도 버튼은 쓸 수 있다", _state() == "normal", _state())
    app._stop_pause_controls()
    _fail_hk.stop()

    # 실제 등록 / 메시지 수신 / 해제
    _pressed = []
    _hk = hotkey_module.GlobalHotkey(0x87, lambda: _pressed.append(1),
                                     hotkey_id=74)
    check(u"RegisterHotKey 로 등록된다", _hk.start(), u"%r" % (_hk.error,))
    check(u"두 번 시작해도 괜찮다", _hk.start())
    _other = hotkey_module.GlobalHotkey(0x87, lambda: None, hotkey_id=75)
    check(u"같은 키를 또 등록하면 실패로 돌려준다", _other.start() is False,
          u"%r" % (_other.error,))
    check(u"실패 이유가 사람이 읽을 문장이다",
          u"다른 프로그램" in (_other.error or u""), u"%r" % (_other.error,))
    _other.stop()

    # 실제 키를 누르는 대신 WM_HOTKEY 를 그 스레드로 보낸다
    ctypes.windll.user32.PostThreadMessageW(_hk._thread_id, 0x0312, 74, 0)
    for _i in range(40):
        if _pressed:
            break
        _time_mod.sleep(0.05)
    check(u"WM_HOTKEY 를 받으면 콜백이 불린다", _pressed == [1],
          u"%r" % (_pressed,))
    _hk.stop()
    check(u"해제하면 등록 상태가 풀린다", not _hk.active)
    _again = hotkey_module.GlobalHotkey(0x87, lambda: None, hotkey_id=76)
    check(u"해제한 키는 다시 등록할 수 있다", _again.start(),
          u"%r" % (_again.error,))
    _again.stop()
    _again.stop()
    check(u"해제를 두 번 불러도 괜찮다", not _again.active)
finally:
    macro_editor._beep = _orig_beep
    app.pause_hotkey = hotkey_module.GlobalHotkey(0x87, lambda: None,
                                                  hotkey_id=77)
    app.paused = False
    app.pause_button.config(state="disabled")
    app.job = _saved_job


section(u"검사: 투명 템플릿 + DPI 불일치 경고")

# 판정 자체(PNG 읽기)는 selftest 가 본다. 여기서는 [매크로 검사] 가 그 판정을
# 실제로 불러 경고로 띄우는지 - 연결부만 확인한다.
import pnginfo as _pnginfo_mod
import screenutil
_mk_tmp = tempfile.mkdtemp(prefix="maskwarn_")
_mk_json = _blank_macro(os.path.join(_mk_tmp, "Macros", "Masked"), u"투명")
for _nm in ("house.png", "ok.png"):
    shutil.copyfile(os.path.join(MACROS_REAL, "Example", "never_matches.png"),
                    os.path.join(_mk_tmp, "Macros", "Masked", _nm))
_mk_seen = []
_mk_orig = _pnginfo_mod.mask_dpi_risk


def _mk_fake(path, system_dpi):
    _mk_seen.append(system_dpi)
    return u"가짜 이유" if os.path.basename(path) == "house.png" else None


_pnginfo_mod.mask_dpi_risk = _mk_fake
try:
    _cv = _open_macro(_mk_json)
    _cv.add_node("waitImage", 40, 40)["image"] = "house.png"
    _cv.add_node("waitImage", 300, 40)["image"] = "ok.png"
    _mk_before = len(app._log_buffer)
    app.validate_macro()
    _mk_lines = [t for t, _tag in app._log_buffer[_mk_before:]]
    check(u"[매크로 검사] 가 위험한 템플릿을 경고한다",
          any(u"house.png" in t and u"가짜 이유" in t and t.startswith(u"경고")
              for t in _mk_lines), u"%r" % (_mk_lines,))
    check(u"안전한 템플릿은 경고하지 않는다",
          not any(u"ok.png" in t for t in _mk_lines), u"%r" % (_mk_lines,))
    check(u"경고일 뿐 실행을 막지는 않는다 (검사 통과)",
          any(u"검사 통과" in t for t in _mk_lines), u"%r" % (_mk_lines,))
    check(u"시스템 DPI 를 96 x 화면 배율로 넘긴다",
          _mk_seen and abs(_mk_seen[0] - 96.0 * screenutil.scale()[0]) < 0.01,
          u"%r" % (_mk_seen[:1],))
finally:
    _pnginfo_mod.mask_dpi_risk = _mk_orig
    shutil.rmtree(_mk_tmp, ignore_errors=True)


section(u"하위 매크로 (UE BP의 '함수')")

_fam_tmp = tempfile.mkdtemp(prefix="family_")
_fam_macros = os.path.join(_fam_tmp, "Macros")


def _write_macro(folder, name, nodes=None, links=None, settings=True):
    os.makedirs(folder, exist_ok=True)
    data = graph_model.blank(name)
    if not settings:
        data.pop("settings", None)
    if nodes:
        data["nodes"] = nodes
        data["entry"] = nodes[0]["id"]
    data["links"] = links or []
    with io.open(os.path.join(folder, "macro.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))
    return os.path.join(folder, "macro.json")


_parent_dir = os.path.join(_fam_macros, "Parent")
_sub_a = os.path.join(_parent_dir, "OpenMenu")
_sub_b = os.path.join(_parent_dir, "ClosePopup")
_lib_dir = os.path.join(_fam_macros, "Standalone")
_parent_json = _write_macro(_parent_dir, u"부모")
_write_macro(_sub_a, u"메뉴 열기", settings=False)
_write_macro(_sub_b, u"팝업 닫기", settings=False)
_write_macro(_lib_dir, u"라이브러리 매크로")
# 가족이 공유하는 이미지는 부모 폴더에 둔다
shutil.copyfile(os.path.join(MACROS_REAL, "Example", "never_matches.png"),
                os.path.join(_parent_dir, "shared.png"))

_saved_macros_dir = macro_editor.MACROS_DIR
macro_editor.MACROS_DIR = _fam_macros
try:
    # --- 라이브러리와 하위 매크로가 서로 섞이지 않는다
    _lib_refs = [r for r, _n, _p in graph_model.list_macros(_fam_macros)]
    check(u"라이브러리에 하위 매크로가 안 보인다",
          _lib_refs == ["Parent", "Standalone"], u"%r" % (_lib_refs,))
    _all_refs = sorted(r for r, _n, _p in
                       graph_model.list_macros(_fam_macros, include_subs=True))
    check(u"include_subs 는 하위까지 훑는다",
          _all_refs == ["Parent", "Parent/ClosePopup", "Parent/OpenMenu",
                        "Standalone"], u"%r" % (_all_refs,))

    # --- 부모를 열면 하위 목록이 뜬다
    app.macro = model.Macro.load(_parent_json)
    app.current_path = None
    app.apply_mode()
    root.update_idletasks()
    _sub_refs = [r for r, _n, _p in app._submacro_refs]
    check(u"부모에서 하위 매크로 목록이 보인다",
          _sub_refs == ["./ClosePopup", "./OpenMenu"], u"%r" % (_sub_refs,))
    check(u"하위 목록 위젯이 채워진다", app.submacro_list.size() == 2,
          u"%d줄" % app.submacro_list.size())
    check(u"부모 편집 중에는 [부모 열기] 가 꺼진다",
          str(app.submacro_parent_btn.cget("state")) == "disabled",
          app.submacro_parent_btn.cget("state"))
    check(u"부모의 이미지 폴더는 자기 폴더",
          os.path.normcase(app.resource_dir()) ==
          os.path.normcase(os.path.abspath(_parent_dir)))

    # --- 하위 매크로를 열면 가족이 그대로 보이고 이미지는 부모 것을 쓴다
    app.macro = model.Macro.load(os.path.join(_sub_a, "macro.json"))
    app.current_path = None
    app.apply_mode()
    root.update_idletasks()
    check(u"하위에서도 형제 목록이 보인다",
          [r for r, _n, _p in app._submacro_refs] ==
          ["./ClosePopup", "./OpenMenu"])
    check(u"하위 편집 중에는 [부모 열기] 가 켜진다",
          str(app.submacro_parent_btn.cget("state")) == "normal")
    check(u"하위의 이미지 폴더는 부모 폴더",
          os.path.normcase(app.resource_dir()) ==
          os.path.normcase(os.path.abspath(_parent_dir)),
          app.resource_dir())
    app.macro.data["nodes"] = [{"id": "n1", "type": "waitImage",
                                "image": "shared.png", "timeout": 1}]
    check(u"부모 이미지를 하위가 참조해도 '없는 이미지' 가 아니다",
          app.macro.missing_images() == [], u"%r" % (app.macro.missing_images(),))

    # --- 참조 해석: "./" 는 가족 안에서만, 라이브러리를 가리지 않는다
    check(u"형제 참조가 해석된다",
          graph_model.resolve_macro_ref("./ClosePopup", _sub_a) ==
          os.path.normpath(os.path.join(_sub_b, "macro.json")))
    check(u"라이브러리 매크로는 하위를 './' 로 못 부른다",
          graph_model.resolve_macro_ref("./OpenMenu", _lib_dir) is None)
    check(u"'./' 로 가족 밖을 벗어날 수 없다",
          graph_model.resolve_macro_ref("./../Standalone", _parent_dir) is None)

    # --- 범위 검사: 남의 하위를 경로로 집으면 검사가 막는다
    app.macro = model.Macro.load(os.path.join(_lib_dir, "macro.json"))
    app.current_path = None
    app.apply_mode()
    app.graph.add_node({"type": "call", "macro": "Parent/OpenMenu"}, 0, 0)
    _scope = app.check_call_targets()
    check(u"남의 하위 매크로 호출을 검사가 막는다",
          any(u"하위 매크로는 부모와 형제만" in p for p in _scope),
          u"%r" % (_scope,))

    # --- 이름 변경이 형제의 호출 참조를 따라 고친다
    _caller_nodes = [{"id": "n1", "type": "call", "macro": "./ClosePopup"}]
    _write_macro(_sub_a, u"메뉴 열기", nodes=_caller_nodes, settings=False)
    app.macro = model.Macro.load(_parent_json)
    app.apply_mode()
    _callers = app.find_macro_callers("./ClosePopup")
    check(u"하위를 부르는 형제를 찾아낸다", len(_callers) == 1,
          u"%r" % (_callers,))
    _renamed = app._rewrite_call_refs(_callers, "./PopupOff")
    with io.open(os.path.join(_sub_a, "macro.json"), encoding="utf-8") as fh:
        _after = json.loads(fh.read())
    check(u"형제의 호출 참조가 갱신된다",
          _renamed == 1 and _after["nodes"][0]["macro"] == "./PopupOff",
          u"%r" % (_after["nodes"][0],))
finally:
    macro_editor.MACROS_DIR = _saved_macros_dir
    shutil.rmtree(_fam_tmp, ignore_errors=True)


section(u"감시 설정 (handlers / watch)")

_w_tmp = tempfile.mkdtemp(prefix="watch_")
_w_macros = os.path.join(_w_tmp, "Macros")
_w_cond = {"type": "imageExists", "image": "popup.png", "region": [0, 0, 50, 50]}


def _write_watch(folder, name, watch=None, handlers=None, settings=True):
    path = _write_macro(folder, name, settings=settings)
    with io.open(path, encoding="utf-8") as fh:
        data = json.loads(fh.read())
    if watch is not None:
        data["watch"] = watch
    if handlers is not None:
        data["handlers"] = handlers
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))
    return path


def _walk_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        for item in _walk_widgets(child):
            yield item


_w_main_dir = os.path.join(_w_macros, "Main")
_write_watch(os.path.join(_w_macros, "PopupClose"), u"팝업 닫기", watch=_w_cond)
_write_watch(os.path.join(_w_macros, "Plain"), u"평범한 매크로")
_w_main = _write_watch(_w_main_dir, u"메인", handlers=["PopupClose"])
_write_watch(os.path.join(_w_main_dir, "RewardClose"), u"보상창 닫기",
             watch=_w_cond, settings=False)
shutil.copyfile(os.path.join(MACROS_REAL, "Example", "never_matches.png"),
                os.path.join(_w_macros, "PopupClose", "popup.png"))

_saved_macros_dir = macro_editor.MACROS_DIR
macro_editor.MACROS_DIR = _w_macros
try:
    app.macro = model.Macro.load(_w_main)
    app.current_path = None
    app.apply_mode()

    _cands = [r for r, _n in app.watch_candidates()]
    check(u"감시 후보: 감시 조건이 있는 라이브러리 + 가족 하위만",
          sorted(_cands) == ["./RewardClose", "PopupClose"], u"%r" % (_cands,))

    _errs, _warns = app.check_handler_targets()
    check(u"올바른 감시 목록은 검사를 통과한다", not _errs, u"%r" % (_errs,))
    app.macro.data["handlers"] = ["PopupClose", "Plain", "Gone"]
    _errs, _warns = app.check_handler_targets()
    check(u"감시 조건 없는 매크로를 걸면 검사가 막는다",
          any(u"감시 조건(watch)이 없습니다" in e for e in _errs), u"%r" % (_errs,))
    check(u"없는 감시 매크로를 걸면 검사가 막는다",
          any(u"찾을 수 없습니다: Gone" in e for e in _errs), u"%r" % (_errs,))
    app.macro.data["handlers"] = ["PopupClose"]

    # --- 대화상자: 열리고, 목록이 보이고, 감시 조건을 켜고, 간격이 들어간다
    _before = list(app.root.winfo_children())
    app.edit_watch()
    _dialogs = [w for w in app.root.winfo_children()
                if w not in _before and isinstance(w, tk.Toplevel)]
    check(u"감시 설정 대화상자가 열린다", len(_dialogs) == 1, u"%d개" % len(_dialogs))
    if _dialogs:
        _dlg = _dialogs[0]
        _dlg.grab_release()
        _lists = [w for w in _walk_widgets(_dlg) if isinstance(w, tk.Listbox)]
        check(u"걸린 감시가 목록에 보인다",
              len(_lists) == 1 and _lists[0].size() == 1
              and u"PopupClose" in _lists[0].get(0),
              u"%r" % ([l.get(0, "end") for l in _lists],))
        _checks = [w for w in _walk_widgets(_dlg)
                   if isinstance(w, ttk_module.Checkbutton)]
        check(u"감시 매크로로 쓰기 체크가 있다", len(_checks) == 1)
        if _checks:
            _checks[0].invoke()
            root.update_idletasks()
            check(u"체크하면 감시 조건이 생긴다",
                  graph_model.is_watch_macro(app.macro.data),
                  u"%r" % (app.macro.data.get("watch"),))
            _combos = [w for w in _walk_widgets(_dlg)
                       if isinstance(w, ttk_module.Combobox)]
            check(u"감시 조건 편집기가 나타난다", len(_combos) >= 1)
            _checks[0].invoke()
            check(u"체크를 끄면 감시 조건이 지워진다",
                  "watch" not in app.macro.data)
        _entries = [w for w in _walk_widgets(_dlg)
                    if isinstance(w, ttk_module.Entry)
                    and not isinstance(w, ttk_module.Combobox)]
        _buttons = [w for w in _walk_widgets(_dlg)
                    if isinstance(w, ttk_module.Button)]
        _close = [b for b in _buttons if b.cget("text") == u"닫기"]
        if _entries and _close:
            _entries[0].delete(0, "end")
            _entries[0].insert(0, "2.5")
            _close[0].invoke()
            check(u"확인 간격이 설정에 들어간다",
                  app.macro.data["settings"].get("handlerInterval") == 2.5,
                  u"%r" % (app.macro.data["settings"].get("handlerInterval"),))
            check(u"닫기를 누르면 대화상자가 닫힌다", not _dlg.winfo_exists())
        else:
            check(u"간격 칸과 닫기 버튼이 있다", False,
                  u"칸 %d, 닫기 %d" % (len(_entries), len(_close)))
            _dlg.destroy()

    # --- 하위 매크로에서는 간격을 고칠 수 없다 (부모 것을 따른다)
    app.macro = model.Macro.load(os.path.join(_w_main_dir, "RewardClose",
                                              "macro.json"))
    app.current_path = None
    app.apply_mode()
    _before = list(app.root.winfo_children())
    app.edit_watch()
    _dialogs = [w for w in app.root.winfo_children()
                if w not in _before and isinstance(w, tk.Toplevel)]
    if _dialogs:
        _dlg = _dialogs[0]
        _dlg.grab_release()
        _entries = [w for w in _walk_widgets(_dlg)
                    if isinstance(w, ttk_module.Entry)
                    and not isinstance(w, ttk_module.Combobox)]
        check(u"하위 매크로는 간격 칸이 꺼져 있다",
              bool(_entries) and "disabled" in str(_entries[0].cget("state")),
              u"%r" % ([str(e.cget("state")) for e in _entries],))
        _cands = [r for r, _n in app.watch_candidates()]
        check(u"자기 자신은 감시 후보에서 빠진다",
              "./RewardClose" not in _cands, u"%r" % (_cands,))
        _dlg.destroy()

    # --- 감시 조건의 이미지도 '사용 중' 이고 '없는 이미지' 검사 대상이다
    app.macro = model.Macro.load(os.path.join(_w_macros, "PopupClose",
                                              "macro.json"))
    app.apply_mode()
    check(u"있는 감시 이미지는 누락으로 잡히지 않는다",
          app.macro.missing_images() == [], u"%r" % (app.macro.missing_images(),))
    app.macro.data["watch"] = dict(_w_cond, image="nope.png")
    check(u"없는 감시 이미지는 누락으로 잡힌다",
          (u"감시 조건", "nope.png") in app.macro.missing_images(),
          u"%r" % (app.macro.missing_images(),))
    _users = app.find_image_users(os.path.join(_w_macros, "PopupClose",
                                               "popup.png"))
    check(u"감시 조건에만 쓰는 이미지도 사용처로 잡힌다",
          any(u"감시 조건" == node for _p, node in _users), u"%r" % (_users,))

    # --- 감시 매크로의 이름을 바꾸면 감시 목록의 참조도 고친다
    _callers = app.find_macro_callers("PopupClose")
    check(u"감시 목록에 건 매크로도 참조로 잡힌다",
          any(path == _w_main for _r, _id, path in _callers), u"%r" % (_callers,))
    _n = app._rewrite_call_refs(_callers, "PopupOff")
    with io.open(_w_main, encoding="utf-8") as fh:
        _after = json.loads(fh.read())
    check(u"감시 목록의 참조가 새 이름으로 바뀐다",
          _n == 1 and _after.get("handlers") == ["PopupOff"],
          u"%d건 %r" % (_n, _after.get("handlers")))
finally:
    macro_editor.MACROS_DIR = _saved_macros_dir
    shutil.rmtree(_w_tmp, ignore_errors=True)
    app.macro = model.Macro(graph_model.blank(u"새 매크로"))
    app.current_path = None
    app.apply_mode()

section(u"시작 노드로 이동")

_bar_texts = []
for child in app.root.winfo_children():
    for widget in child.winfo_children() if hasattr(child, "winfo_children") else []:
        try:
            _bar_texts.append(widget.cget("text"))
        except Exception:
            pass
check(u"툴바에 '시작 노드로 이동' 버튼이 있다",
      any(t and u"시작 노드로 이동" in t for t in _bar_texts),
      u"%r" % (_bar_texts,))

app.macro = model.Macro(graph_model.blank(u"시작 노드 이동"))
app.current_path = None
app.apply_mode()
_gcv = app.canvas_view
_gcv.reset_view()
check(u"노드가 없으면 이동할 곳도 없다", _gcv.focus_entry() is False)

# 다른 매크로를 열었을 때처럼, 지금 보는 자리에서 아주 멀리 떨어진 노드
_away = _gcv.add_node("log", 4000, 3000)["id"]
_gcv.add_node("log", 4000, 3400)
root.update_idletasks()
check(u"처음 만든 노드가 시작 노드", _gcv.graph.entry == _away)


def _view_size():
    """center_on_node 와 같은 규칙으로 캔버스 크기를 잰다 (아직 안 그려졌으면 기본값)."""
    w = _gcv.canvas.winfo_width()
    h = _gcv.canvas.winfo_height()
    return (w, h) if w > 1 and h > 1 else (800, 600)


_vw, _vh = _view_size()
_r = _gcv.node_rect(_gcv.graph.node(_away))
check(u"이동 전에는 화면 밖에 있다",
      _r[0] > _vw or _r[1] > _vh, u"%r / %r" % (_r, (_vw, _vh)))

_gcv.zoom = 0.75
_keep = set(_gcv.selected_nodes)
app.goto_entry_node()
_r = _gcv.node_rect(_gcv.graph.node(_away))
check(u"시작 노드가 화면 한가운데로 온다",
      abs((_r[0] + _r[2]) / 2.0 - _vw / 2.0) < 1.0
      and abs((_r[1] + _r[3]) / 2.0 - _vh / 2.0) < 1.0,
      u"%r / %r" % (_r, (_vw, _vh)))
check(u"배율은 그대로 둔다", abs(_gcv.zoom - 0.75) < 1e-6, u"%r" % (_gcv.zoom,))
check(u"선택은 건드리지 않는다", _gcv.selected_nodes == _keep,
      u"%r -> %r" % (_keep, _gcv.selected_nodes))

# 시작 노드를 옮겨 지정하면 그쪽으로 간다
_second = [n["id"] for n in _gcv.graph.nodes if n["id"] != _away][0]
_gcv.graph.entry = _second
app.goto_entry_node()
_r = _gcv.node_rect(_gcv.graph.node(_second))
check(u"시작 노드를 바꾸면 그 노드로 간다",
      abs((_r[0] + _r[2]) / 2.0 - _vw / 2.0) < 1.0
      and abs((_r[1] + _r[3]) / 2.0 - _vh / 2.0) < 1.0, u"%r" % (_r,))

# 트리 형식에서는 캔버스가 없다. 죽지 않고 안내만 한다.
app.macro = model.Macro({"name": u"트리", "version": 1, "steps": []})
app.current_path = None
app.apply_mode()
app.goto_entry_node()
check(u"트리 형식에서는 안내만 하고 넘어간다",
      u"노드 모드" in app.status.get(), u"%r" % (app.status.get(),))

section(u"실행 로그 파일")

# 실행 로그 패널은 편집기를 닫으면 사라진다. 나중에 문제를 되짚으려면
# 파일로 남아 있어야 한다. 여기서는 OculiX 를 실제로 돌리지 않고
# 로그가 열리고 · 쌓이고 · 결과와 함께 닫히는지만 본다.

app.macro = model.Macro(graph_model.blank(u"로그 남기기"))
app.current_path = None
app.apply_mode()
_lg1 = app.canvas_view.add_node("log", 0, 0)["id"]
app.canvas_view.graph.entry = _lg1
_ltmp = tempfile.mkdtemp(prefix="runlog_macro_")
app.macro.save(os.path.join(_ltmp, "LogMacro", "macro.json"))

_orig_run_log = runner_module.run_macro
_orig_notify_log = notify.notify
runner_module.run_macro = (
    lambda path, on_line, on_done, start_node=None, resume=False:
    type("FakeJob", (), {"is_running": lambda self: False,
                         "stop": lambda self: None,
                         "cancelled": False})())
notify.notify = lambda title, message, on_error=None: True
try:
    app.job = None
    app.run_macro()
    _log_path = app.runlog.path if app.runlog else None
    check(u"실행하면 로그 파일이 열린다",
          bool(_log_path) and os.path.exists(_log_path), u"%s" % (_log_path,))
    app.log_line(u"[INFO] 실행 중 한 줄", None)
    app._on_run_done(0)
    check(u"끝나면 로그 파일을 닫는다", app.runlog is None)

    _log_text = io.open(_log_path, encoding="utf-8").read() if _log_path else u""
    check(u"실행 중 출력이 파일에 남는다", u"[INFO] 실행 중 한 줄" in _log_text)
    check(u"머리말에 매크로 파일 경로", u"LogMacro" in _log_text)
    check(u"머리말에 매크로 이름", u"로그 남기기" in _log_text)
    check(u"꼬리말에 종료 코드", u"exit 0" in _log_text and u"정상 종료" in _log_text,
          _log_text.strip().splitlines()[-1] if _log_text else u"")
    check(u"로그 경로를 패널에 알려 준다",
          bool(_log_path) and _log_path in app.log.get("1.0", "end"))
    check(u"latest.log 사본이 같은 내용",
          os.path.exists(editor_runlog.LATEST)
          and io.open(editor_runlog.LATEST, encoding="utf-8").read() == _log_text)

    app.log_line(u"실행이 끝난 뒤의 줄", None)
    check(u"닫힌 뒤 줄은 파일에 안 들어간다",
          u"실행이 끝난 뒤의 줄" not in io.open(_log_path, encoding="utf-8").read())

    # 중지한 실행도 이유가 남아야 한다
    app.job = None
    app.run_macro()
    _stopped_path = app.runlog.path
    app.job.cancelled = True
    app._on_run_done(2)
    check(u"중지한 실행은 그렇게 적힌다",
          u"사용자가 중지" in io.open(_stopped_path, encoding="utf-8").read())

    # 실행 중에 편집기를 닫으면 열린 파일이 그대로 남으면 안 된다
    app.job = None
    app.run_macro()
    _aborted_path = app.runlog.path
    app.runlog.abort(u"편집기를 닫음")
    check(u"중단된 실행도 꼬리말이 붙는다",
          u"편집기를 닫음" in io.open(_aborted_path, encoding="utf-8").read())
finally:
    runner_module.run_macro = _orig_run_log
    notify.notify = _orig_notify_log
    app.job = None
    app.runlog = None
    shutil.rmtree(_ltmp, ignore_errors=True)

# 오래된 로그 정리. 무한히 쌓이면 폴더가 못 쓰게 된다.
for _i in range(editor_runlog.KEEP + 5):
    io.open(os.path.join(editor_runlog.LOG_DIR,
                         "20200101-%06d_오래된.log" % _i),
            "w", encoding="utf-8").write(u"x")
editor_runlog.prune()
_left = [n for n in os.listdir(editor_runlog.LOG_DIR)
         if editor_runlog._STAMPED.match(n)]
check(u"오래된 로그는 정리된다", len(_left) == editor_runlog.KEEP, u"%d개" % len(_left))
check(u"latest.log 는 정리 대상이 아니다",
      os.path.exists(editor_runlog.LATEST))
check(u"파일 이름에 쓸 수 없는 글자를 바꾼다",
      editor_runlog._safe_name(u'아침/퀘스트:1') == u"아침_퀘스트_1",
      editor_runlog._safe_name(u'아침/퀘스트:1'))


# ------------------------------------------------------------- 해상도 대응

section(u"해상도 대응")

import nodeclip as editor_nodeclip
import pickers as editor_pickers
import project_panel as editor_panel
import screenutil as editor_screen

_sc_spec = {"window": {"class": "UnityWndClass", "title": u"게임"},
            "client": [1, 30, 1364, 1072], "screen": [2048, 1152]}
_sc_tmp = tempfile.mkdtemp(prefix="scaling_")
_sc_macros = os.path.join(_sc_tmp, "Macros")
_sc_main = os.path.join(_sc_macros, "Main")
_sc_capture = os.path.join(_sc_main, "@1920x1080")
os.makedirs(_sc_capture)
os.makedirs(os.path.join(_sc_main, ".scaled", "1278x1000"))


def _sc_file(*parts):
    with open(os.path.join(*parts), "wb") as out:
        out.write(b"png")


_sc_file(_sc_main, "base.png")
_sc_file(_sc_main, ".scaled", "1278x1000", "base.png")
_sc_file(_sc_capture, "base.png")
_sc_file(_sc_capture, "only.png")

_sc_data = graph_model.blank(u"Main")
_sc_data["settings"]["scaling"] = _sc_spec
_sc_data["nodes"] = [
    {"id": "n1", "type": "click", "point": [88, 73], "ui": {"x": 0, "y": 0}},
    {"id": "n2", "type": "waitImage", "image": "only.png",
     "ui": {"x": 0, "y": 100}},
    {"id": "n3", "type": "click", "image": "base.png",
     "ui": {"x": 0, "y": 200}},
]
_sc_data["entry"] = "n1"
_sc_path = os.path.join(_sc_main, "macro.json")
with io.open(_sc_path, "w", encoding="utf-8") as _fh:
    _fh.write(json.dumps(_sc_data, ensure_ascii=False))

_sc_env = {"screen": (1920, 1080), "client": [1, 31, 1278, 1000]}
_sc_real = (editor_screen.logical_screen_size, editor_screen.game_client,
            editor_screen.window_at, editor_pickers.pick_point,
            macro_editor.MACROS_DIR, editor_panel.simpledialog.askstring,
            mb.askyesno)
editor_screen.logical_screen_size = lambda: _sc_env["screen"]
editor_screen.game_client = lambda window: _sc_env["client"]
macro_editor.MACROS_DIR = _sc_macros
mb.askyesno = lambda *a, **k: True

try:
    _plain = model.Macro()
    check(u"설정이 없으면 Macro.scaling 은 None", _plain.scaling is None)
    app.macro = _plain
    check(u"설정이 없으면 찍은 값을 그대로 저장",
          app._stored_point((83, 71)) == (83, 71))
    check(u"설정이 없으면 좌표 기준 칸을 숨긴다",
          not app.field_visible(schema.SPACE_FIELD))

    app.macro = model.Macro.load(_sc_path)
    app.apply_mode()
    check(u"Macro.scaling 을 읽는다", app.macro.scaling == _sc_spec)
    check(u"설정이 있으면 좌표 기준 칸을 보인다",
          app.field_visible(schema.SPACE_FIELD))

    app.current_step_obj = app.graph.node("n1")
    app.build_properties()
    check(u"속성 패널에 좌표 기준이 나온다",
          _field_widget(app.prop_frame, u"좌표 기준",
                        (ttk_module.Combobox,)) is not None)

    check(u"다른 환경에서 찍은 좌표를 기준 값으로 되돌린다",
          app._stored_point((83, 71)) == (89, 73),
          u"%r" % (app._stored_point((83, 71)),))
    _stored = app._stored_region((871, 836, 411, 201))
    _back = graph_model.Transform(_sc_spec["client"],
                                  _sc_env["client"]).region(_stored)
    check(u"찍은 영역을 기준 값으로 되돌린다",
          _stored is not None and abs(_back[0] - 871) <= 6,
          u"%r -> %r" % (_stored, _back))
    check(u"화면 공간은 화면 크기로 되돌린다",
          app._stored_point((938, 469), {"space": "screen"}) == (1001, 500),
          u"%r" % (app._stored_point((938, 469), {"space": "screen"}),))

    _sc_env["client"] = None
    check(u"다른 화면에서 창을 못 찾으면 저장을 거부한다",
          app._stored_point((83, 71)) is None
          and app._stored_region((1, 2, 3, 4)) is None)
    _sc_env["screen"] = (2048, 1152)
    check(u"기준 화면이면 게임 없이도 고칠 수 있다",
          app._stored_point((83, 71)) == (83, 71))
    _sc_env["client"] = [1, 30, 1364, 1072]
    check(u"기준 환경에서는 찍은 값을 그대로 저장한다",
          app._stored_point((83, 71)) == (83, 71))

    _dest = app._capture_destination("new.png")
    check(u"기준 화면의 캡처는 매크로 폴더에 저장한다",
          _dest == os.path.join(_sc_main, "new.png"), _dest)

    _sc_env["screen"] = (1920, 1080)
    _sc_env["client"] = [1, 31, 1278, 1000]
    _dest = app._capture_destination("new.png")
    check(u"다른 화면의 캡처는 @폴더에 저장한다",
          _dest == os.path.join(_sc_capture, "new.png"), _dest)
    check(u"찍을 때의 창 크기를 함께 남긴다",
          graph_model.read_capture_client(_sc_capture)
          == [1.0, 31.0, 1278.0, 1000.0])

    check(u"@폴더에만 있는 이미지는 없는 이미지가 아니다",
          app.macro.missing_images() == [],
          u"%r" % (app.macro.missing_images(),))
    _sc_names = [label for _k, label, _p in imagepicker.scan_images(
        _sc_main, _sc_macros)]
    check(u"이미지 선택 목록에 @폴더 전용 이미지가 나온다",
          "only.png" in _sc_names, u"%r" % (_sc_names,))
    check(u"이미지 선택 목록에 같은 이름이 두 번 나오지 않는다",
          _sc_names.count("base.png") == 1, u"%r" % (_sc_names,))
    check(u"이미지 선택 목록에 축소본이 나오지 않는다",
          not any(".scaled" in label for label in _sc_names))

    class _SmallTree(object):
        def __init__(self):
            self.rows = []

        def insert(self, parent, _where, text=u"", tags=()):
            self.rows.append(text)
            return len(self.rows)

    class _SmallPanel(object):
        tree = _SmallTree()
        paths = {}
        app = app
        _insert_dir = editor_panel.ProjectPanel._insert_dir

        def refresh(self, _select=None):
            pass

    _SmallPanel()._insert_dir("", _sc_main)
    check(u"프로젝트 패널에 축소본 폴더가 나오지 않는다",
          not any(".scaled" in row for row in _SmallPanel.tree.rows),
          u"%r" % (_SmallPanel.tree.rows,))
    check(u"프로젝트 패널에 @폴더는 나온다",
          any("@1920x1080" in row for row in _SmallPanel.tree.rows))

    check(u"@폴더 변종의 사용처를 찾는다", any(
        user[1] == "n3" for user in app.find_image_users(
            os.path.join(_sc_capture, "base.png"))))

    # 다른 매크로로 복사하면 변종도 함께 간다
    _sc_other = os.path.join(_sc_macros, "Other")
    os.makedirs(_sc_other)
    _map, _notes, _count = editor_nodeclip.import_images(
        {"nodes": [{"type": "click", "image": "base.png"},
                   {"type": "click", "image": "only.png"}],
         "sourceDir": _sc_main}, _sc_other)
    check(u"복사할 때 기준 이미지와 변종을 함께 옮긴다", _count == 3 and all(
        os.path.isfile(os.path.join(_sc_other, *parts)) for parts in (
            ("base.png",), ("@1920x1080", "base.png"),
            ("@1920x1080", "only.png"), ("@1920x1080", "capture.json"))),
        u"%r %r" % (_count, _notes))

    # 어느 변종을 고쳐도 이름은 함께 바뀐다
    editor_panel.simpledialog.askstring = lambda *a, **k: u"renamed.png"
    editor_panel.ProjectPanel._rename(_SmallPanel(),
                                      os.path.join(_sc_capture, "base.png"))
    check(u"이름을 바꾸면 기준 이미지와 변종이 함께 바뀐다",
          os.path.isfile(os.path.join(_sc_main, "renamed.png"))
          and os.path.isfile(os.path.join(_sc_capture, "renamed.png"))
          and not os.path.exists(os.path.join(_sc_capture, "base.png")))
    _saved = json.loads(io.open(_sc_path, encoding="utf-8").read())
    check(u"노드의 참조도 함께 바뀐다",
          [n for n in _saved["nodes"] if n["id"] == "n3"][0]["image"]
          == "renamed.png")

    # 하위 매크로는 부모 설정을 쓴다
    _sc_sub = os.path.join(_sc_main, "Sub")
    os.makedirs(_sc_sub)
    with io.open(os.path.join(_sc_sub, "macro.json"), "w",
                 encoding="utf-8") as _fh:
        _fh.write(json.dumps(graph_model.blank(u"Sub"), ensure_ascii=False))
    _sub_macro = model.Macro.load(os.path.join(_sc_sub, "macro.json"))
    check(u"하위 매크로는 부모의 해상도 설정을 읽는다",
          _sub_macro.scaling == _sc_spec)

    # 창을 찍어서 기준으로 등록한다
    app.macro = model.Macro()
    app.macro.data.pop("settings", None)
    app.apply_mode()
    editor_pickers.pick_point = lambda _parent: (50, 60)
    editor_screen.window_at = lambda x, y: {
        "class": "Cls", "title": u"창", "client": [1, 2, 300, 200]}


    def _settings_buttons():
        _before = list(app.root.winfo_children())
        app.edit_settings()
        _dialogs = [w for w in app.root.winfo_children()
                    if w not in _before and isinstance(w, tk.Toplevel)]
        check(u"설정 대화상자에 해상도 대응 칸이 있어도 열린다",
              len(_dialogs) == 1)
        _dialogs[0].grab_release()
        return {w.cget("text"): w for w in _find_widgets(
            _dialogs[0], (ttk_module.Button,))}

    _buttons = _settings_buttons()
    _buttons[u"기준 창 등록"].invoke()
    _buttons[u"취소"].invoke()
    check(u"취소하면 등록하지 않는다",
          "scaling" not in app.macro.data["settings"])

    _buttons = _settings_buttons()
    _buttons[u"기준 창 등록"].invoke()
    _buttons[u"확인"].invoke()
    check(u"찍은 창을 기준으로 등록한다",
          app.macro.data["settings"].get("scaling") == {
              "window": {"class": "Cls", "title": u"창"},
              "client": [1, 2, 300, 200], "screen": [1920, 1080]},
          u"%r" % (app.macro.data["settings"].get("scaling"),))

    _buttons = _settings_buttons()
    _buttons[u"해제"].invoke()
    _buttons[u"확인"].invoke()
    check(u"해제하면 설정이 사라진다",
          "scaling" not in app.macro.data["settings"])

    # 검사가 벌어진 가로세로비를 경고한다
    app.macro.data["settings"]["scaling"] = _sc_spec
    _sc_env["client"] = [1, 31, 1278, 950]
    check(u"가로세로비가 벌어지면 검사가 경고한다",
          any(u"가로세로비" in line for line in app._scaling_warnings()))
    _sc_env["client"] = [1, 31, 1278, 1000]
    check(u"비율이 맞으면 경고하지 않는다", app._scaling_warnings() == [])
    check(u"상태 글이 현재 배율을 보여 준다",
          u"기준 1364x1072 -> 현재 1278x1000"
          in app._scaling_text(app.macro.scaling),
          app._scaling_text(app.macro.scaling))
finally:
    (editor_screen.logical_screen_size, editor_screen.game_client,
     editor_screen.window_at, editor_pickers.pick_point,
     macro_editor.MACROS_DIR, editor_panel.simpledialog.askstring,
     mb.askyesno) = _sc_real
    shutil.rmtree(_sc_tmp, ignore_errors=True)


print("")
print("=" * 62)
print("passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
try:
    root.destroy()
except Exception:
    pass
editor_settings.PATH = _real_settings_path
shutil.rmtree(_settings_tmp, ignore_errors=True)
shutil.rmtree(_runlog_tmp, ignore_errors=True)
if FAIL:
    print(u"실패:")
    for name in FAIL:
        print("  - %s" % name)
    sys.exit(1)
print("GUITEST_OK")
sys.exit(0)
