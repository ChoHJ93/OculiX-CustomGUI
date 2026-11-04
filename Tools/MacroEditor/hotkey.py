# -*- coding: utf-8 -*-
"""전역 단축키 - 편집기 창이 앞에 없어도 받는 키 (Windows RegisterHotKey).

게임 창이 앞에 있을 때도 일시정지를 걸 수 있어야 한다. tkinter 의 bind 는
편집기 창에 포커스가 있을 때만 동작하고, 창을 전환하는 사이에도 매크로는
계속 돈다.

외부 패키지를 쓰지 않는다. RegisterHotKey 는 Windows 가 공식으로 제공하는
단축키 등록 기능이고, 키 입력을 가로채는 훅이 아니다.

다루는 방식

* **실행 중에만 등록한다.** 등록해 두면 그 키는 다른 프로그램에 가지 않는다.
  편집기를 켜 두기만 해도 F6 을 빼앗으면 곤란하다.
* 등록한 스레드의 메시지 큐로 WM_HOTKEY 가 오므로 전용 스레드가 메시지를
  돌린다. 콜백은 **그 스레드에서** 불린다 - tkinter 를 직접 건드리면 안 된다.
* 다른 프로그램이 이미 그 키를 쓰고 있으면 등록이 실패한다. 실패해도 예외를
  내지 않는다 - 알림 때문에 실행이 막히면 안 된다는 notify 와 같은 원칙이다.
"""

import ctypes
import threading
from ctypes import wintypes

VK_F6 = 0x75

_MOD_NOREPEAT = 0x4000       # 누르고 있어도 한 번만 온다
_WM_QUIT = 0x0012
_WM_HOTKEY = 0x0312
_PM_NOREMOVE = 0
_ERROR_HOTKEY_ALREADY_REGISTERED = 1409


class GlobalHotkey(object):
    """키 하나. start() 로 등록하고 stop() 으로 푼다. 다시 쓸 수 있다."""

    def __init__(self, vk, on_press, hotkey_id=1):
        self.vk = vk
        self.on_press = on_press
        self.hotkey_id = hotkey_id
        self.active = False
        self.error = None            # 등록 실패 이유 (사람이 읽을 문장)
        self._thread = None
        self._thread_id = None
        self._ready = None

    def start(self):
        """등록한다. 됐으면 True. 실패하면 False 이고 self.error 에 이유가 있다."""
        if self.active:
            return True
        self.error = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(2.0):
            self.error = u"응답이 없습니다"
            return False
        return self.active

    def stop(self):
        """등록을 푼다. 등록돼 있지 않으면 아무 일도 하지 않는다."""
        thread = self._thread
        if thread is None:
            return
        try:
            self._user32().PostThreadMessageW(
                self._thread_id, _WM_QUIT, 0, 0)
        except (AttributeError, OSError):
            pass
        thread.join(2.0)
        self._thread = None
        self.active = False

    @staticmethod
    def _user32():
        # 다른 모듈과 공유하지 않는 인스턴스. argtypes 와 last_error 가 섞이지 않는다.
        lib = ctypes.WinDLL("user32", use_last_error=True)
        lib.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                       wintypes.UINT, wintypes.UINT]
        lib.RegisterHotKey.restype = wintypes.BOOL
        lib.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        lib.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                    wintypes.UINT, wintypes.UINT]
        lib.GetMessageW.restype = ctypes.c_int
        lib.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                     wintypes.UINT, wintypes.UINT, wintypes.UINT]
        lib.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        return lib

    def _loop(self):
        try:
            user32 = self._user32()
            self._thread_id = ctypes.WinDLL("kernel32").GetCurrentThreadId()
        except (AttributeError, OSError) as exc:      # Windows 가 아니다
            self.error = u"%s" % exc
            self._ready.set()
            return

        msg = wintypes.MSG()
        # 이 스레드의 메시지 큐를 먼저 만든다. 없으면 stop() 의 WM_QUIT 가 샌다.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_NOREMOVE)

        if not user32.RegisterHotKey(None, self.hotkey_id, _MOD_NOREPEAT,
                                     self.vk):
            code = ctypes.get_last_error()
            if code == _ERROR_HOTKEY_ALREADY_REGISTERED:
                self.error = u"다른 프로그램이 이미 이 키를 쓰고 있습니다"
            else:
                self.error = u"등록 실패 (오류 %d)" % code
            self._ready.set()
            return

        self.active = True
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY:
                    self.on_press()
        finally:
            user32.UnregisterHotKey(None, self.hotkey_id)
            self.active = False
