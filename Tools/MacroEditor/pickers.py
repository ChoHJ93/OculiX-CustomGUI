# -*- coding: utf-8 -*-
"""화면에서 좌표 / 색 / 영역을 집는 오버레이.

모든 반환 좌표는 논리 좌표다 (OculiX가 쓰는 좌표계).
tkinter의 event.x_root / y_root 가 이미 논리 좌표라 변환이 필요 없다.

색을 읽을 때만 주의가 필요하다. 오버레이가 화면을 덮고 있으면 오버레이 색이
읽히므로, 클릭 직후 오버레이를 없애고 잠깐 기다린 뒤 샘플링한다.
"""

import time
import tkinter as tk

import screenutil


def _virtual_bounds():
    """전체 가상 데스크톱 영역 (논리 좌표). 음수 원점도 그대로 쓴다."""
    import ctypes
    u = ctypes.windll.user32
    return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
            u.GetSystemMetrics(78), u.GetSystemMetrics(79))


class _Overlay(object):
    """화면 전체를 덮는 반투명 창. 서브클래스가 동작을 정의한다."""

    ALPHA = 0.30
    HINT = u"클릭해서 선택  /  ESC 취소"

    def __init__(self, parent):
        self.parent = parent
        self.result = None
        x, y, w, h = _virtual_bounds()
        self.origin = (x, y)

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", self.ALPHA)
        self.win.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.win.configure(bg="#000000", cursor="crosshair")

        self.canvas = tk.Canvas(self.win, bg="#000000", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.readout = tk.Label(self.win, text=self.HINT, bg="#111111",
                                fg="#ffffff", font=("Consolas", 13), padx=10, pady=6)
        self.readout.place(x=20, y=20)

        self.win.bind("<Escape>", self._cancel)
        self.canvas.bind("<Motion>", self._on_motion)
        self.win.focus_force()
        self.win.grab_set()

    # 서브클래스가 채운다
    def _on_motion(self, event):
        self.readout.config(text=u"  (%d, %d)   %s" % (event.x_root, event.y_root, self.HINT))

    def _cancel(self, _event=None):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()

    def run(self):
        self.parent.wait_window(self.win)
        return self.result


class PointPicker(_Overlay):
    HINT = u"클릭해서 좌표 선택  /  ESC 취소"

    def __init__(self, parent):
        _Overlay.__init__(self, parent)
        self.canvas.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        self.result = (event.x_root, event.y_root)
        self._close()


class ColorPicker(_Overlay):
    HINT = u"클릭해서 색 선택  /  ESC 취소"

    def __init__(self, parent):
        _Overlay.__init__(self, parent)
        self.canvas.bind("<Button-1>", self._on_click)
        self._point = None

    def _on_click(self, event):
        # 오버레이가 덮고 있으면 오버레이 색이 읽힌다. 먼저 치우고 샘플링한다.
        self._point = (event.x_root, event.y_root)
        self._close()

    def run(self):
        self.parent.wait_window(self.win)
        if not self._point:
            return None
        self.parent.update()
        time.sleep(0.18)          # 화면이 다시 그려질 시간
        rgb = screenutil.read_pixel(*self._point)
        if rgb is None:
            return None
        return {"point": list(self._point), "rgb": list(rgb)}


class RegionPicker(_Overlay):
    HINT = u"드래그해서 영역 선택  /  ESC 취소"
    ALPHA = 0.35

    def __init__(self, parent):
        _Overlay.__init__(self, parent)
        self.start = None
        self.rect_id = None
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def _to_canvas(self, event):
        return event.x_root - self.origin[0], event.y_root - self.origin[1]

    def _on_press(self, event):
        self.start = (event.x_root, event.y_root)
        cx, cy = self._to_canvas(event)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            cx, cy, cx, cy, outline="#00ff88", width=2)

    def _on_drag(self, event):
        if not self.start or not self.rect_id:
            return
        sx = self.start[0] - self.origin[0]
        sy = self.start[1] - self.origin[1]
        cx, cy = self._to_canvas(event)
        self.canvas.coords(self.rect_id, sx, sy, cx, cy)
        w = abs(event.x_root - self.start[0])
        h = abs(event.y_root - self.start[1])
        self.readout.config(
            text=u"  %d x %d   시작 (%d, %d)   %s"
                 % (w, h, min(self.start[0], event.x_root),
                    min(self.start[1], event.y_root), self.HINT))

    def _on_release(self, event):
        if not self.start:
            return
        x = min(self.start[0], event.x_root)
        y = min(self.start[1], event.y_root)
        w = abs(event.x_root - self.start[0])
        h = abs(event.y_root - self.start[1])
        if w < 4 or h < 4:
            self.readout.config(text=u"  너무 작습니다. 다시 드래그하세요.")
            self.start = None
            return
        self.result = (x, y, w, h)
        self._close()


def pick_point(parent):
    """논리 좌표 (x, y) 또는 None."""
    return PointPicker(parent).run()


def pick_color(parent):
    """{'point': [x, y], 'rgb': [r, g, b]} 또는 None."""
    return ColorPicker(parent).run()


def pick_region(parent):
    """논리 좌표 (x, y, w, h) 또는 None."""
    return RegionPicker(parent).run()
