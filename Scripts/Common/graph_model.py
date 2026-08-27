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

import os

try:                        # Jython 2.7 / CPython 3 양쪽에서 문자열을 가린다
    _TEXT_TYPES = (str, unicode)
except NameError:
    _TEXT_TYPES = (str,)

FORMAT_GRAPH = "graph"
FORMAT_TREE = "tree"

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
