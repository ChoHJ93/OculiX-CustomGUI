# -*- coding: utf-8 -*-
"""단계/조건 정의표.

편집기 UI는 이 표를 읽어서 입력 폼을 자동 생성한다.
새 단계 종류를 추가하려면 여기에 항목 하나만 넣으면 되고 UI 코드는 건드리지 않는다.
엔진(Scripts/Common/macro_engine.py)이 실제로 지원하는 것만 등록되어 있다.

field type
    str text int float bool choice
    image   이미지 파일 (찾아보기 / 화면에서 캡처)
    point   [x, y]     (화면에서 좌표 찍기)
    rgb     [r, g, b]  (화면에서 색 찍기)
    region  [x, y, w, h] (화면에서 영역 드래그)
    tolerance  int 또는 [r, g, b]
    condition  중첩 조건
    target     {image|point} 형태의 대상
"""

from collections import OrderedDict


# 모든 단계에 공통으로 붙는 필드
COMMON_FIELDS = [
    {"name": "label", "type": "str", "label": u"이름",
     "help": u"로그에 표시할 이름. 비우면 단계 종류가 표시된다"},
    {"name": "enabled", "type": "bool", "label": u"사용", "default": True,
     "help": u"끄면 실행 시 건너뛴다"},
    {"name": "onFail", "type": "choice", "label": u"실패 시",
     "options": [("", u"매크로 중단 (기본)"), ("continue", u"무시하고 계속")],
     "help": u"노드의 빨간 '실패' 핀에 다른 노드를 연결하면 그쪽이 우선한다. "
             u"이 설정은 실패 핀을 연결하지 않았을 때만 쓰인다. "
             u"무시하고 계속하면 엉뚱한 곳을 클릭할 수 있으니 신중히"},
]

_IMAGE_SEARCH_FIELDS = [
    {"name": "image", "type": "image", "label": u"이미지"},
    {"name": "similarity", "type": "float", "label": u"정확도",
     "help": u"비우면 매크로 기본값. 0.90에서 시작해 실제 점수를 보고 조정"},
    {"name": "timeout", "type": "float", "label": u"제한시간(초)",
     "help": u"비우면 매크로 기본값"},
    {"name": "region", "type": "region", "label": u"검색 영역",
     "help": u"좁힐수록 빠르고 오탐이 적다. 비우면 전체 화면"},
]

_CLICK_FIELDS = [
    {"name": "image", "type": "image", "label": u"이미지",
     "help": u"이미지를 찾아서 그 위치를 클릭. 좌표 대신 이쪽을 권장"},
    {"name": "text", "type": "str", "label": u"텍스트",
     "help": u"화면 글자를 읽어(OCR) 찾아 그 중앙을 클릭한다. 이미지가 비어 있을 때만 "
             u"쓰인다. 대소문자와 공백을 무시한 부분 일치다. "
             u"**검색 영역을 좁혀야 정확하다** - 넓으면 글자를 통째로 놓친다"},
    {"name": "ocrLanguage", "type": "choice", "label": u"인식 언어",
     "options": [("", u"매크로 기본값"), ("eng", u"영어 eng"),
                 ("kor", u"한국어 kor"), ("chi_sim", u"중국어 간체 chi_sim"),
                 ("fra", u"프랑스어 fra"), ("hin", u"힌디어 hin"),
                 ("spa", u"스페인어 spa")],
     "help": u"화면 글자를 읽어 찾는다. 한 번에 한 언어만 인식된다 (kor 로는 영문이, eng 로는 한글이 깨진다). 비우면 매크로 설정값"},
    {"name": "point", "type": "point", "label": u"좌표",
     "help": u"이미지·텍스트 대신 절대 좌표를 클릭할 때. "
             u"셋 다 비우면 커서가 지금 있는 자리에서 그대로 실행된다 "
             u"(mouseDown/mouseUp 과 같은 단순 입력)"},
    {"name": "targetOffset", "type": "point", "label": u"오프셋",
     "help": u"찾은 지점에서 떨어진 곳을 누를 때 (예: 레이블 찾고 아래 버튼 클릭)"},
    {"name": "similarity", "type": "float", "label": u"정확도"},
    {"name": "timeout", "type": "float", "label": u"제한시간(초)"},
    {"name": "region", "type": "region", "label": u"검색 영역"},
]


STEP_TYPES = OrderedDict([

    # --- 기본 ---
    ("log", {
        "label": u"로그 출력",
        "group": u"기본",
        "fields": [
            {"name": "message", "type": "str", "label": u"메시지"},
        ],
    }),
    ("wait", {
        "label": u"대기 (고정 시간)",
        "group": u"기본",
        "fields": [
            {"name": "seconds", "type": "float", "label": u"초", "default": 1.0},
        ],
    }),

    ("run", {
        "label": u"프로그램 실행",
        "group": u"기본",
        "fields": [
            {"name": "command", "type": "str", "label": u"명령",
             "help": u"실행할 프로그램이나 문서. "
                     u"예: virtmgmt.msc / notepad.exe / D:/Tools/app.exe / "
                     u"https://example.com"},
            {"name": "args", "type": "args", "label": u"인자",
             "help": u"공백으로 구분. 공백이 든 인자는 \"큰따옴표\" 로 묶는다"},
            {"name": "useShell", "type": "bool", "label": u"연결 프로그램으로 열기",
             "default": True,
             "help": u".msc .lnk 문서 URL 은 이 방식이어야 열린다. "
                     u"끄면 실행 파일을 직접 실행하고 종료를 기다릴 수 있다"},
            {"name": "waitForExit", "type": "bool", "label": u"끝날 때까지 대기",
             "default": False,
             "help": u"'연결 프로그램으로 열기'를 끈 경우에만 의미가 있다. "
                     u"종료 코드가 0이 아니면 실패로 본다"},
            {"name": "timeout", "type": "float", "label": u"대기 제한(초)",
             "help": u"끝날 때까지 대기할 때만 쓰인다. 비우면 30초"},
            {"name": "workingDir", "type": "str", "label": u"작업 폴더"},
        ],
    }),

    # --- 화면 대기 ---
    ("waitImage", {
        "label": u"이미지 나타날 때까지 대기",
        "group": u"화면",
        "fields": _IMAGE_SEARCH_FIELDS,
    }),
    ("waitVanish", {
        "label": u"이미지 사라질 때까지 대기",
        "group": u"화면",
        "fields": _IMAGE_SEARCH_FIELDS,
    }),
    ("waitText", {
        "label": u"텍스트 나타날 때까지 대기",
        "group": u"화면",
        "fields": [
            {"name": "text", "type": "str", "label": u"찾을 글자",
             "help": u"대소문자와 공백을 무시한 부분 일치로 찾는다"},
            {"name": "ocrLanguage", "type": "choice", "label": u"인식 언어",
             "options": [("", u"매크로 기본값"), ("eng", u"영어 eng"),
                         ("kor", u"한국어 kor"), ("chi_sim", u"중국어 간체 chi_sim"),
                         ("fra", u"프랑스어 fra"), ("hin", u"힌디어 hin"),
                         ("spa", u"스페인어 spa")],
             "help": u"화면 글자를 읽어 찾는다. 한 번에 한 언어만 인식된다 (kor 로는 영문이, eng 로는 한글이 깨진다). 비우면 매크로 설정값"},
            {"name": "timeout", "type": "float", "label": u"제한시간(초)"},
            {"name": "region", "type": "region", "label": u"검색 영역",
             "help": u"**좁힐수록 정확하다.** 화면 전체를 읽으면 글자를 놓치거나 "
                     u"없는 공백이 끼어든다"},
        ],
    }),
    ("waitColor", {
        "label": u"픽셀 색 바뀔 때까지 대기",
        "group": u"화면",
        "fields": [
            {"name": "point", "type": "point", "label": u"좌표"},
            {"name": "rgb", "type": "rgb", "label": u"목표 색"},
            {"name": "tolerance", "type": "tolerance", "label": u"허용 오차",
             "default": 10, "help": u"채널별 차이. [10,5,20]처럼 채널마다 다르게도 가능"},
            {"name": "timeout", "type": "float", "label": u"제한시간(초)"},
            {"name": "interval", "type": "float", "label": u"검사 간격(초)",
             "default": 0.1},
        ],
    }),

    # --- 마우스 ---
    ("click", {"label": u"클릭", "group": u"마우스", "fields": _CLICK_FIELDS}),
    ("doubleClick", {"label": u"더블클릭", "group": u"마우스", "fields": _CLICK_FIELDS}),
    ("rightClick", {"label": u"우클릭", "group": u"마우스", "fields": _CLICK_FIELDS}),
    ("hover", {"label": u"마우스 올리기", "group": u"마우스", "fields": _CLICK_FIELDS}),
    ("mouseDown", {
        "label": u"마우스 버튼 누르기",
        "group": u"마우스",
        "fields": [
            {"name": "button", "type": "choice", "label": u"버튼", "default": "LEFT",
             "options": [("LEFT", u"왼쪽"), ("MIDDLE", u"가운데"), ("RIGHT", u"오른쪽")]},
        ],
    }),
    ("mouseUp", {
        "label": u"마우스 버튼 떼기",
        "group": u"마우스",
        "fields": [
            {"name": "button", "type": "choice", "label": u"버튼", "default": "LEFT",
             "options": [("LEFT", u"왼쪽"), ("MIDDLE", u"가운데"), ("RIGHT", u"오른쪽")]},
        ],
    }),
    ("drag", {
        "label": u"드래그",
        "group": u"마우스",
        "fields": [
            {"name": "from", "type": "target", "label": u"시작"},
            {"name": "to", "type": "target", "label": u"끝"},
            {"name": "waypoints", "type": "points", "label": u"경유지",
             "help": u"시작과 끝 사이로 지나갈 좌표. 'x,y' 를 세미콜론으로 "
                     u"구분한다 (예: 300,400 ; 500,200). "
                     u"비우면 시작에서 끝으로 곧장 끈다. "
                     u"경유지는 좌표만 쓸 수 있다 - 끄는 도중에는 화면이 "
                     u"바뀌고 있어서 이미지로 찾을 수 없다"},
        ],
    }),
    ("wheel", {
        "label": u"휠 스크롤",
        "group": u"마우스",
        "fields": [
            {"name": "image", "type": "image", "label": u"기준 이미지"},
            {"name": "point", "type": "point", "label": u"기준 좌표",
             "help": u"둘 다 비우면 커서가 지금 있는 자리에서 스크롤한다"},
            {"name": "direction", "type": "choice", "label": u"방향", "default": "down",
             "options": [("down", u"아래로"), ("up", u"위로")]},
            {"name": "amount", "type": "int", "label": u"칸 수", "default": 3},
        ],
    }),

    # --- 키보드 ---
    ("type", {
        "label": u"문자 입력",
        "group": u"키보드",
        "fields": [
            {"name": "text", "type": "text", "label": u"내용"},
            {"name": "usePaste", "type": "bool", "label": u"붙여넣기로 입력",
             "default": False,
             "help": u"한글이나 긴 문자열은 켜는 것이 안정적이다"},
        ],
    }),
    ("key", {
        "label": u"특수키 / 조합키",
        "group": u"키보드",
        "fields": [
            # 하나의 필드가 key 와 modifiers 를 함께 다룬다.
            # 이름을 손으로 타이핑하면 오타가 나기 쉬워서 선택 창으로 처리한다.
            {"name": "key", "type": "keycombo", "label": u"키",
             "help": u"[선택...] 을 눌러 실제 키를 눌러 캡처하거나 목록에서 고른다. "
                     u"조합키도 함께 지정된다"},
        ],
    }),

    # --- 흐름 제어 ---
    ("if", {
        "label": u"조건 분기",
        "group": u"흐름",
        "containers": ["then", "else"],
        "container_labels": {"then": u"참일 때", "else": u"거짓일 때"},
        "fields": [
            {"name": "condition", "type": "condition", "label": u"조건"},
        ],
    }),
    ("repeat", {
        "label": u"반복",
        "group": u"흐름",
        "containers": ["steps"],
        "container_labels": {"steps": u"반복 본문"},
        "fields": [
            {"name": "times", "type": "int", "label": u"반복 횟수",
             "help": u"횟수를 정할 때. 아래 '조건'과 함께 쓸 수 없다"},
            {"name": "while", "type": "condition", "label": u"조건이 참인 동안",
             "help": u"횟수 대신 조건으로 반복할 때"},
            {"name": "maxIterations", "type": "int", "label": u"최대 반복",
             "help": u"조건 반복에는 필수. 무한 루프를 형식 차원에서 막는다"},
            {"name": "allowMaxIterations", "type": "bool",
             "label": u"최대 도달을 성공으로 취급", "default": True},
        ],
    }),
    ("break", {
        "label": u"반복 빠져나오기",
        "group": u"흐름",
        "fields": [],
    }),
    ("call", {
        "label": u"매크로 호출",
        "group": u"흐름",
        "fields": [
            {"name": "macro", "type": "macro_ref", "label": u"매크로",
             "help": u"Macros 폴더 기준 이름. 예: OpenMenu 또는 Common/Login. "
                     u"호출된 매크로는 자기 폴더의 이미지와 자기 설정을 쓴다"},
            {"name": "args", "type": "call_args", "label": u"넘길 값",
             "help": u"호출할 매크로가 선언한 매개변수에 넘길 값. "
                     u"칸은 대상 매크로의 선언을 읽어 자동으로 만들어진다"},
        ],
    }),
])


CONDITION_TYPES = OrderedDict([
    ("imageExists", {
        "label": u"이미지가 있으면",
        "fields": [
            {"name": "image", "type": "image", "label": u"이미지"},
            {"name": "similarity", "type": "float", "label": u"정확도"},
            {"name": "timeout", "type": "float", "label": u"제한시간(초)", "default": 3},
            {"name": "region", "type": "region", "label": u"검색 영역"},
        ],
    }),
    ("imageMissing", {
        "label": u"이미지가 없으면",
        "fields": [
            {"name": "image", "type": "image", "label": u"이미지"},
            {"name": "similarity", "type": "float", "label": u"정확도"},
            {"name": "timeout", "type": "float", "label": u"제한시간(초)", "default": 3},
            {"name": "region", "type": "region", "label": u"검색 영역"},
        ],
    }),
    ("textExists", {
        "label": u"글자가 보이면",
        "fields": [
            {"name": "text", "type": "str", "label": u"찾을 글자",
             "help": u"대소문자와 공백을 무시한 부분 일치"},
            {"name": "ocrLanguage", "type": "choice", "label": u"인식 언어",
             "options": [("", u"매크로 기본값"), ("eng", u"영어 eng"),
                         ("kor", u"한국어 kor"), ("chi_sim", u"중국어 간체 chi_sim"),
                         ("fra", u"프랑스어 fra"), ("hin", u"힌디어 hin"),
                         ("spa", u"스페인어 spa")],
             "help": u"화면 글자를 읽어 찾는다. 한 번에 한 언어만 인식된다 (kor 로는 영문이, eng 로는 한글이 깨진다). 비우면 매크로 설정값"},
            {"name": "timeout", "type": "float", "label": u"제한시간(초)", "default": 3},
            {"name": "region", "type": "region", "label": u"검색 영역",
             "help": u"좁힐수록 정확하다"},
        ],
    }),
    ("textMissing", {
        "label": u"글자가 안 보이면",
        "fields": [
            {"name": "text", "type": "str", "label": u"찾을 글자",
             "help": u"대소문자와 공백을 무시한 부분 일치"},
            {"name": "ocrLanguage", "type": "choice", "label": u"인식 언어",
             "options": [("", u"매크로 기본값"), ("eng", u"영어 eng"),
                         ("kor", u"한국어 kor"), ("chi_sim", u"중국어 간체 chi_sim"),
                         ("fra", u"프랑스어 fra"), ("hin", u"힌디어 hin"),
                         ("spa", u"스페인어 spa")],
             "help": u"화면 글자를 읽어 찾는다. 한 번에 한 언어만 인식된다 (kor 로는 영문이, eng 로는 한글이 깨진다). 비우면 매크로 설정값"},
            {"name": "timeout", "type": "float", "label": u"제한시간(초)", "default": 3},
            {"name": "region", "type": "region", "label": u"검색 영역"},
        ],
    }),
    ("colorMatches", {
        "label": u"픽셀 색이 일치하면",
        "fields": [
            {"name": "point", "type": "point", "label": u"좌표"},
            {"name": "rgb", "type": "rgb", "label": u"색"},
            {"name": "tolerance", "type": "tolerance", "label": u"허용 오차", "default": 10},
        ],
    }),
    ("paramCompare", {
        "label": u"매개변수를 비교하면",
        "fields": [
            {"name": "param", "type": "param_name", "label": u"매개변수",
             "help": u"이 매크로가 선언한 매개변수. "
                     u"'매크로 설정'에서 선언한다"},
            {"name": "op", "type": "choice", "label": u"비교",
             "default": "==",
             "options": [("==", u"같으면 =="), ("!=", u"다르면 !="),
                         ("<", u"작으면 <"), ("<=", u"작거나 같으면 <="),
                         (">", u"크면 >"), (">=", u"크거나 같으면 >=")],
             "help": u"문자열에는 == 와 != 만 쓰는 것이 안전하다"},
            {"name": "value", "type": "str", "label": u"비교할 값",
             "help": u"매개변수의 선언 타입으로 바꾼 뒤 비교한다"},
        ],
    }),
    ("not", {
        "label": u"반대 (NOT)",
        "fields": [
            {"name": "condition", "type": "condition", "label": u"대상 조건"},
        ],
    }),
    ("all", {
        "label": u"모두 참 (AND)",
        "fields": [
            {"name": "conditions", "type": "condition_list", "label": u"조건들"},
        ],
    }),
    ("any", {
        "label": u"하나라도 참 (OR)",
        "fields": [
            {"name": "conditions", "type": "condition_list", "label": u"조건들"},
        ],
    }),
])


def step_label(stype):
    spec = STEP_TYPES.get(stype)
    return spec["label"] if spec else stype


def fields_for(stype):
    spec = STEP_TYPES.get(stype)
    if not spec:
        return []
    return spec["fields"]


def containers_for(stype):
    spec = STEP_TYPES.get(stype)
    if not spec:
        return []
    return spec.get("containers", [])


def container_label(stype, key):
    spec = STEP_TYPES.get(stype) or {}
    return (spec.get("container_labels") or {}).get(key, key)


def grouped_types():
    """추가 메뉴용: {그룹: [(type, label), ...]}"""
    groups = OrderedDict()
    for stype, spec in STEP_TYPES.items():
        groups.setdefault(spec.get("group", u"기타"), []).append(
            (stype, spec["label"]))
    return groups


def new_step(stype):
    """기본값이 채워진 새 단계 dict를 만든다."""
    step = {"type": stype}
    for field in fields_for(stype):
        if "default" in field:
            step[field["name"]] = field["default"]
    for key in containers_for(stype):
        step[key] = []
    if stype == "repeat":
        # 기본은 횟수 반복. while은 사용자가 골라 넣는다.
        step.pop("allowMaxIterations", None)
        step["times"] = 1
    if stype == "if":
        step["condition"] = new_condition("imageExists")
    return step


def new_condition(ctype):
    cond = {"type": ctype}
    spec = CONDITION_TYPES.get(ctype) or {}
    for field in spec.get("fields", []):
        if "default" in field:
            cond[field["name"]] = field["default"]
    if ctype in ("all", "any"):
        cond["conditions"] = []
    if ctype == "not":
        cond["condition"] = {"type": "imageExists"}
    return cond


def condition_images(cond):
    """조건 하나가 참조하는 이미지 이름들. all/any/not 안쪽까지 훑는다."""
    out = []
    if not isinstance(cond, dict):
        return out
    if cond.get("image"):
        out.append(cond["image"])
    if isinstance(cond.get("condition"), dict):
        out.extend(condition_images(cond["condition"]))
    for sub in cond.get("conditions") or []:
        out.extend(condition_images(sub))
    return out


def image_params(step):
    """단계/노드가 참조하는 이미지 전부. [(라벨, 파일이름), ...]

    한 노드가 이미지를 여럿 쓸 수 있다 - 드래그의 시작/끝, 조건 안의 이미지.
    노드에 그림을 그리는 쪽과 누락 파일을 찾는 쪽이 같은 목록을 봐야 하므로
    정의를 여기 한 곳에만 둔다.
    """
    out = []
    if step.get("image"):
        out.append((u"이미지", step["image"]))
    for key, label in (("from", u"시작"), ("to", u"끝")):
        sub = step.get(key)
        if isinstance(sub, dict) and sub.get("image"):
            out.append((label, sub["image"]))
    for key in ("condition", "while"):
        for name in condition_images(step.get(key)):
            out.append((u"조건", name))
    return out


def rewrite_condition_images(cond, mapping):
    """조건 안의 이미지 이름을 바꾼다. `condition_images` 와 짝이다."""
    if not isinstance(cond, dict):
        return
    name = cond.get("image")
    if name and name in mapping:
        cond["image"] = mapping[name]
    if isinstance(cond.get("condition"), dict):
        rewrite_condition_images(cond["condition"], mapping)
    for sub in cond.get("conditions") or []:
        rewrite_condition_images(sub, mapping)


def rewrite_images(step, mapping):
    """단계/노드의 이미지 이름을 {옛 이름: 새 이름} 으로 갈아 끼운다.

    `image_params` 가 훑는 자리를 그대로 훑는다. 한쪽만 고치면 다른 매크로로
    복사할 때 그림을 못 찾는 노드가 생기므로 두 함수를 나란히 둔다.
    """
    if not mapping:
        return
    if step.get("image") in mapping:
        step["image"] = mapping[step["image"]]
    for key in ("from", "to"):
        sub = step.get(key)
        if isinstance(sub, dict) and sub.get("image") in mapping:
            sub["image"] = mapping[sub["image"]]
    for key in ("condition", "while"):
        rewrite_condition_images(step.get(key), mapping)


def summarize(step):
    """트리에 한 줄로 표시할 요약 문자열."""
    stype = step.get("type", u"?")
    label = step.get("label")
    base = label if label else step_label(stype)

    detail = u""
    if stype == "log":
        detail = step.get("message", u"")
    elif stype == "wait":
        detail = u"%s초" % step.get("seconds", "")
    elif stype in ("waitImage", "waitVanish"):
        detail = step.get("image", u"")
    elif stype == "waitText":
        detail = u'"%s"' % (step.get("text") or u"")
    elif stype in ("click", "doubleClick", "rightClick", "hover"):
        if step.get("image"):
            detail = step["image"]
        elif step.get("text"):
            detail = u'글자 "%s"' % step["text"]
        elif step.get("point"):
            detail = u"(%s, %s)" % tuple(step["point"])
    elif stype == "waitColor":
        detail = u"%s -> %s" % (step.get("point"), step.get("rgb"))
    elif stype == "type":
        detail = (step.get("text") or u"")[:30]
    elif stype == "key":
        parts = list(step.get("modifiers") or [])
        if step.get("key"):
            parts.append(step["key"])
        detail = u" + ".join(parts)
    elif stype == "if":
        detail = describe_condition(step.get("condition"))
    elif stype == "repeat":
        if "times" in step:
            detail = u"%s회" % step.get("times")
        elif "while" in step:
            detail = u"while %s (최대 %s)" % (
                describe_condition(step.get("while")), step.get("maxIterations"))
    elif stype == "call":
        detail = step.get("macro") or u"(매크로 미지정)"
    elif stype == "run":
        detail = step.get("command") or u"(명령 미지정)"
        if step.get("args"):
            detail += u" " + (step["args"] if isinstance(step["args"], str)
                              else u" ".join(step["args"]))

    if detail:
        return u"%s  —  %s" % (base, detail)
    return base


def describe_condition(cond):
    if not isinstance(cond, dict):
        return u"(조건 없음)"
    ctype = cond.get("type")
    if ctype in ("imageExists", "imageMissing"):
        name = u"있으면" if ctype == "imageExists" else u"없으면"
        return u"%s %s" % (cond.get("image") or u"(이미지 미지정)", name)
    if ctype in ("textExists", "textMissing"):
        word = u"보이면" if ctype == "textExists" else u"안 보이면"
        return u'글자 "%s" %s' % (cond.get("text") or u"", word)
    if ctype == "colorMatches":
        return u"색 %s @ %s" % (cond.get("rgb"), cond.get("point"))
    if ctype == "paramCompare":
        return u"%s %s %s" % (cond.get("param") or u"(매개변수 미지정)",
                              cond.get("op") or u"?",
                              cond.get("value"))
    if ctype == "not":
        return u"NOT(%s)" % describe_condition(cond.get("condition"))
    if ctype in ("all", "any"):
        joiner = u" AND " if ctype == "all" else u" OR "
        subs = cond.get("conditions") or []
        if not subs:
            return u"(빈 조건)"
        return u"(" + joiner.join(describe_condition(c) for c in subs) + u")"
    return unicode(ctype) if str is bytes else str(ctype)
