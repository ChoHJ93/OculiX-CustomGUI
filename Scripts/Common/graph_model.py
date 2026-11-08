# -*- coding: utf-8 -*-
"""노드 그래프 모델 - 편집기(Python 3)와 실행 엔진(Jython 2.7)이 함께 쓴다.

핀 정의와 검증 규칙을 한 곳에 두기 위해 양쪽에서 import 한다.
따라서 이 파일은 Python 2.7과 3.x 양쪽에서 돌아가는 문법만 쓴다
(f-string 금지, `except X as e` 사용).

형식
    {
      "name": "...",
      "version": 2,
      "format": "graph",
      "settings": {..., "maxSteps": 5000, "maxSeconds": 300},
      "handlers": ["시스템팝업닫기"],        (선택) 도는 동안 걸 감시 매크로
      "watch": {...조건...},                 (선택) 이 매크로가 감시 매크로일 때
      "entry": "n1",
      "nodes": [
        {"id": "n1", "type": "log", "message": "hi", "ui": {"x": 80, "y": 60}},
        {"id": "n2", "type": "if",  "condition": {...}, "ui": {...}}
      ],
      "links": [
        {"from": "n1", "pin": "next",  "to": "n2"},
        {"from": "n2", "pin": "true",  "to": "n3"},
        {"from": "n2", "pin": "false", "to": "n4"}
      ]
    }

실행 핀 규칙
    출력 핀 하나에는 링크가 하나만 붙는다 (블루프린트와 동일).
    입력에는 여러 링크가 모일 수 있다 (흐름 합류).
"""

import math
import os

try:                        # Jython 2.7 / CPython 3 양쪽에서 문자열을 가린다
    _TEXT_TYPES = (str, unicode)
except NameError:
    _TEXT_TYPES = (str,)

FORMAT_GRAPH = "graph"
FORMAT_TREE = "tree"

# 편집기가 마지막으로 선택한 노드 id. 실행에는 쓰지 않는다.
LAST_SELECTED = "lastSelected"

# ------------------------------------------------------------------ 매개변수
#
# 매크로는 입력 매개변수를 선언할 수 있고, 호출 노드가 값을 넘긴다.
#
#     선언 (macro.json 최상위)
#       "params": [{"name": "retryCount", "type": "int", "default": 3}]
#     호출 (call 노드)
#       {"type": "call", "macro": "Common/Login", "args": {"retryCount": 5}}
#
# 값은 호출마다 새로 묶인다. 같은 매크로를 다른 값으로 여러 번 불러도
# 서로 섞이지 않는다 - 호출된 매크로는 자기 엔진 인스턴스를 새로 받기 때문이다.
# 지금은 원시 타입만 다룬다. 노드끼리 값을 선으로 잇는 데이터 핀은 없다.

PARAM_TYPES = ("int", "float", "string", "bool")
PARAM_TYPE_LABELS = {
    "int": u"정수",
    "float": u"실수",
    "string": u"문자열",
    "bool": u"참/거짓",
}

# 매개변수 비교 연산자. 문자열에는 ==/!= 만 쓰는 것이 안전하다.
PARAM_OPS = ("==", "!=", "<", "<=", ">", ">=")

_TRUE_WORDS = ("true", "1", "yes", "y", "on", u"참")
_FALSE_WORDS = ("false", "0", "no", "n", "off", u"거짓", "")


class ParamError(Exception):
    """매개변수 선언이나 전달값이 잘못됐을 때."""


def declared_params(macro):
    """매크로가 선언한 매개변수 목록. 없으면 빈 목록."""
    params = macro.get("params") if isinstance(macro, dict) else None
    return list(params) if isinstance(params, list) else []


def param_names(macro):
    return [p.get("name") for p in declared_params(macro) if p.get("name")]


# 반복이 값 목록을 하나씩 넣어 주는 변수. call 의 인자에서 PARAM_REF 로 읽는다.
# 선언된 매개변수(params)와 달리 반복 본문 안에서만 살아 있다.
PARAM_REF = "$param"


def is_param_ref(value):
    """{"$param": "이름"} 형태인가."""
    return isinstance(value, dict) and list(value.keys()) == [PARAM_REF]


def param_ref(name):
    return {PARAM_REF: name}


def foreach_spec(node):
    """repeat 노드의 forEach 설정. 없으면 None."""
    if not isinstance(node, dict) or node.get("type") != "repeat":
        return None
    spec = node.get("forEach")
    return spec if isinstance(spec, dict) else None


def loop_params(macro):
    """forEach 반복이 만드는 변수 -> 타입. 이름이 겹치면 먼저 나온 것을 쓴다.

    선언된 매개변수와 달리 매크로 단위가 아니라 노드에 붙어 있어서,
    조건 검증과 편집기 목록을 위해 여기서 모아 준다.
    """
    found = {}
    nodes = macro.get("nodes") if isinstance(macro, dict) else None
    for node in nodes or []:
        spec = foreach_spec(node)
        if not spec:
            continue
        name = spec.get("param")
        if name and name not in found:
            found[name] = spec.get("type")
    return found


def scope_param_names(macro):
    """이 매크로 안에서 이름으로 참조할 수 있는 값 전부 (선언 + 반복 변수)."""
    names = list(param_names(macro))
    for name in sorted(loop_params(macro).keys()):
        if name not in names:
            names.append(name)
    return names


def validate_foreach(node):
    """forEach 설정 자체를 검사한다. 오류 목록을 반환."""
    spec = foreach_spec(node)
    if spec is None:
        return []
    where = u"노드 %s의 값 반복" % node.get("id")
    problems = []
    name = spec.get("param")
    if not name or not isinstance(name, _TEXT_TYPES):
        problems.append(u"%s: 변수 이름이 필요합니다" % where)
    ptype = spec.get("type")
    if ptype not in PARAM_TYPES:
        problems.append(u"%s: 타입은 %s 중 하나여야 합니다 (지금 %r)"
                        % (where, u"/".join(PARAM_TYPES), ptype))
        return problems
    values = spec.get("values")
    if not isinstance(values, list) or not values:
        problems.append(u"%s: 값이 하나 이상 필요합니다" % where)
        return problems
    for index, raw in enumerate(values):
        try:
            coerce_param(raw, ptype, u"%s %d번째 값" % (where, index + 1))
        except ParamError as exc:
            problems.append(u"%s" % exc)
    return problems


def foreach_values(spec, where=u"값 반복"):
    """forEach 의 값 목록을 선언된 타입으로 바꿔서 돌려준다."""
    ptype = spec.get("type")
    return [coerce_param(raw, ptype, u"%s %d번째 값" % (where, i + 1))
            for i, raw in enumerate(spec.get("values") or [])]


def resolve_args(args, scope):
    """call 의 인자에서 {"$param": 이름} 을 실제 값으로 바꾼다.

    (값 dict, 문제목록) 을 반환한다. 이름이 범위에 없으면 문제로 남긴다 -
    조용히 비워 두면 반복 밖에서 쓴 참조가 말없이 어긋난다.
    """
    args = args if isinstance(args, dict) else {}
    scope = scope if isinstance(scope, dict) else {}
    out = {}
    problems = []
    for key in sorted(args.keys()):
        value = args[key]
        if not is_param_ref(value):
            out[key] = value
            continue
        name = value.get(PARAM_REF)
        if name in scope:
            out[key] = scope[name]
        else:
            problems.append(
                u"넘길 값 '%s': 참조한 '%s' 가 지금 범위에 없습니다 "
                u"(반복 본문 밖에서 반복 변수를 쓰지 않았는지 확인하세요)"
                % (key, name))
    return out, problems


def coerce_param(value, ptype, where=u"매개변수"):
    """값을 선언된 타입으로 바꾼다. 못 바꾸면 ParamError.

    조용히 넘기지 않는 이유: 문자열 "3" 과 숫자 3 이 섞이면 비교 조건이
    말없이 어긋난다. 그런 실패는 나중에 찾기가 매우 어렵다.
    """
    if ptype == "string":
        if isinstance(value, bool):
            return u"true" if value else u"false"
        if isinstance(value, _TEXT_TYPES):
            return value
        return u"%s" % (value,)

    if ptype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, _TEXT_TYPES):
            text = value.strip().lower()
            if text in _TRUE_WORDS:
                return True
            if text in _FALSE_WORDS:
                return False
            raise ParamError(u"%s: 참/거짓으로 볼 수 없습니다: %r" % (where, value))
        return bool(value)

    if ptype in ("int", "float"):
        if isinstance(value, bool):
            raise ParamError(u"%s: 참/거짓을 숫자로 쓰지 않습니다" % where)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ParamError(u"%s: 숫자로 볼 수 없습니다: %r" % (where, value))
        if ptype == "int":
            if number != int(number):
                raise ParamError(u"%s: 정수가 아닙니다: %r" % (where, value))
            return int(number)
        return number

    raise ParamError(u"%s: 모르는 타입입니다: %r" % (where, ptype))


def validate_params(macro):
    """매개변수 **선언** 자체를 검사한다. 오류 목록을 반환."""
    problems = []
    seen = set()
    for index, param in enumerate(declared_params(macro)):
        where = u"매개변수 %d번" % (index + 1)
        if not isinstance(param, dict):
            problems.append(u"%s: 형식이 잘못됐습니다: %r" % (where, param))
            continue
        name = param.get("name")
        if not name or not isinstance(name, _TEXT_TYPES):
            problems.append(u"%s: 이름이 필요합니다" % where)
            continue
        where = u"매개변수 '%s'" % name
        if name in seen:
            problems.append(u"%s: 이름이 중복됩니다" % where)
        seen.add(name)
        ptype = param.get("type")
        if ptype not in PARAM_TYPES:
            problems.append(u"%s: 타입은 %s 중 하나여야 합니다 (지금 %r)"
                            % (where, u"/".join(PARAM_TYPES), ptype))
            continue
        if "default" in param:
            try:
                coerce_param(param["default"], ptype, where + u" 기본값")
            except ParamError as exc:
                problems.append(u"%s" % exc)
    return problems


def bind_params(macro, args, allow_refs=False):
    """선언과 전달값을 맞춰 실제로 쓸 값 dict 를 만든다.

    (값, 문제목록) 을 반환한다. 문제가 있으면 호출하는 쪽이 멈춘다.
    선언에 없는 값을 넘기면 오류다 - 이름을 바꿨을 때 조용히 무시되면
    매크로가 왜 안 먹는지 찾을 수 없기 때문이다.

    allow_refs=True 는 **실행 전 검사**용이다. {"$param": 이름} 은 아직 값이
    아니라 이름이므로 타입 변환을 하지 않고 통과시킨다. 실행 시점에는
    resolve_args 가 이미 값으로 바꿔 놓으므로 기본값(False)을 그대로 쓴다 -
    그래야 풀리지 않은 참조가 흘러들어온 것을 엔진이 잡아낸다.
    """
    args = args if isinstance(args, dict) else {}
    declared = declared_params(macro)
    values = {}
    problems = []

    known = set()
    for param in declared:
        name = param.get("name")
        if not name:
            continue
        known.add(name)
        ptype = param.get("type")
        where = u"매개변수 '%s'" % name
        if name in args:
            raw = args[name]
            if is_param_ref(raw):
                if allow_refs:
                    # 값은 실행할 때 정해진다. 여기서는 이름이 대상 매크로에
                    # 선언돼 있는지만 본 셈이다.
                    values[name] = raw
                    continue
                problems.append(
                    u"%s: 참조 %s 가 값으로 바뀌지 않았습니다" % (where, raw))
                continue
        elif "default" in param:
            raw = param["default"]
        else:
            problems.append(u"%s: 값이 필요합니다 (기본값도 없습니다)" % where)
            continue
        try:
            values[name] = coerce_param(raw, ptype, where)
        except ParamError as exc:
            problems.append(u"%s" % exc)

    for name in sorted(args.keys()):
        if name not in known:
            problems.append(u"넘긴 값 '%s' 는 이 매크로에 선언되지 않았습니다"
                            % name)
    return values, problems


# 엔진의 Engine.evaluate() 가 실제로 처리하는 조건 종류. 편집기의
# schema.CONDITION_TYPES 와 이것이 어긋나면 편집기에서 만들 수 있는데
# 실행하면 죽는 조건이 생긴다. selftest 가 둘을 대조한다.
CONDITION_TYPES = ("imageExists", "imageMissing", "textExists", "textMissing",
                   "colorMatches", "paramCompare", "not", "all", "any")



def _conditions_in(cond):
    """조건 하나와 그 안에 중첩된 조건들을 모두 훑는다."""
    if not isinstance(cond, dict):
        return []
    out = [cond]
    if isinstance(cond.get("condition"), dict):
        out.extend(_conditions_in(cond["condition"]))
    for sub in cond.get("conditions") or []:
        out.extend(_conditions_in(sub))
    return out


def _all_conditions(node):
    """노드가 품고 있는 조건 전부 (if 의 condition, repeat 의 while)."""
    out = []
    for key in ("condition", "while"):
        out.extend(_conditions_in(node.get(key)))
    return out


def compare_params(left, op, right):
    """매개변수 비교. 양쪽은 이미 같은 타입으로 맞춰져 있어야 한다."""
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise ParamError(u"모르는 비교 연산자입니다: %r" % (op,))

# 노드 종류별 실행 출력 핀. (핀 이름, 표시 이름)
EXEC_PINS = {
    "if": [("true", u"참"), ("false", u"거짓")],
    "repeat": [("body", u"본문"), ("completed", u"완료")],
    "break": [],
}
DEFAULT_PINS = [("next", u"다음")]

# 실패 전용 출력 핀. 이 핀에 노드를 연결하면 그 단계가 실패했을 때 그쪽으로 흐른다.
# 연결하지 않으면 예전처럼 onFail 설정(중단 / 무시하고 계속)을 따른다.
FAIL_PIN = "fail"
FAIL_PIN_LABEL = u"실패"

# 흐름만 바꾸는 break 를 뺀 모든 노드가 실패 핀을 가진다.
# 실패할 일이 없는 노드(log 등)에서는 그냥 쓰이지 않을 뿐이라 규칙을 단순하게 뒀다.
NO_FAIL_PIN = ("break",)

# 루프로 취급되는 노드 - 순환이 이 노드를 지나면 상한이 걸린다
LOOP_TYPES = ("repeat",)

DEFAULT_MAX_STEPS = 5000
DEFAULT_MAX_SECONDS = 300

# 매크로 호출 중첩 깊이 상한. 순환 호출을 별도로 잡더라도 최후의 방어선으로 둔다.
MAX_CALL_DEPTH = 16


# 노드를 '사용 안 함'으로 꺼놨을 때 어느 핀으로 흘려보낼지.
# if를 끄면 조건을 거짓으로 본다. repeat을 끄면 본문을 건너뛴다.
SKIP_PINS = {
    "if": "false",
    "repeat": "completed",
    "break": None,
}


# 핀 타입. 지금은 실행 핀 하나뿐이지만, 나중에 값을 넘기는 데이터 핀이
# 생기면 여기에 종류가 늘어난다. 편집기는 이 값을 노드에 표시한다.
PIN_TYPE_EXEC = "exec"
PIN_TYPE_FAIL = "fail"

PIN_TYPE_LABELS = {
    PIN_TYPE_EXEC: u"Exec",
    PIN_TYPE_FAIL: u"Exec",
}

PIN_TYPE_COLORS = {
    PIN_TYPE_EXEC: "#e8e8f0",
    PIN_TYPE_FAIL: "#ff7b72",     # 실패 경로는 붉게
}


def has_fail_pin(node_type):
    return node_type not in NO_FAIL_PIN


def exec_pins(node_type):
    """이 종류의 노드가 가진 실행 출력 핀 목록. 실패 핀이 마지막에 붙는다."""
    pins = list(EXEC_PINS.get(node_type, DEFAULT_PINS))
    if has_fail_pin(node_type):
        pins.append((FAIL_PIN, FAIL_PIN_LABEL))
    return pins


def pin_type(node_type, pin):
    """출력 핀의 타입."""
    if pin == FAIL_PIN:
        return PIN_TYPE_FAIL
    return PIN_TYPE_EXEC


def input_pin_type(node_type):
    """입력 핀의 타입."""
    return PIN_TYPE_EXEC


def pin_type_label(pin_type_name):
    return PIN_TYPE_LABELS.get(pin_type_name, pin_type_name)


def pin_type_color(pin_type_name):
    return PIN_TYPE_COLORS.get(pin_type_name, "#cccccc")


def skip_pin(node_type):
    """비활성화된 노드를 지나갈 때 따라갈 핀."""
    if node_type in SKIP_PINS:
        return SKIP_PINS[node_type]
    return "next"


def pin_names(node_type):
    return [name for name, _label in exec_pins(node_type)]


def is_graph(data):
    if not isinstance(data, dict):
        return False
    if data.get("format") == FORMAT_GRAPH:
        return True
    return "nodes" in data and "steps" not in data


class GraphError(Exception):
    pass


class Graph(object):

    def __init__(self, data=None):
        if data is None:
            data = blank()
        self.data = data
        self.data.setdefault("format", FORMAT_GRAPH)
        self.data.setdefault("nodes", [])
        self.data.setdefault("links", [])
        self.data.setdefault("settings", {})

    # ------------------------------------------------------------------ 접근

    @property
    def nodes(self):
        return self.data["nodes"]

    @property
    def links(self):
        return self.data["links"]

    @property
    def entry(self):
        return self.data.get("entry")

    @entry.setter
    def entry(self, node_id):
        self.data["entry"] = node_id

    @property
    def last_selected(self):
        """마지막으로 선택한 노드 id. 지워진 노드를 가리킬 수 있다."""
        return self.data.get(LAST_SELECTED)

    @last_selected.setter
    def last_selected(self, node_id):
        self.data[LAST_SELECTED] = node_id

    def node(self, node_id):
        for n in self.nodes:
            if n.get("id") == node_id:
                return n
        return None

    def index_of(self, node_id):
        for i, n in enumerate(self.nodes):
            if n.get("id") == node_id:
                return i
        return -1

    def target(self, node_id, pin):
        """(node_id, pin)에 연결된 대상 노드 id. 없으면 None."""
        for link in self.links:
            if link.get("from") == node_id and link.get("pin") == pin:
                return link.get("to")
        return None

    def outgoing(self, node_id):
        return [l for l in self.links if l.get("from") == node_id]

    def incoming(self, node_id):
        return [l for l in self.links if l.get("to") == node_id]

    # ------------------------------------------------------------------ 편집

    def new_id(self, prefix="n"):
        used = set(n.get("id") for n in self.nodes)
        i = 1
        while True:
            candidate = "%s%d" % (prefix, i)
            if candidate not in used:
                return candidate
            i += 1

    def add_node(self, node, x=0, y=0):
        if "id" not in node:
            node["id"] = self.new_id()
        if self.node(node["id"]) is not None:
            raise GraphError(u"이미 있는 노드 id: %s" % node["id"])
        node.setdefault("ui", {})
        node["ui"].setdefault("x", int(x))
        node["ui"].setdefault("y", int(y))
        self.nodes.append(node)
        if not self.entry:
            self.entry = node["id"]
        return node

    def remove_node(self, node_id):
        index = self.index_of(node_id)
        if index < 0:
            return None
        removed = self.nodes.pop(index)
        self.data["links"] = [l for l in self.links
                              if l.get("from") != node_id and l.get("to") != node_id]
        if self.entry == node_id:
            self.entry = self.nodes[0]["id"] if self.nodes else None
        return removed

    def connect(self, from_id, pin, to_id):
        """출력 핀 하나에는 링크 하나. 기존 링크는 교체된다."""
        if self.node(from_id) is None:
            raise GraphError(u"출발 노드가 없습니다: %s" % from_id)
        if self.node(to_id) is None:
            raise GraphError(u"도착 노드가 없습니다: %s" % to_id)
        if pin not in pin_names(self.node(from_id).get("type")):
            raise GraphError(u"%s 노드에 '%s' 핀이 없습니다"
                             % (self.node(from_id).get("type"), pin))
        if from_id == to_id:
            raise GraphError(u"자기 자신에게 연결할 수 없습니다")
        self.disconnect(from_id, pin)
        self.links.append({"from": from_id, "pin": pin, "to": to_id})
        return True

    def disconnect(self, from_id, pin):
        before = len(self.links)
        self.data["links"] = [l for l in self.links
                              if not (l.get("from") == from_id and l.get("pin") == pin)]
        return len(self.links) != before

    def move_node(self, node_id, x, y):
        node = self.node(node_id)
        if node is None:
            return
        node.setdefault("ui", {})
        node["ui"]["x"] = int(x)
        node["ui"]["y"] = int(y)

    # ------------------------------------------------------------------ 분석

    def reachable(self):
        """entry에서 실행 링크로 도달 가능한 노드 id 집합."""
        if not self.entry:
            return set()
        seen = set()
        stack = [self.entry]
        while stack:
            current = stack.pop()
            if current in seen or self.node(current) is None:
                continue
            seen.add(current)
            for link in self.outgoing(current):
                stack.append(link.get("to"))
        return seen

    def find_cycles(self):
        """순환 경로 목록. 각 항목은 노드 id 리스트."""
        cycles = []
        colour = {}

        def visit(node_id, path):
            colour[node_id] = 1
            path.append(node_id)
            for link in self.outgoing(node_id):
                nxt = link.get("to")
                if self.node(nxt) is None:
                    continue
                state = colour.get(nxt, 0)
                if state == 1:
                    start = path.index(nxt)
                    cycles.append(list(path[start:]))
                elif state == 0:
                    visit(nxt, path)
            path.pop()
            colour[node_id] = 2

        for node in self.nodes:
            if colour.get(node.get("id"), 0) == 0:
                visit(node.get("id"), [])
        return cycles

    def unbounded_cycles(self):
        """루프 노드를 지나지 않는 순환. 실행 예산에만 의존하게 되는 것들."""
        result = []
        for cycle in self.find_cycles():
            has_loop = False
            for node_id in cycle:
                node = self.node(node_id)
                if node is not None and node.get("type") in LOOP_TYPES:
                    has_loop = True
                    break
            if not has_loop:
                result.append(cycle)
        return result

    def validate(self):
        """(오류, 경고) 두 목록을 반환. 오류가 있으면 실행하면 안 된다."""
        errors = []
        warnings = []

        ids = [n.get("id") for n in self.nodes]
        for node_id in set(ids):
            if ids.count(node_id) > 1:
                errors.append(u"중복된 노드 id: %s" % node_id)
        for node in self.nodes:
            if not node.get("id"):
                errors.append(u"id 없는 노드가 있습니다")
            if not node.get("type"):
                errors.append(u"노드 %s: type이 없습니다" % node.get("id"))

        if not self.nodes:
            errors.append(u"노드가 하나도 없습니다")
        elif not self.entry:
            errors.append(u"시작 노드(entry)가 지정되지 않았습니다")
        elif self.node(self.entry) is None:
            errors.append(u"시작 노드 %s 를 찾을 수 없습니다" % self.entry)

        for link in self.links:
            src = self.node(link.get("from"))
            dst = self.node(link.get("to"))
            if src is None:
                errors.append(u"연결의 출발 노드가 없습니다: %s" % link.get("from"))
                continue
            if dst is None:
                errors.append(u"연결의 도착 노드가 없습니다: %s" % link.get("to"))
                continue
            if link.get("pin") not in pin_names(src.get("type")):
                errors.append(u"노드 %s(%s)에 '%s' 핀이 없습니다"
                              % (src.get("id"), src.get("type"), link.get("pin")))

        seen_pins = set()
        for link in self.links:
            key = (link.get("from"), link.get("pin"))
            if key in seen_pins:
                errors.append(u"출력 핀 %s.%s 에 연결이 두 개 이상입니다" % key)
            seen_pins.add(key)

        errors.extend(validate_node_params(self.nodes, warnings))

        reachable = self.reachable()
        unreachable = [n for n in self.nodes if n.get("id") not in reachable]
        for node in unreachable:
            warnings.append(u"노드 %s(%s)는 시작 노드에서 닿지 않습니다"
                            % (node.get("id"), node.get("type")))

        # 시작 노드가 다른 노드로부터 입력을 받고 있는데 앞쪽에 닿지 않는 노드가
        # 있다면, 시작 노드를 잘못 지정했을 가능성이 높다.
        # 노드를 추가한 순서 때문에 첫 노드가 시작으로 굳어지는 실수가 잦다.
        if self.entry and unreachable and self.incoming(self.entry):
            heads = [n.get("id") for n in unreachable if not self.incoming(n.get("id"))]
            if heads:
                warnings.append(
                    u"시작 노드 %s 가 다른 노드의 연결을 받고 있습니다. "
                    u"실제 시작은 %s 인 것 같습니다 — 노드를 우클릭해 "
                    u"'시작 노드로 지정'을 확인하세요."
                    % (self.entry, u" 또는 ".join(heads)))

        for node in self.nodes:
            if node.get("onFail") == "continue" and                     self.target(node.get("id"), FAIL_PIN):
                warnings.append(
                    u"노드 %s: '실패' 핀이 연결되어 있어 '실패 시: 무시하고 계속' "
                    u"설정은 쓰이지 않습니다 (핀이 우선)" % node.get("id"))

        for cycle in self.unbounded_cycles():
            warnings.append(
                u"순환 %s 은 반복 노드를 지나지 않습니다. "
                u"실행 예산(maxSteps/maxSeconds)에만 의존해 멈춥니다."
                % u" -> ".join(cycle))

        for node in self.nodes:
            if node.get("type") == "repeat":
                # 반복 방식은 셋 중 하나뿐이다. 둘 이상 적혀 있으면 어느 쪽이
                # 뜻인지 알 수 없다 - 예전에 times 가 조용히 이겨서 조건 반복이
                # 조건을 보지도 않고 끝난 적이 있다. 짐작하지 않는다.
                modes = [key for key in ("times", "while", "forEach")
                         if key in node]
                if not modes:
                    errors.append(
                        u"노드 %s: 반복 횟수(times) / 조건(while) / "
                        u"값 목록(forEach) 중 하나가 필요합니다" % node.get("id"))
                if len(modes) > 1:
                    errors.append(
                        u"노드 %s: 반복 방식을 하나만 골라야 합니다 "
                        u"(지금 %s 가 함께 있습니다)"
                        % (node.get("id"), u", ".join(modes)))
                if "while" in node and "maxIterations" not in node:
                    errors.append(u"노드 %s: 조건 반복에는 maxIterations가 필수입니다"
                                  % node.get("id"))
                errors.extend(validate_foreach(node))
                spec = foreach_spec(node)
                if spec and spec.get("param") in set(param_names(self.data)):
                    # 같은 이름이면 반복이 도는 동안 선언된 매개변수가 가려진다.
                    errors.append(
                        u"노드 %s: 반복 변수 '%s' 가 선언된 매개변수와 이름이 "
                        u"같습니다. 다른 이름을 쓰세요"
                        % (node.get("id"), spec.get("param")))
            if node.get("type") == "if" and not node.get("condition"):
                errors.append(u"노드 %s: 조건이 없습니다" % node.get("id"))

        errors.extend(validate_params(self.data))
        errors.extend(validate_handler_decl(self.data, warnings))
        errors.extend(validate_scaling(self.data))
        # 조건에 종류가 없으면 실행할 때 'unknown condition type: None' 으로
        # 죽는다. 편집기의 AND/OR 목록에는 'None' 이라고만 보여서 왜 안 되는지
        # 알기 어렵다. 검사에서 먼저 잡는다.
        for node in self.nodes:
            for cond in _all_conditions(node):
                ctype = cond.get("type")
                if ctype not in CONDITION_TYPES:
                    errors.append(
                        u"노드 %s: 조건의 종류가 잘못됐습니다 (%r). "
                        u"조건을 지우고 다시 넣으세요"
                        % (node.get("id"), ctype))

        # 조건이 참조하는 매개변수가 이 매크로에 선언돼 있는지.
        # 이름을 바꿨을 때 조건이 조용히 어긋나는 것을 막는다.
        known = set(scope_param_names(self.data))
        for node in self.nodes:
            for cond in _all_conditions(node):
                if cond.get("type") != "paramCompare":
                    continue
                where = u"노드 %s" % node.get("id")
                name = cond.get("param")
                if not name:
                    errors.append(u"%s: 비교할 매개변수를 골라야 합니다" % where)
                elif name not in known:
                    errors.append(
                        u"%s: '%s' 는 이 매크로에 선언되지 않은 매개변수입니다"
                        % (where, name))
                if cond.get("op") not in PARAM_OPS:
                    errors.append(u"%s: 비교 방법이 잘못됐습니다 (%r)"
                                  % (where, cond.get("op")))

        # 호출 인자가 참조하는 이름이 이 매크로에 있는지. 범위(반복 본문 안인지)
        # 까지는 실행 시점에 resolve_args 가 잡는다.
        for node in self.nodes:
            if node.get("type") != "call":
                continue
            args = node.get("args")
            if not isinstance(args, dict):
                continue
            for key in sorted(args.keys()):
                if not is_param_ref(args[key]):
                    continue
                name = args[key].get(PARAM_REF)
                if name not in known:
                    errors.append(
                        u"노드 %s: 넘길 값 '%s' 가 참조한 '%s' 는 이 매크로에 "
                        u"없는 이름입니다" % (node.get("id"), key, name))

        return errors, warnings


# ------------------------------------------------------- 매크로 참조 (call 노드)

def find_macros_root(start_dir):
    """매크로 모음 폴더를 찾는다.

    호출 참조는 이 폴더 기준의 상대 경로다. 폴더 이름이 'Macros'인 조상을
    찾고, 없으면 현재 매크로 폴더의 부모를 쓴다.
    """
    current = os.path.abspath(start_dir)
    while True:
        if os.path.basename(current) == "Macros":
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        if os.path.basename(parent) == "Macros":
            return parent
        current = parent
    return os.path.dirname(os.path.abspath(start_dir))


def family_root(folder):
    """이 폴더가 하위 매크로 폴더면 부모 매크로 폴더를, 아니면 자신을 준다.

    하위 매크로 = macro.json 을 가진 폴더가 macro.json 을 가진 다른 폴더
    안에 중첩된 것. `Macros/Common` 같은 그룹 폴더는 자체 macro.json 이
    없으므로 이 규칙에 걸리지 않는다. 반환값은 절대 경로다.
    """
    folder = os.path.abspath(folder)
    parent = os.path.dirname(folder)
    if (parent != folder
            and os.path.isfile(os.path.join(folder, "macro.json"))
            and os.path.isfile(os.path.join(parent, "macro.json"))):
        return parent
    return folder


def is_sub_macro(macro_path):
    """이 macro.json 이 다른 매크로 폴더 안의 하위 매크로인가."""
    folder = os.path.dirname(os.path.abspath(macro_path))
    return family_root(folder) != folder


def list_sub_macros(folder):
    """매크로 가족의 하위 매크로 목록. [(참조 "./이름", 표시이름, 경로)]

    부모 폴더를 주면 그 하위 매크로들을, 하위 매크로 폴더를 주면
    가족 전체(자기 포함 형제들)를 돌려준다.
    """
    found = []
    if not folder:
        return found
    root = family_root(folder)
    if not os.path.isfile(os.path.join(root, "macro.json")):
        return found
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return found
    for name in names:
        path = os.path.join(root, name, "macro.json")
        if not os.path.isfile(path):
            continue
        data = read_macro_file(path)
        if data is None:
            continue
        found.append(("./" + name, data.get("name") or name, path))
    return found


def resolve_macro_ref(ref, base_dir):
    """호출 참조를 macro.json의 절대 경로로 바꾼다. 못 찾으면 None.

    받아들이는 형태
        "OpenMenu"                 Macros/OpenMenu/macro.json
        "Common/Login"             Macros/Common/Login/macro.json
        "./Sub"                    호출한 매크로 가족의 하위 매크로 (아래 참조)
        "OpenMenu/macro.json"      위와 동일
        "../Other/macro.json"      호출한 매크로 폴더 기준 상대 경로
        "D:/.../macro.json"        절대 경로
    """
    if not ref:
        return None
    ref = ref.replace("\\", "/").strip()

    if ref.startswith("./"):
        # 하위 매크로 참조 - 가족(부모 매크로 폴더) 안에서만 찾는다.
        # 라이브러리에 같은 이름의 매크로가 있어도 여기로는 잡히지 않는다.
        # 일반 참조처럼 Macros 루트 후보를 거치면 "./이름"이 "이름"과 같게
        # 정규화되어 라이브러리가 하위 매크로를 가리는 사고가 난다.
        name = ref[2:].strip("/")
        if not name or "/" in name or name == "..":
            return None
        path = os.path.normpath(os.path.join(family_root(base_dir),
                                             name, "macro.json"))
        return path if os.path.isfile(path) else None

    candidates = []
    if os.path.isabs(ref):
        candidates.append(ref)
        candidates.append(os.path.join(ref, "macro.json"))
    else:
        root = find_macros_root(base_dir)
        candidates.append(os.path.join(root, ref, "macro.json"))
        candidates.append(os.path.join(root, ref))
        candidates.append(os.path.join(base_dir, ref, "macro.json"))
        candidates.append(os.path.join(base_dir, ref))

    for candidate in candidates:
        path = os.path.normpath(candidate)
        if os.path.isfile(path):
            return path
    return None


def read_macro_file(path):
    """매크로 파일이면 내용을 반환, 아니면 None.

    Macros 폴더에는 매크로가 아닌 json이 섞일 수 있으므로 형식을 확인한다.
    """
    import json
    try:
        handle = open(path, "rb")
        try:
            data = json.loads(handle.read().decode("utf-8"))
        finally:
            handle.close()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if "nodes" not in data and "steps" not in data:
        return None
    return data


def is_standalone_ref(ref):
    """폴더가 아니라 파일 하나로 된 매크로인가."""
    return bool(ref) and ref.lower().endswith(".json")


def list_macros(macros_root, include_subs=False):
    """Macros 폴더 아래의 매크로 목록. [(참조이름, 표시이름, 경로)]

    두 가지 형태를 모두 인식한다.

        Macros/이름/macro.json   ->  참조 "이름"        (권장 - 이미지를 같이 둔다)
        Macros/이름.json         ->  참조 "이름.json"   (이미지 없는 매크로용)

    폴더형을 권장하는 이유는 이미지가 매크로 파일 옆에서 찾아지기 때문이다.
    파일 하나로 두면 이미지 기준 폴더가 Macros 루트가 되어 뒤섞이기 쉽다.

    매크로 폴더 안에 중첩된 매크로(하위 매크로)는 그 부모의 사유물이라
    라이브러리 목록에 넣지 않는다. `include_subs=True` 는 참조 갱신이나
    이미지 사용처 검색처럼 **모든** 매크로 파일을 훑어야 할 때 쓴다.
    """
    found = []
    if not os.path.isdir(macros_root):
        return found
    for dirpath, dirnames, filenames in os.walk(macros_root):
        is_macro_folder = any(f.lower() == "macro.json" for f in filenames)
        if is_macro_folder and not include_subs \
                and os.path.normcase(os.path.abspath(dirpath)) \
                != os.path.normcase(os.path.abspath(macros_root)):
            # 매크로 폴더 아래로는 내려가지 않는다 - 이미지와 하위 매크로는
            # 그 매크로의 사유물이다. (Macros 루트 자체에 macro.json 이 있는
            # 특수 배치에서는 루트 전체가 잘려나가므로 루트는 예외)
            dirnames[:] = []
        for filename in filenames:
            if not filename.lower().endswith(".json"):
                continue
            path = os.path.join(dirpath, filename)
            data = read_macro_file(path)
            if data is None:
                continue
            if filename.lower() == "macro.json":
                ref = os.path.relpath(dirpath, macros_root).replace("\\", "/")
                if ref == ".":
                    ref = "macro.json"      # Macros 루트에 바로 놓인 경우
            else:
                ref = os.path.relpath(path, macros_root).replace("\\", "/")
            found.append((ref, data.get("name") or ref, path))
    found.sort()
    return found


def call_targets(nodes):
    """이 노드 목록이 호출하는 매크로 참조들."""
    return [n.get("macro") for n in nodes
            if n.get("type") == "call" and n.get("macro")]


def find_call_cycle(ref, base_dir, seen=None):
    """호출 사슬에 순환이 있으면 그 경로를 반환. 없으면 None.

    A -> B -> A 처럼 서로 부르는 구성을 작성 시점에 잡는다.
    """
    import json
    if seen is None:
        seen = []
    path = resolve_macro_ref(ref, base_dir)
    if path is None:
        return None
    key = os.path.normcase(path)
    if key in seen:
        return seen[seen.index(key):] + [key]
    seen = seen + [key]
    try:
        handle = open(path, "rb")
        try:
            data = json.loads(handle.read().decode("utf-8"))
        finally:
            handle.close()
    except Exception:
        return None
    nodes = data.get("nodes") or []
    folder = os.path.dirname(path)
    for target in call_targets(nodes):
        cycle = find_call_cycle(target, folder, seen)
        if cycle:
            return cycle
    return None


# ------------------------------------------------------- 감시 매크로 (handlers)
#
# 메인 흐름이 도는 동안 예상하지 못한 팝업 등을 처리하는 매크로.
#
#     감시 매크로 (macro.json 최상위)
#       "watch": {"type": "imageExists", "image": "popup.png", "region": [...]}
#     감시를 거는 쪽 (부모든 하위든 같은 자리)
#       "handlers": ["시스템팝업닫기", "./보상창닫기"]
#
# 감시 목록은 호출 단계마다 쌓였다가 그 매크로가 끝나면 걷힌다. 최상위
# 매크로의 목록이 실행 내내 걸리는 '전역' 감시이고, 하위/호출 매크로의 목록은
# 그 매크로가 도는 동안만 뒤에 붙는다. 확인은 바깥 -> 안쪽 순서다.
#
# `handlers` 를 settings 가 아니라 최상위에 두는 이유: 하위 매크로는 자기
# settings 를 갖지 않고 부모 것을 상속한다. settings 에 두면 하위 매크로가
# 자기 감시 목록을 가질 수 없다.
#
# 감시는 별도 스레드가 아니라 메인 흐름이 **틈틈이** 확인한다 (노드 사이,
# 대기 노드 안). 입력 장치가 하나뿐이라 동시에 돌리면 입력이 섞이기 때문이다.

# 한 바퀴 확인을 마친 뒤 다음 바퀴까지의 최소 간격(초). 최상위 매크로 설정
# `handlerInterval` 하나만 쓴다.
DEFAULT_HANDLER_INTERVAL = 1.0

# 메인이 한 노드도 나아가지 못하는 동안 같은 감시가 이만큼 연달아 걸리면
# 닫기가 먹지 않는 것으로 보고 실행을 멈춘다.
HANDLER_REPEAT_LIMIT = 5

# 일시정지 로그 표식. 엔진이 찍고 편집기가 읽어서 "정말 멈췄다"를 안다 -
# 요청한 순간에는 아직 도는 노드가 있어서 멈춘 것이 아니다.
PAUSED_MARK = u"[일시정지]"
RESUMED_MARK = u"[재개]"


def watch_condition(macro):
    """감시 매크로의 감시 조건. 감시 매크로가 아니면 None."""
    cond = macro.get("watch") if isinstance(macro, dict) else None
    return cond if isinstance(cond, dict) else None


def is_watch_macro(macro):
    return watch_condition(macro) is not None


def handler_refs(macro):
    """이 매크로가 거는 감시 매크로 참조 목록. 없으면 빈 목록."""
    refs = macro.get("handlers") if isinstance(macro, dict) else None
    if not isinstance(refs, list):
        return []
    return [r for r in refs if isinstance(r, _TEXT_TYPES) and r.strip()]


def handler_interval(macro):
    """감시 확인 간격(초). 설정이 없거나 잘못됐으면 기본값."""
    settings = macro.get("settings") if isinstance(macro, dict) else None
    try:
        value = float((settings or {}).get("handlerInterval",
                                           DEFAULT_HANDLER_INTERVAL))
    except (TypeError, ValueError):
        return DEFAULT_HANDLER_INTERVAL
    return value if value >= 0 else DEFAULT_HANDLER_INTERVAL


def validate_handler_decl(macro, cautions=None):
    """감시 관련 선언 자체(파일을 열지 않고 볼 수 있는 것)를 검사한다."""
    problems = []
    raw = macro.get("handlers")
    if raw is not None:
        if not isinstance(raw, list):
            problems.append(u"감시 매크로 목록(handlers)은 목록이어야 합니다: %r"
                            % (raw,))
        else:
            seen = set()
            for ref in raw:
                if not isinstance(ref, _TEXT_TYPES) or not ref.strip():
                    problems.append(u"감시 매크로 목록에 빈 칸이 있습니다: %r"
                                    % (ref,))
                    continue
                if ref in seen and cautions is not None:
                    cautions.append(u"감시 매크로 '%s' 가 목록에 두 번 있습니다. "
                                    u"한 번만 확인합니다" % ref)
                seen.add(ref)

    settings = macro.get("settings") or {}
    if "handlerInterval" in settings:
        try:
            if float(settings["handlerInterval"]) < 0:
                raise ValueError()
        except (TypeError, ValueError):
            problems.append(u"감시 확인 간격(handlerInterval)은 0 이상의 "
                            u"숫자여야 합니다: %r" % (settings["handlerInterval"],))

    if "watch" in macro:
        problems.extend(validate_watch(macro, cautions))
    return problems


def validate_watch(macro, cautions=None):
    """감시 조건을 검사한다."""
    cond = macro.get("watch")
    if not isinstance(cond, dict) or not cond.get("type"):
        return [u"감시 조건(watch)이 비어 있습니다"]
    problems = []
    for sub in _conditions_in(cond):
        ctype = sub.get("type")
        if ctype not in CONDITION_TYPES:
            problems.append(u"감시 조건의 종류가 잘못됐습니다 (%r)" % (ctype,))
        elif ctype == "paramCompare":
            # 감시는 호출 노드 없이 엔진이 직접 확인한다. 값을 넘겨줄 쪽이
            # 없으니 매개변수 비교는 늘 기본값끼리 비교하게 된다.
            problems.append(u"감시 조건에는 매개변수 비교를 쓸 수 없습니다")
        elif ctype in ("imageExists", "imageMissing") and not sub.get("image"):
            problems.append(u"감시 조건에 이미지가 필요합니다")
        elif ctype in ("textExists", "textMissing") and not sub.get("text"):
            problems.append(u"감시 조건에 찾을 글자가 필요합니다")
        if (ctype in ("imageExists", "imageMissing", "textExists",
                      "textMissing")
                and not sub.get("region") and cautions is not None):
            cautions.append(u"감시 조건에 영역(region)이 없습니다. 확인할 때마다 "
                            u"화면 전체를 훑어 메인 흐름이 그만큼 느려집니다")
    return problems


def check_handler_refs(macro, base_dir, macro_path=None):
    """감시 매크로 참조를 실제 파일과 대조한다. (오류, 경고) 를 반환.

    호출 참조와 같은 규칙을 따른다 - 하위 매크로는 같은 가족 안에서만
    쓸 수 있다. 판정은 참조 표기가 아니라 파일 위치로 한다.
    """
    errors = []
    warnings = []
    own = os.path.normcase(os.path.abspath(macro_path)) if macro_path else None
    family = os.path.normcase(family_root(base_dir))
    for ref in handler_refs(macro):
        path = resolve_macro_ref(ref, base_dir)
        if path is None:
            errors.append(u"감시 매크로를 찾을 수 없습니다: %s" % ref)
            continue
        if own and os.path.normcase(os.path.abspath(path)) == own:
            errors.append(u"자기 자신을 감시 매크로로 걸 수 없습니다: %s" % ref)
            continue
        folder = os.path.dirname(os.path.abspath(path))
        owner = family_root(folder)
        if owner != folder and os.path.normcase(owner) != family:
            errors.append(u"'%s' 는 다른 매크로의 하위 매크로입니다. 하위 "
                          u"매크로는 같은 가족 안에서만 감시로 쓸 수 있습니다"
                          % ref)
            continue
        data = read_macro_file(path)
        if data is None:
            errors.append(u"감시 매크로를 읽지 못했습니다: %s" % ref)
            continue
        if not is_watch_macro(data):
            errors.append(u"'%s' 에는 감시 조건(watch)이 없습니다. 감시 매크로로 "
                          u"쓰려면 그 매크로의 설정에서 감시 조건을 정하세요"
                          % ref)
            continue
        for problem in validate_watch(data):
            errors.append(u"감시 매크로 '%s': %s" % (ref, problem))
        if handler_refs(data):
            warnings.append(u"감시 매크로 '%s' 가 가진 감시 목록은 쓰이지 "
                            u"않습니다 (감시를 처리하는 동안에는 감시하지 "
                            u"않습니다)" % ref)
    return errors, warnings


# ------------------------------------------------------- 해상도 대응 (scaling)
#
# 매크로의 좌표와 이미지는 **기준 환경**에서 만든 값이고 그대로 저장한다.
# 다른 해상도에서는 실행할 때 변환하고, 그 환경에서 찍은 값은 저장할 때 기준
# 값으로 되돌린다. 해상도별 사본을 두면 수정할 때마다 갈라지기 때문이다.
#
#     최상위 매크로 settings
#       "scaling": {
#         "window": {"class": "UnityWndClass", "title": "마비노기 모바일"},
#         "client": [1, 30, 1364, 1072],     기준 창의 안쪽 (OculiX 좌표)
#         "screen": [2048, 1152]             기준 주 모니터 (OculiX 좌표)
#       }
#
# 배율의 기준은 모니터가 아니라 **창의 안쪽**이다. 게임은 창 크기에 맞춰 그리고,
# OculiX 좌표는 Windows 배율이 적용된 논리 좌표라서, 모니터 해상도만으로는
# 배율이 나오지 않는다 (2560x1440 @125% -> 1920x1080 @100% 는 0.75 가 아니라 0.93).
#
# 좌표 공간은 두 가지다. 게임 창과 달리 실행기, 작업 표시줄, UAC 는 Windows
# 배율로 크기가 정해져서 논리 크기가 해상도와 상관없이 같다.
#     window   창 안쪽 기준으로 변환하고 이미지도 줄인다 (기본)
#     screen   화면 크기에 비례해 자리만 옮기고 이미지는 그대로 쓴다
#
# `space` 를 settings 가 아니라 최상위에 두는 이유는 `handlers` 와 같다 -
# 하위 매크로는 자기 settings 를 갖지 않는다.

SPACE_WINDOW = "window"
SPACE_SCREEN = "screen"
SPACES = (SPACE_WINDOW, SPACE_SCREEN)

# 반올림 차이. 엔진은 물리값을 배율로 나눠서 1364.0x1072.8 을 얻고 편집기는
# 1364x1072 를 얻는다. 기준 환경에서 이 차이로 무엇이든 달라지면 안 된다.
ROUNDING_SLACK = 2

# 이 값 이하로 다르면 같은 창이다. 좌표를 보정하지 않고 축소본도 만들지 않는다.
# 게임은 시작할 때의 DPI 로 제목 표시줄을 그려서, 배율을 바꾼 뒤 다시 띄우지
# 않으면 안쪽이 (1.6,36) 1362x1066 이나 (0.8,24.8) 1364x1078 이 된다 (실측 최대 6).
# 이 차이를 배율로 치면 204x35 가 203x35 가 되는데 줄일 이유가 없는 크기다.
SAME_RECT_SLACK = 8

# 변환할 때 검색 영역을 사방으로 넓히는 값(px). 창의 가로세로비가 살짝 달라지면
# UI 가 최대 1.8px 어긋났다 (1364x1072 -> 1278x1000 실측).
REGION_PAD = 4

# 가로세로비가 이 비율 넘게 달라지면 경고한다. 그만큼 UI 배치가 비례를 벗어난다.
ASPECT_WARN = 0.02

# 그 화면 크기에서 다시 찍은 이미지를 두는 폴더의 접두사 (`@1920x1080`).
# 화면 크기로 짓는 이유: 실행기 단계에는 게임 창이 아직 없다.
CAPTURE_PREFIX = "@"
CAPTURE_INFO = "capture.json"

# 엔진이 만든 축소본. 지워도 다시 만든다.
SCALED_FOLDER = ".scaled"


def _rounded(value):
    """반올림. 파이썬 3 의 round() 는 짝수 쪽으로 가서 2.7 과 값이 다르다.

    편집기와 엔진이 같은 값을 내야 하므로 직접 한다.
    """
    return int(math.floor(float(value) + 0.5))


def same_size(a, b, slack=SAME_RECT_SLACK):
    """두 크기 (w, h) 가 사실상 같은가."""
    return (abs(float(a[0]) - float(b[0])) <= slack
            and abs(float(a[1]) - float(b[1])) <= slack)


class Transform(object):
    """기준 사각형에서 현재 사각형으로 좌표와 크기를 옮긴다.

    `scales_content` 는 사각형 안의 내용물(이미지, 오프셋)도 함께 줄어드는가다.
    게임 창은 그렇고, 화면(실행기, 작업 표시줄)은 자리만 옮겨 간다.

    두 사각형이 사실상 같으면 `identity` 이고 값을 그대로 돌려준다.
    다만 반올림보다 크게 다르면 검색 영역은 그만큼 넓힌다. 내용물이 실제로
    밀려 있어서, 영역을 그대로 두면 빠듯한 노드의 대상이 영역 밖으로 나간다
    (`Check_DD_VeryHard_Selected` 가 1362x1066 에서 4.1px 나간다).
    크기만 같고 위치가 다르면 `resized` 가 거짓이고 좌표만 옮긴다.
    """

    def __init__(self, reference, current, scales_content=True):
        self.reference = [float(v) for v in reference]
        self.current = [float(v) for v in current]
        self.rx, self.ry, self.rw, self.rh = self.reference
        self.cx, self.cy, self.cw, self.ch = self.current
        # 크기가 사실상 같으면 배율은 정확히 1 이다. 스냅으로 옮겨 가는 창을
        # 재면 1364x1072.8 이 나오는데, 이것을 1.0007 배로 치면 같은 크기의
        # 축소본이 생긴다 (실제 실행에서 637x483 -> 637x483 이 만들어졌다).
        self.resized = not same_size(self.reference[2:], self.current[2:])
        self.sx = self.cw / self.rw if self.resized else 1.0
        self.sy = self.ch / self.rh if self.resized else 1.0
        # 게임 UI 는 가로와 세로의 기하평균으로 줄어든다. 가로세로비가 조금
        # 다른 창에서 실측한 UI 배율 0.7475 와 이 값 0.7476 이 일치했다.
        self.scale = math.sqrt(self.sx * self.sy)
        self.scales_content = scales_content
        self.drift = max(abs(a - b)
                         for a, b in zip(self.reference, self.current))
        self.identity = self.drift <= SAME_RECT_SLACK

    def _x(self, x):
        return self.cx + (float(x) - self.rx) * self.sx

    def _y(self, y):
        return self.cy + (float(y) - self.ry) * self.sy

    def point(self, point):
        """기준 좌표 -> 현재 좌표."""
        if self.identity:
            return [int(point[0]), int(point[1])]
        return [_rounded(self._x(point[0])), _rounded(self._y(point[1]))]

    def inverse_point(self, point):
        """현재 좌표 -> 기준 좌표. 편집기가 찍은 값을 저장할 때 쓴다."""
        if self.identity:
            return [int(point[0]), int(point[1])]
        return [_rounded(self.rx + (float(point[0]) - self.cx) / self.sx),
                _rounded(self.ry + (float(point[1]) - self.cy) / self.sy)]

    def region(self, region, bounds=None):
        """기준 영역 -> 현재 영역. `bounds` [x, y, w, h] 안으로 자른다.

        안쪽으로 줄어들지 않게 바깥쪽으로 올림하고 사방으로 넓힌다.
        영역이 템플릿보다 작아지면 대상이 있어도 찾지 못한다.
        """
        x, y, w, h = [float(v) for v in region]
        if self.identity:
            if self.drift <= ROUNDING_SLACK:
                return [int(x), int(y), int(w), int(h)]
            pad = int(math.ceil(self.drift))
            left = int(x) - pad
            top = int(y) - pad
            right = int(x + w) + pad
            bottom = int(y + h) + pad
        else:
            left = int(math.floor(self._x(x))) - REGION_PAD
            top = int(math.floor(self._y(y))) - REGION_PAD
            right = int(math.ceil(self._x(x + w))) + REGION_PAD
            bottom = int(math.ceil(self._y(y + h))) + REGION_PAD
        if bounds:
            bx, by, bw, bh = [int(v) for v in bounds]
            left = max(left, bx)
            top = max(top, by)
            right = min(right, bx + bw)
            bottom = min(bottom, by + bh)
        return [left, top, max(1, right - left), max(1, bottom - top)]

    def inverse_region(self, region):
        """현재 영역 -> 기준 영역. 편집기가 찍은 값을 저장할 때 쓴다."""
        x, y, w, h = [float(v) for v in region]
        left, top = self.inverse_point((x, y))
        right, bottom = self.inverse_point((x + w, y + h))
        return [left, top, right - left, bottom - top]

    def offset(self, offset):
        """찾은 자리에서 떨어진 거리. 내용물과 함께 줄어든다."""
        if not self.resized or not self.scales_content:
            return [int(offset[0]), int(offset[1])]
        return [_rounded(float(offset[0]) * self.sx),
                _rounded(float(offset[1]) * self.sy)]

    def image_size(self, width, height):
        """템플릿의 새 크기. **반올림**이어야 한다.

        OculiX 의 Pattern.resize 는 소수점을 버린다. 341x61 을 0.9349 배 하면
        318.8 이 318 이 되어 점수가 0.9104 로 떨어지고, 319 로 반올림하면
        0.9653 이다 (실제 렌더링에서 측정). 폭 1px 이 점수 0.05 를 좌우한다.
        """
        return (max(1, _rounded(float(width) * self.scale)),
                max(1, _rounded(float(height) * self.scale)))

    def aspect_drift(self):
        """가로세로비가 기준에서 벗어난 비율."""
        return abs((self.cw / self.ch) / (self.rw / self.rh) - 1.0)

    def size_key(self):
        """축소본 폴더 이름에 쓰는 현재 크기 (`1278x1000`)."""
        return "%dx%d" % (_rounded(self.cw), _rounded(self.ch))

    def describe(self):
        if not self.resized:
            return u"창 위치만 다릅니다 (%d,%d) -> (%d,%d). 좌표만 옮깁니다" % (
                _rounded(self.rx), _rounded(self.ry),
                _rounded(self.cx), _rounded(self.cy))
        return u"기준 %dx%d -> 현재 %dx%d (가로 %.4f, 세로 %.4f, 이미지 %.4f)" % (
            _rounded(self.rw), _rounded(self.rh), _rounded(self.cw),
            _rounded(self.ch), self.sx, self.sy, self.scale)


def screen_view(spec, size):
    """화면 공간의 변환. 자리만 비례해서 옮긴다."""
    reference = spec["screen"]
    return Transform([0, 0, reference[0], reference[1]],
                     [0, 0, size[0], size[1]], scales_content=False)


def scaling_of(macro):
    """매크로의 해상도 대응 설정. 없으면 None (변환을 전혀 하지 않는다)."""
    settings = macro.get("settings") if isinstance(macro, dict) else None
    spec = (settings or {}).get("scaling")
    return spec if isinstance(spec, dict) else None


def _numbers(value, count):
    """숫자 count 개짜리 목록인가."""
    if not isinstance(value, (list, tuple)) or len(value) != count:
        return False
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return False
    return True


def validate_scaling(macro):
    """해상도 대응 선언을 검사한다. 오류 목록을 반환."""
    problems = []
    if not isinstance(macro, dict):
        return problems
    if macro.get("space") not in (None, "") + SPACES:
        problems.append(u"좌표 기준(space)은 %s 중 하나여야 합니다 (지금 %r)"
                        % (u"/".join(SPACES), macro.get("space")))
    settings = macro.get("settings") or {}
    if "scaling" not in settings:
        return problems
    spec = settings["scaling"]
    if not isinstance(spec, dict):
        problems.append(u"해상도 대응(scaling) 설정의 형식이 잘못됐습니다: %r"
                        % (spec,))
        return problems
    window = spec.get("window")
    if not isinstance(window, dict) or not (window.get("class")
                                            or window.get("title")):
        problems.append(u"해상도 대응: 기준 창의 class 나 title 이 필요합니다")
    client = spec.get("client")
    if not _numbers(client, 4) or client[2] <= 0 or client[3] <= 0:
        problems.append(u"해상도 대응: 기준 창 안쪽(client)은 "
                        u"[x, y, w, h] 여야 합니다: %r" % (client,))
    screen = spec.get("screen")
    if not _numbers(screen, 2) or screen[0] <= 0 or screen[1] <= 0:
        problems.append(u"해상도 대응: 기준 화면(screen)은 [w, h] 여야 합니다: "
                        u"%r" % (screen,))
    return problems


def capture_folder_name(size):
    """그 화면 크기에서 찍은 이미지를 두는 폴더 이름."""
    return "%s%dx%d" % (CAPTURE_PREFIX, int(size[0]), int(size[1]))


def is_image_folder(name):
    """매크로 폴더 안에서 이미지 변종을 담는 폴더 이름인가."""
    return name == SCALED_FOLDER or name.startswith(CAPTURE_PREFIX)


def capture_folders(base_dir):
    """`@...` 폴더의 절대 경로 목록."""
    try:
        names = sorted(os.listdir(base_dir))
    except OSError:
        return []
    return [os.path.join(base_dir, name) for name in names
            if name.startswith(CAPTURE_PREFIX)
            and os.path.isdir(os.path.join(base_dir, name))]


def read_capture_client(folder):
    """이 `@` 폴더의 이미지를 찍을 때의 창 안쪽. 모르면 None."""
    import json
    try:
        handle = open(os.path.join(folder, CAPTURE_INFO), "rb")
        try:
            data = json.loads(handle.read().decode("utf-8"))
        finally:
            handle.close()
    except Exception:
        return None
    client = data.get("client") if isinstance(data, dict) else None
    return client if _numbers(client, 4) else None


def write_capture_info(folder, screen, client=None):
    """`@` 폴더의 안내 파일을 쓴다. 창을 못 쟀으면 아는 값을 지우지 않는다."""
    import json
    if not os.path.isdir(folder):
        os.makedirs(folder)
    if client is None:
        client = read_capture_client(folder)
    data = {"screen": [int(screen[0]), int(screen[1])]}
    if client is not None:
        data["client"] = [float(v) for v in client]
    handle = open(os.path.join(folder, CAPTURE_INFO), "wb")
    try:
        handle.write(json.dumps(data, indent=2).encode("utf-8"))
    finally:
        handle.close()


def locate_image(base_dir, name, screen_size=None):
    """이 이름으로 쓸 이미지 파일을 찾는다. 없으면 None.

    순서
      1. 지금 화면 크기의 `@폴더` - 그 환경에서 찍은 것이 가장 잘 맞는다
      2. 매크로 폴더 바로 아래 - 기준 환경에서 찍은 것
      3. 다른 `@폴더` - 다른 환경에서 새로 찍어 기준 이미지가 없는 경우

    반환 {"path": 경로, "capture": 기준 이미지면 False, "client": 찍을 때의 창}
    """
    if os.path.isabs(name):
        if os.path.isfile(name):
            return {"path": name, "capture": False, "client": None}
        return None
    if screen_size:
        folder = os.path.join(base_dir, capture_folder_name(screen_size))
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return {"path": path, "capture": True,
                    "client": read_capture_client(folder)}
    path = os.path.join(base_dir, name)
    if os.path.isfile(path):
        return {"path": path, "capture": False, "client": None}
    for folder in capture_folders(base_dir):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return {"path": path, "capture": True,
                    "client": read_capture_client(folder)}
    return None


def image_family(base_dir, name):
    """이 이름의 이미지 파일 전부 (기준 + 각 `@폴더`). 있는 것만 준다."""
    found = []
    path = os.path.join(base_dir, name)
    if os.path.isfile(path):
        found.append(path)
    for folder in capture_folders(base_dir):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            found.append(path)
    return found


def base_image_path(path):
    """`@폴더` 안의 이미지면 매크로 폴더 바로 아래의 경로로 바꿔 준다.

    노드는 이미지를 이름으로만 참조한다. 사용처를 찾거나 노드에 지정할 때는
    어느 변종을 골랐든 같은 이미지다.
    """
    folder, name = os.path.split(path)
    if os.path.basename(folder).startswith(CAPTURE_PREFIX):
        return os.path.join(os.path.dirname(folder), name)
    return path


def scaled_image_path(base_dir, name, view):
    """엔진이 만든 축소본의 경로."""
    if os.path.isabs(name):
        name = os.path.basename(name)
    return os.path.join(base_dir, SCALED_FOLDER, view.size_key(), name)


# --------------------------------------------------------------- 파라미터 검증

def validate_node_params(nodes, cautions=None):
    """트리/그래프 공통으로 쓰는 단계 파라미터 검사.

    반환값은 오류 목록이다. `cautions` 에 리스트를 주면 오류는 아니지만
    알아 두면 좋은 것들이 거기에 담긴다.
    """
    problems = []
    for node in nodes:
        ntype = node.get("type")
        where = u"노드 %s(%s)" % (node.get("id", "?"), ntype)
        for spot in [node] + _all_conditions(node):
            if spot.get("space") not in (None, "") + SPACES:
                problems.append(u"%s: 좌표 기준(space)은 %s 중 하나여야 합니다 "
                                u"(지금 %r)" % (where, u"/".join(SPACES),
                                                spot.get("space")))
        if ntype in ("waitImage", "waitVanish") and not node.get("image"):
            problems.append(u"%s: 이미지가 필요합니다" % where)
        if ntype == "waitText" and not node.get("text"):
            problems.append(u"%s: 찾을 글자가 필요합니다" % where)

        # 글자 인식은 영역이 넓을수록 눈에 띄게 부정확해진다. 실측에서 좁은
        # 라벨 영역은 정확히 읽혔지만 창 전체는 공백이 끼고 대부분 누락됐다.
        # 오류는 아니므로 경고로만 알린다.
        # type 노드의 text 는 화면에서 찾을 글자가 아니라 키보드로 칠 내용이다.
        # 화면을 읽는 노드만 대상으로 삼는다.
        reads_text = (
            ntype == "waitText"
            or (ntype in ("click", "doubleClick", "rightClick", "hover")
                and node.get("text") and not node.get("image")))
        if reads_text and not node.get("region") and cautions is not None:
            cautions.append(u"%s: 글자를 찾을 영역(region)이 없습니다. "
                            u"영역을 좁히지 않으면 인식률이 크게 떨어집니다" % where)
        # 대상을 하나도 주지 않으면 커서가 지금 있는 자리에서 그대로 실행된다.
        # 오류는 아니지만 의도한 경우가 드물고, 엉뚱한 창을 누르면 되돌릴 수
        # 없으므로 경고로 알린다.
        if ntype in ("click", "doubleClick", "rightClick", "hover", "wheel"):
            has_target = (node.get("image") or node.get("text")
                          or node.get("point"))
            if not has_target and cautions is not None:
                cautions.append(
                    u"%s: 대상이 없어 현재 커서 위치에서 그대로 실행됩니다. "
                    u"의도한 것이 아니면 이미지나 좌표를 지정하세요" % where)

        # 드래그는 두 지점이 모두 있어야 한다. '현재 커서 위치' 같은 기본값이
        # 성립하지 않으므로 클릭 계열과 달리 오류로 둔다.
        if ntype == "drag":
            for side, side_label in (("from", u"시작"), ("to", u"끝")):
                spot = node.get(side) or {}
                if not (spot.get("image") or spot.get("text")
                        or spot.get("point")):
                    problems.append(
                        u"%s: 드래그 %s 지점에 이미지, 텍스트, 좌표 중 "
                        u"하나가 필요합니다" % (where, side_label))
            for index, point in enumerate(node.get("waypoints") or []):
                if not (isinstance(point, (list, tuple)) and len(point) == 2):
                    problems.append(
                        u"%s: 경유지 %d번이 [x, y] 형식이 아닙니다: %r"
                        % (where, index + 1, point))
        if ntype == "waitColor":
            if not node.get("point"):
                problems.append(u"%s: 좌표가 필요합니다" % where)
            if not node.get("rgb"):
                problems.append(u"%s: 색이 필요합니다" % where)
        if ntype == "call" and not node.get("macro"):
            problems.append(u"%s: 호출할 매크로를 지정해야 합니다" % where)
        if ntype == "run" and not node.get("command"):
            problems.append(u"%s: 실행할 명령을 지정해야 합니다" % where)
    return problems


# --------------------------------------------------------------- 생성 / 변환

def blank(name=u"새 매크로"):
    return {
        "name": name,
        "version": 2,
        "format": FORMAT_GRAPH,
        "settings": {
            "screen": 0,
            "defaultSimilarity": 0.90,
            "defaultTimeout": 10,
            "stepDelay": 0,
            "maxSteps": DEFAULT_MAX_STEPS,
            "maxSeconds": DEFAULT_MAX_SECONDS,
        },
        "entry": None,
        "nodes": [],
        "links": [],
    }


def from_tree(tree_data, x_start=60, y_start=60, dx=260, dy=120):
    """기존 트리 형식 매크로를 그래프로 변환한다.

    중첩 구조가 그대로 실행 링크로 펼쳐지므로 동작은 같다.
    좌표는 대충 배치하고 사용자가 옮기면 된다.
    """
    graph = Graph(blank(tree_data.get("name", u"변환된 매크로")))
    settings = dict(tree_data.get("settings") or {})
    settings.setdefault("maxSteps", DEFAULT_MAX_STEPS)
    settings.setdefault("maxSeconds", DEFAULT_MAX_SECONDS)
    graph.data["settings"] = settings

    counter = [0]
    layout = {"y": y_start}

    def make_node(step, depth):
        counter[0] += 1
        node = {}
        for key, value in step.items():
            if key in ("then", "else", "steps"):
                continue
            node[key] = value
        node["id"] = "n%d" % counter[0]
        node["ui"] = {"x": x_start + depth * dx, "y": layout["y"]}
        layout["y"] += dy
        graph.nodes.append(node)
        return node

    def build(steps, depth):
        """steps 체인을 만들고 (첫 노드 id, 마지막 노드들의 열린 핀 목록) 반환."""
        first = None
        open_pins = []          # [(node_id, pin)] - 다음 노드로 이어야 할 자리
        for step in steps:
            node = make_node(step, depth)
            node_id = node["id"]
            if first is None:
                first = node_id
            for src_id, pin in open_pins:
                graph.links.append({"from": src_id, "pin": pin, "to": node_id})
            open_pins = []

            ntype = step.get("type")
            if ntype == "if":
                then_first, then_open = build(step.get("then") or [], depth + 1)
                else_first, else_open = build(step.get("else") or [], depth + 1)
                if then_first:
                    graph.links.append({"from": node_id, "pin": "true", "to": then_first})
                    open_pins.extend(then_open)
                else:
                    open_pins.append((node_id, "true"))
                if else_first:
                    graph.links.append({"from": node_id, "pin": "false", "to": else_first})
                    open_pins.extend(else_open)
                else:
                    open_pins.append((node_id, "false"))
            elif ntype == "repeat":
                body_first, body_open = build(step.get("steps") or [], depth + 1)
                if body_first:
                    graph.links.append({"from": node_id, "pin": "body", "to": body_first})
                    # 본문 체인의 끝은 그래프에서 열어둔다. 실행기가 루프로 되돌린다.
                    del body_open[:]
                open_pins.append((node_id, "completed"))
            elif ntype == "break":
                pass            # break 뒤로는 이어지지 않는다
            else:
                open_pins.append((node_id, "next"))
        return first, open_pins

    entry, _open = build(tree_data.get("steps") or [], 0)
    graph.entry = entry
    return graph
