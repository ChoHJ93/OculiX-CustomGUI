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
from ctypes import wintypes

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

ENUM_CURRENT_SETTINGS = -1


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
