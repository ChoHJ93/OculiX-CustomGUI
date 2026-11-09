# -*- coding: utf-8 -*-
"""좌표계 변환.

이 PC에서 실측으로 확인한 사실 (2026-08-16):

    창 / 커서 / tkinter 좌표  ->  논리 좌표 (OculiX Screen(0) = 2048x1152 와 동일)
    GDI GetPixel / BitBlt     ->  물리 좌표 (2560x1440, 논리 x 1.25)

즉 마우스로 찍은 좌표는 그대로 매크로에 넣으면 되지만,
그 좌표의 픽셀 색을 GDI로 읽으려면 배율을 곱해야 한다.

검증 방법: 알려진 색의 패널을 논리 좌표 (358,401)에 띄우고
  - OculiX      -> (200,30,30)  일치
  - GDI 그대로  -> (255,255,255) 불일치
  - GDI x1.25   -> (200,30,30)  일치
"""

import ctypes
import re
from ctypes import wintypes

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

ENUM_CURRENT_SETTINGS = -1

# 64비트에서 창 핸들이 잘리지 않게 형을 정해 둔다.
_user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
_user32.FindWindowW.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = (wintypes.POINT,)
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

GA_ROOT = 2


class _DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_MONITORINFOF_PRIMARY = 1
_MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
_user32.EnumDisplayMonitors.argtypes = (wintypes.HDC,
                                        ctypes.POINTER(wintypes.RECT),
                                        _MonitorEnumProc, wintypes.LPARAM)
_user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE,
                                    ctypes.POINTER(_MONITORINFO))

# 제목 표시줄 높이와, 창을 끌어 옮기려면 보여야 하는 최소 폭.
_TITLE_HEIGHT = 32
_TITLE_MIN_VISIBLE = 120

_GEOMETRY = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


def work_areas():
    """모니터별 작업 영역 [(왼, 위, 오른, 아래), ...]. 주 모니터가 맨 앞이다."""
    found = []

    def visit(monitor, _dc, _rect, _param):
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
            primary = bool(info.dwFlags & _MONITORINFOF_PRIMARY)
            found.append((not primary,
                          (work.left, work.top, work.right, work.bottom)))
        return True

    _user32.EnumDisplayMonitors(None, None, _MonitorEnumProc(visit), 0)
    return [area for _order, area in sorted(found)]


def fit_geometry(text, areas=None):
    """저장된 창 위치가 지금 화면에서 보이게 고친다. (geometry, 옮겼는가).

    모니터 구성이 바뀌면 저장된 좌표가 없는 화면을 가리킨다. Windows 는 그런
    창을 알아서 옮겨 주지 않아서, 창은 떠 있는데 보이지 않게 된다.
    제목 표시줄을 잡을 수 있는 한 그대로 둔다 - 위치는 사용자가 정한 것이다.
    못 잡으면 주 모니터 가운데로 옮기고, 크기는 그 화면에 맞게 줄인다.
    """
    matched = _GEOMETRY.match(text or "")
    if areas is None:
        areas = work_areas()
    if not matched or not areas:
        return text, False

    width, height, x, y = [int(v) for v in matched.groups()]
    for left, top, right, bottom in areas:
        wide = min(right, x + width) - max(left, x)
        tall = min(bottom, y + _TITLE_HEIGHT) - max(top, y)
        if wide >= min(width, _TITLE_MIN_VISIBLE) and tall > 0:
            return text, False

    left, top, right, bottom = areas[0]
    area_w, area_h = right - left, bottom - top - _TITLE_HEIGHT
    width, height = min(width, area_w), min(height, area_h)
    return ("%dx%d+%d+%d" % (width, height,
                             left + (area_w - width) // 2,
                             top + (area_h - height) // 2)), True


def logical_screen_size():
    """DPI-unaware 프로세스가 보는 주 모니터 크기. OculiX Screen(0)과 같다."""
    return _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)


def physical_screen_size():
    """주 모니터의 실제 디스플레이 모드 해상도."""
    dm = _DEVMODE()
    dm.dmSize = ctypes.sizeof(_DEVMODE)
    ok = _user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    if not ok:
        return logical_screen_size()
    return int(dm.dmPelsWidth), int(dm.dmPelsHeight)


_scale_cache = None


def scale():
    """논리 -> 물리 배율 (x, y). 125% 스케일링이면 (1.25, 1.25)."""
    global _scale_cache
    if _scale_cache is None:
        lw, lh = logical_screen_size()
        pw, ph = physical_screen_size()
        if lw <= 0 or lh <= 0:
            _scale_cache = (1.0, 1.0)
        else:
            _scale_cache = (float(pw) / lw, float(ph) / lh)
    return _scale_cache


def logical_to_physical(x, y):
    sx, sy = scale()
    return int(round(x * sx)), int(round(y * sy))


def read_pixel(x, y):
    """논리 좌표의 픽셀 색을 (r, g, b)로 반환. 변환은 내부에서 처리한다."""
    px, py = logical_to_physical(x, y)
    dc = _user32.GetDC(0)
    try:
        value = _gdi32.GetPixel(dc, px, py)
    finally:
        _user32.ReleaseDC(0, dc)
    if value == 0xFFFFFFFF:      # CLR_INVALID
        return None
    return (value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)


def client_rect(handle):
    """창 안쪽의 논리 좌표 [x, y, w, h]. 창이 없거나 최소화면 None.

    편집기는 DPI 비인식 프로세스라 Windows 가 논리값으로 바꿔서 준다.
    이 값이 OculiX 좌표와 같다 (실측: 물리 1,38 1705x1341 -> 1,30 1364x1072).
    """
    if not handle:
        return None
    rect = wintypes.RECT()
    if not _user32.GetClientRect(handle, ctypes.byref(rect)):
        return None
    if rect.right <= 0 or rect.bottom <= 0:
        return None
    origin = wintypes.POINT(0, 0)
    if not _user32.ClientToScreen(handle, ctypes.byref(origin)):
        return None
    return [origin.x, origin.y, rect.right, rect.bottom]


def game_client(window):
    """`settings.scaling.window` 가 가리키는 창의 안쪽. 없으면 None."""
    if not window:
        return None
    return client_rect(_user32.FindWindowW(window.get("class"),
                                           window.get("title")))


def window_at(x, y):
    """이 지점의 최상위 창. {"class", "title", "client"} 또는 None."""
    handle = _user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    if not handle:
        return None
    handle = _user32.GetAncestor(handle, GA_ROOT) or handle
    client = client_rect(handle)
    if client is None:
        return None
    kind = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(handle, kind, 256)
    title = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(handle, title, 512)
    return {"class": kind.value, "title": title.value, "client": client,
            "process": window_process(handle)}


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND,
                                             ctypes.POINTER(wintypes.DWORD))
_kernel32 = ctypes.windll.kernel32
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD))
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


def window_process(handle):
    """창을 만든 프로세스의 실행 파일 이름 (예: notepad.exe). 모르면 None.

    엔진의 window_util.window_process 와 같은 값을 내야 한다 - 편집기에서
    찍은 이름으로 엔진이 창을 찾는다.
    """
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    process = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION,
                                    False, pid.value)
    if not process:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if not _kernel32.QueryFullProcessImageNameW(process, 0, buf,
                                                    ctypes.byref(size)):
            return None
        return buf.value.replace("/", "\\").split("\\")[-1]
    finally:
        _kernel32.CloseHandle(process)


def cursor_position():
    """커서의 논리 좌표. 변환 불필요 - 이미 논리 좌표다."""
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def describe():
    lw, lh = logical_screen_size()
    pw, ph = physical_screen_size()
    sx, sy = scale()
    return (u"주 모니터  논리 %dx%d  물리 %dx%d  배율 %.3f/%.3f" %
            (lw, lh, pw, ph, sx, sy))


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(describe())
    x, y = cursor_position()
    print(u"커서 논리 좌표 = (%d, %d)" % (x, y))
    print(u"그 지점 색      = %s" % (read_pixel(x, y),))
