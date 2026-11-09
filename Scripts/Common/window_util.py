# -*- coding: utf-8 -*-
u"""창 찾기 / 포커스 / 이동 (Jython 전용).

`focusWindow` 와 `moveWindow` 노드가 쓴다. 엔진(macro_engine)이 이 노드를
만났을 때만 import 한다. 다른 매크로에서는 이 파일의 어떤 코드도 돌지 않는다.

좌표계
    노드의 좌표는 편집기의 [찍기] 가 준 값 그대로다. 편집기는 DPI 비인식
    프로세스라 그 값은 Windows 가 배율을 감춰 준 논리 좌표다 (screenutil 참조).
    JVM 은 DPI 인식 프로세스라 Win32 가 물리 좌표를 준다. 둘을 맞추려고 창을
    재고 옮기는 동안만 이 스레드를 DPI 비인식 문맥으로 바꾼다
    (SetThreadDpiAwarenessContext). 그러면 Windows 가 모니터마다 배율을 알아서
    풀어 주므로, 배율이 다른 보조 모니터에서도 편집기에서 찍은 좌표와 같은
    값을 쓰게 된다. 직접 배율을 곱하면 모니터마다 달라서 틀린다.

    단, DwmGetWindowAttribute 는 문맥과 무관하게 늘 물리 좌표를 준다.
    그래서 보이지 않는 테두리 폭은 물리 값으로 재서 창의 배율로 나눈다.

창 사각형
    GetWindowRect 에는 Windows 10/11 의 보이지 않는 크기 조절 테두리(보통
    7px)가 들어 있다. 그대로 쓰면 (0, 0) 으로 옮긴 창이 왼쪽에 7px 틈을 두고
    선다. 이동 좌표는 **눈에 보이는 창 테두리의 왼쪽 위**로 정한다.
"""

import time

import jarray
from java.lang import Character, Object, String

# 창을 찾지 못했을 때 다시 볼 간격(초).
FIND_POLL = 0.25

# 포커스를 요청한 뒤 실제로 넘어왔는지 확인하는 시간(초)과 간격.
FOCUS_SETTLE = 0.6
FOCUS_POLL = 0.05

# 옮긴 뒤 위치를 다시 잴 때까지 기다리는 시간(초).
MOVE_SETTLE = 0.15

# 옮긴 자리가 요청과 이만큼(px) 안에 있으면 성공으로 본다. 배율이 다른 모니터로
# 넘어가면 창이 WM_DPICHANGED 를 받아 테두리가 몇 px 달라진다.
MOVE_SLACK = 8

# Win32 상수
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_MINIMIZE = 0x20000000
WS_MAXIMIZE = 0x01000000
SW_RESTORE = 9
GA_ROOTOWNER = 3
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# DPI_AWARENESS_CONTEXT 핸들 값
DPI_UNAWARE = -1
DPI_PER_MONITOR_V2 = -4

# 창 상태
NORMAL = "normal"
MINIMIZED = "minimized"
MAXIMIZED = "maximized"
FULLSCREEN = "fullscreen"

STATE_LABELS = {
    NORMAL: u"보통",
    MINIMIZED: u"최소화",
    MAXIMIZED: u"최대화",
    FULLSCREEN: u"전체 화면",
}


class WindowError(Exception):
    u"""창을 다룰 수 없다 (API 를 쓸 수 없거나 거부됐다)."""
    pass


# ------------------------------------------------------------------ JNA

class _Api(object):
    u"""JNA 핸들 모음. 처음 쓸 때 한 번 만든다."""

    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        from com.sun.jna import Function, Native, Pointer
        from com.sun.jna.platform.win32 import Kernel32, User32, WinDef, WinUser
        from com.sun.jna.ptr import IntByReference
        self.Native = Native
        self.Pointer = Pointer
        self.WinDef = WinDef
        self.WinUser = WinUser
        self.IntByReference = IntByReference
        self.user32 = User32.INSTANCE
        self.kernel32 = Kernel32.INSTANCE
        self.dwm = Function.getFunction("dwmapi", "DwmGetWindowAttribute")
        try:
            self.set_context = Function.getFunction(
                "user32", "SetThreadDpiAwarenessContext")
        except Exception:
            # Windows 10 1607 이전. 문맥을 바꿀 수 없으면 좌표를 그대로 쓴다.
            self.set_context = None

    def call_int(self, function, args):
        return function.invokeInt(jarray.array(args, Object))

    def context(self, value):
        u"""이 스레드의 DPI 문맥을 바꾸고 이전 값을 돌려준다. 못 바꾸면 None."""
        if self.set_context is None:
            return None
        if not isinstance(value, self.Pointer):
            value = self.Pointer.createConstant(value)
        return self.set_context.invoke(self.Pointer,
                                       jarray.array([value], Object))


def _in_context(value, func):
    u"""DPI 문맥을 잠시 바꿔서 func() 을 부른다. 끝나면 반드시 되돌린다."""
    api = _Api.get()
    previous = api.context(value)
    try:
        return func()
    finally:
        if previous is not None:
            api.context(previous)


def _logical(func):
    u"""편집기와 같은 논리 좌표로 창을 다룬다."""
    return _in_context(DPI_UNAWARE, func)


def _physical(func):
    return _in_context(DPI_PER_MONITOR_V2, func)


def _rect_tuple(rect):
    return (rect.left, rect.top, rect.right, rect.bottom)


def handle_text(handle):
    u"""로그용 창 핸들 표기."""
    try:
        api = _Api.get()
        return u"0x%X" % api.Pointer.nativeValue(handle.getPointer())
    except Exception:
        return u"%s" % handle


# ------------------------------------------------------------------ 창 정보

def window_title(handle):
    api = _Api.get()
    buf = jarray.zeros(512, Character.TYPE)
    count = api.user32.GetWindowText(handle, buf, 512)
    return unicode(String(buf, 0, max(0, count)))


def window_class(handle):
    api = _Api.get()
    buf = jarray.zeros(256, Character.TYPE)
    count = api.user32.GetClassName(handle, buf, 256)
    return unicode(String(buf, 0, max(0, count)))


def window_process(handle, cache=None):
    u"""창을 만든 프로세스의 실행 파일 이름 (예: notepad.exe). 모르면 None.

    안티치트로 보호되는 프로세스나 관리자 권한 프로세스는 열리지 않을 수 있다.
    """
    api = _Api.get()
    pid_ref = api.IntByReference()
    api.user32.GetWindowThreadProcessId(handle, pid_ref)
    pid = pid_ref.getValue()
    if cache is not None and pid in cache:
        return cache[pid]
    name = None
    process = api.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                       False, pid)
    if process is not None:
        try:
            buf = jarray.zeros(1024, Character.TYPE)
            size = api.IntByReference(1024)
            if api.kernel32.QueryFullProcessImageName(process, 0, buf, size):
                path = unicode(String(buf, 0, size.getValue()))
                name = path.replace(u"/", u"\\").split(u"\\")[-1]
        finally:
            api.kernel32.CloseHandle(process)
    if cache is not None:
        cache[pid] = name
    return name


def _cloaked(handle):
    u"""화면에 없는데 IsWindowVisible 이 참인 창 (Windows 11 의 숨은 앱 창)."""
    api = _Api.get()
    value = api.IntByReference(0)
    result = api.call_int(api.dwm, [handle, DWMWA_CLOAKED, value, 4])
    return result == 0 and value.getValue() != 0


def describe(handle):
    u"""로그에 남길 창 설명."""
    process = window_process(handle) or u"?"
    return u'"%s" [%s, %s, %s]' % (window_title(handle), window_class(handle),
                                   process, handle_text(handle))


# ------------------------------------------------------------------ 찾기

def spec_of(step):
    u"""노드에서 창 조건만 뽑는다. 조건이 하나도 없으면 None."""
    spec = {}
    for key in ("title", "windowClass", "process"):
        value = step.get(key)
        if value not in (None, u"", ""):
            spec[key] = unicode(value).strip()
    if not spec:
        return None
    spec["titleMatch"] = step.get("titleMatch") or "contains"
    return spec


def describe_spec(spec):
    parts = []
    if spec.get("title"):
        how = u"일치" if spec.get("titleMatch") == "exact" else u"포함"
        parts.append(u'제목 "%s" %s' % (spec["title"], how))
    if spec.get("windowClass"):
        parts.append(u"클래스 %s" % spec["windowClass"])
    if spec.get("process"):
        parts.append(u"프로세스 %s" % spec["process"])
    return u", ".join(parts)


def _process_name(value):
    value = value.lower()
    if not value.endswith(u".exe"):
        value += u".exe"
    return value


def _matches(handle, spec, cache):
    api = _Api.get()
    if not api.user32.IsWindowVisible(handle):
        return False
    title = spec.get("title")
    if title is not None:
        actual = window_title(handle).lower()
        wanted = title.lower()
        if spec.get("titleMatch") == "exact":
            if actual != wanted:
                return False
        elif wanted not in actual:
            return False
    kind = spec.get("windowClass")
    if kind is not None and window_class(handle).lower() != kind.lower():
        return False
    process = spec.get("process")
    if process is not None:
        name = window_process(handle, cache)
        if name is None or name.lower() != _process_name(process):
            return False
    # 비싼 확인은 맨 마지막에 한다. 대부분의 창은 위에서 걸러진다.
    return not _cloaked(handle)


def find_windows(spec):
    u"""조건에 맞는 보이는 최상위 창들. 화면 앞쪽(Z 순서)부터 담긴다."""
    api = _Api.get()
    found = []
    cache = {}
    handle = api.user32.FindWindowEx(None, None, None, None)
    while handle is not None:
        if _matches(handle, spec, cache):
            found.append(handle)
        handle = api.user32.FindWindowEx(None, handle, None, None)
    return found


# ------------------------------------------------------------------ 상태

def _style(handle):
    return _Api.get().user32.GetWindowLong(handle, GWL_STYLE)


def _monitor_rect(monitor):
    api = _Api.get()
    info = api.WinUser.MONITORINFO()
    if not api.user32.GetMonitorInfo(monitor, info).booleanValue():
        return None
    return _rect_tuple(info.rcMonitor)


def window_rect(handle):
    u"""창 사각형 (보이지 않는 테두리 포함, 논리 좌표)."""
    api = _Api.get()

    def measure():
        rect = api.WinDef.RECT()
        if not api.user32.GetWindowRect(handle, rect):
            return None
        return _rect_tuple(rect)
    return _logical(measure)


def window_monitor(handle):
    u"""창이 주로 걸쳐 있는 모니터의 사각형 (논리 좌표)."""
    api = _Api.get()
    return _logical(lambda: _monitor_rect(
        api.user32.MonitorFromWindow(handle, MONITOR_DEFAULTTONEAREST)))


def window_state(handle):
    u"""보통 / 최소화 / 최대화 / 전체 화면.

    전체 화면은 창이 자기 모니터를 통째로 덮는 경우다. 게임의 테두리 없는
    전체 화면과 독점 전체 화면이 여기 든다. 작업 표시줄 자동 숨김을 켜면
    최대화한 창도 모니터를 덮으므로, 제목 표시줄이 있는 최대화 창은 최대화로
    본다.
    """
    style = _style(handle)
    if style & WS_MINIMIZE:
        return MINIMIZED
    rect = window_rect(handle)
    monitor = window_monitor(handle)
    covers = (rect is not None and monitor is not None
              and rect[0] <= monitor[0] and rect[1] <= monitor[1]
              and rect[2] >= monitor[2] and rect[3] >= monitor[3])
    maximized = bool(style & WS_MAXIMIZE)
    if covers and not (maximized and style & WS_CAPTION == WS_CAPTION):
        return FULLSCREEN
    if maximized:
        return MAXIMIZED
    return NORMAL


def monitor_at(x, y):
    u"""이 논리 좌표가 든 모니터의 사각형. 어느 모니터에도 없으면 None."""
    api = _Api.get()

    def lookup():
        point = api.WinDef.POINT.ByValue(int(x), int(y))
        monitor = api.user32.MonitorFromPoint(point, MONITOR_DEFAULTTONULL)
        if monitor is None:
            return None
        return _monitor_rect(monitor)
    return _logical(lookup)


def frame_insets(handle):
    u"""창 사각형에서 눈에 보이는 테두리까지의 거리 (왼, 위, 오른, 아래). 논리 px.

    DWM 은 늘 물리 좌표를 주므로 물리 문맥에서 창 사각형과 함께 잰 뒤,
    논리 사각형과의 비율(그 창이 놓인 모니터의 배율)로 나눈다.
    """
    api = _Api.get()

    def measure():
        rect = api.WinDef.RECT()
        frame = api.WinDef.RECT()
        if not api.user32.GetWindowRect(handle, rect):
            return None
        result = api.call_int(api.dwm, [handle, DWMWA_EXTENDED_FRAME_BOUNDS,
                                        frame, 16])
        if result != 0:
            return None
        frame.read()
        return _rect_tuple(rect), _rect_tuple(frame)
    measured = _physical(measure)
    logical = window_rect(handle)
    if measured is None or logical is None:
        return (0, 0, 0, 0)
    physical, frame = measured
    width = physical[2] - physical[0]
    ratio = float(width) / max(1, logical[2] - logical[0]) if width else 1.0
    if ratio <= 0:
        ratio = 1.0
    return tuple(int(round(v / ratio)) for v in (
        frame[0] - physical[0], frame[1] - physical[1],
        physical[2] - frame[2], physical[3] - frame[3]))


def frame_rect(handle):
    u"""눈에 보이는 창 테두리 (논리 좌표)."""
    rect = window_rect(handle)
    if rect is None:
        return None
    inset = frame_insets(handle)
    return (rect[0] + inset[0], rect[1] + inset[1],
            rect[2] - inset[2], rect[3] - inset[3])


# ------------------------------------------------------------------ 포커스

def _same(a, b):
    return a is not None and b is not None and a.equals(b)


def is_foreground(handle):
    u"""이 창(또는 이 창이 소유한 대화 상자)이 지금 입력을 받는가."""
    api = _Api.get()
    current = api.user32.GetForegroundWindow()
    if current is None:
        return False
    if _same(current, handle):
        return True
    return _same(api.user32.GetAncestor(current, GA_ROOTOWNER), handle)


def _wait_foreground(handle, seconds):
    deadline = time.time() + seconds
    while True:
        if is_foreground(handle):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(FOCUS_POLL)


def focus(handle, log):
    u"""창을 앞으로 가져와 입력을 받게 한다. 성공하면 True.

    Windows 는 다른 프로세스가 포커스를 가져가는 것을 막는다 (포그라운드 잠금).
    편집기가 띄운 실행기는 보통 허용되지만 사용자가 그 사이 다른 창을 만졌으면
    거부된다. 그때는 지금 포그라운드 창의 입력 큐에 잠시 붙어서 다시 요청한다.
    키를 눌러 잠금을 푸는 방법(Alt 주입)은 쓰지 않는다 - 대상 앱의 메뉴가
    열리는 부작용이 있다.
    """
    api = _Api.get()
    user32 = api.user32
    if _style(handle) & WS_MINIMIZE:
        log(u"    최소화돼 있어 복원합니다")
        user32.ShowWindow(handle, SW_RESTORE)

    user32.SetForegroundWindow(handle)
    if _wait_foreground(handle, FOCUS_SETTLE):
        return True

    current = user32.GetForegroundWindow()
    if current is None:
        return False
    log(u"    Windows 가 포커스 요청을 거부했습니다. 입력 큐에 붙어서 "
        u"다시 시도합니다")
    WinDef = api.WinDef
    mine = WinDef.DWORD(api.kernel32.GetCurrentThreadId())
    theirs = WinDef.DWORD(user32.GetWindowThreadProcessId(current, None))
    attached = user32.AttachThreadInput(mine, theirs, True)
    try:
        user32.BringWindowToTop(handle)
        user32.SetForegroundWindow(handle)
    finally:
        if attached:
            user32.AttachThreadInput(mine, theirs, False)
    return _wait_foreground(handle, FOCUS_SETTLE)


# ------------------------------------------------------------------ 이동

def move_frame(handle, x, y):
    u"""눈에 보이는 창 테두리의 왼쪽 위를 (x, y) 로 옮긴다. 옮긴 뒤 테두리를 준다.

    크기는 바꾸지 않고 Z 순서와 포커스도 건드리지 않는다.
    """
    api = _Api.get()
    rect = window_rect(handle)
    if rect is None:
        raise WindowError(u"창 위치를 읽지 못했습니다")
    inset = frame_insets(handle)
    left, top = int(x) - inset[0], int(y) - inset[1]

    def apply_move():
        return api.user32.SetWindowPos(
            handle, None, left, top, 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
    if not _logical(apply_move):
        code = api.Native.getLastError()
        hint = u""
        if code == 5:
            hint = u" - 관리자 권한으로 실행된 창은 옮길 수 없습니다"
        raise WindowError(u"창을 옮기지 못했습니다 (오류 %d)%s" % (code, hint))
    time.sleep(MOVE_SETTLE)
    return frame_rect(handle)
