# -*- coding: utf-8 -*-
"""패널 도킹 - 창을 끌어서 위치를 바꾼다.

영역은 네 개다.

    ┌──────┬────────────┬──────┐
    │ left │   center   │ right│
    ├──────┴────────────┴──────┤
    │          bottom          │
    └──────────────────────────┘

한 영역에 여러 패널이 오면 세로로 쌓인다.
패널 제목줄을 끌어서 다른 영역에 놓으면 옮겨진다.

**tkinter는 위젯의 부모를 바꿀 수 없다.** 그래서 레이아웃이 바뀌면 패널 내용을
다시 짓는다. 유지해야 하는 상태(로그 내용, 캔버스 확대율 등)는 각 패널이
`save_state` / `restore_state` 로 넘긴다.
"""

import tkinter as tk
from tkinter import ttk

import theme


AREAS = ("left", "center", "right", "bottom")
AREA_LABELS = {
    "left": u"왼쪽",
    "center": u"가운데",
    "right": u"오른쪽",
    "bottom": u"아래",
}


class DockPanel(object):

    def __init__(self, key, title, factory, save_state=None, restore_state=None,
                 min_width=140, min_height=90):
        self.key = key
        self.title = title
        self.factory = factory              # factory(parent_frame) -> None
        self.save_state = save_state        # () -> dict
        self.restore_state = restore_state  # (dict) -> None
        self.min_width = min_width
        self.min_height = min_height
        self.header = None


class DockManager(object):

    def __init__(self, master, on_change=None, on_before_rebuild=None):
        self.master = master
        self.on_change = on_change
        # 다시 짓기 직전에 호출된다. 앱이 갖고 있는 위젯 참조를 비우는 자리다.
        # 비우지 않으면 파괴된 위젯을 건드려 TclError 가 난다.
        self.on_before_rebuild = on_before_rebuild
        self.panels = {}
        self.order = []
        self.layout = dict((area, []) for area in AREAS)
        self._area_frames = {}
        self._area_panes = {}
        self._drag = None
        self._ghost = None
        self._highlight = None
        self._building = False

        self.outer = ttk.PanedWindow(master, orient="vertical")
        self.outer.pack(fill="both", expand=True)
        self.top_row = None
        self.bottom_pane = None

    # ------------------------------------------------------------------ 등록

    def register(self, key, title, factory, save_state=None, restore_state=None):
        panel = DockPanel(key, title, factory, save_state, restore_state)
        self.panels[key] = panel
        self.order.append(key)
        return panel

    # ------------------------------------------------------------------ 상태

    def default_layout(self):
        return {
            "left": ["library", "submacros", "project"],
            "center": ["graph"],
            "right": ["properties"],
            "bottom": ["log"],
        }

    def get_layout(self):
        """저장할 레이아웃 정보."""
        data = {"areas": dict((a, list(self.layout[a])) for a in AREAS)}
        sashes = {}
        try:
            def grab(key, pane):
                if pane is None:
                    return
                count = len(pane.panes()) - 1
                if count <= 0:
                    return
                values = [pane.sashpos(i) for i in range(count)]
                # 창이 그려지기 전이면 전부 0 으로 읽힌다. 그런 값을 저장하면
                # 다음 실행 때 패널이 다 접힌 채로 뜬다. 그러면 저장하지 않는다.
                if any(v > 1 for v in values):
                    sashes[key] = values

            grab("outer", self.outer)
            grab("top", self.top_row)
            for area, pane in self._area_panes.items():
                grab(area, pane)
        except tk.TclError:
            pass
        data["sashes"] = sashes
        return data

    def set_layout(self, data):
        """저장해 둔 레이아웃을 적용. 모르는 패널 이름은 버린다."""
        areas = (data or {}).get("areas") or {}
        clean = dict((a, []) for a in AREAS)
        placed = set()
        for area in AREAS:
            for key in areas.get(area) or []:
                if key in self.panels and key not in placed:
                    clean[area].append(key)
                    placed.add(key)
        # 저장본에 없던 패널은 기본 위치로
        defaults = self.default_layout()
        for area in AREAS:
            for key in defaults[area]:
                if key in self.panels and key not in placed:
                    clean[area].append(key)
                    placed.add(key)
        self.layout = clean
        self.rebuild(sashes=(data or {}).get("sashes"))

    # ------------------------------------------------------------------ 구축

    def rebuild(self, sashes=None):
        if self._building:
            return
        self._building = True
        try:
            states = {}
            for key, panel in self.panels.items():
                if panel.save_state:
                    try:
                        states[key] = panel.save_state()
                    except Exception:
                        states[key] = None

            if self.on_before_rebuild:
                self.on_before_rebuild()

            for child in self.outer.panes():
                self.outer.forget(child)
            for widget in self.outer.winfo_children():
                widget.destroy()
            self._area_frames.clear()
            self._area_panes.clear()

            self.top_row = ttk.PanedWindow(self.outer, orient="horizontal")
            has_top = any(self.layout[a] for a in ("left", "center", "right"))
            if has_top:
                self.outer.add(self.top_row, weight=4)

            weights = {"left": 1, "center": 4, "right": 2}
            for area in ("left", "center", "right"):
                if not self.layout[area]:
                    continue
                pane = ttk.PanedWindow(self.top_row, orient="vertical")
                self.top_row.add(pane, weight=weights[area])
                self._area_panes[area] = pane
                self._fill_area(area, pane)

            if self.layout["bottom"]:
                pane = ttk.PanedWindow(self.outer, orient="vertical")
                self.outer.add(pane, weight=1)
                self._area_panes["bottom"] = pane
                self._fill_area("bottom", pane)

            for key, panel in self.panels.items():
                if panel.restore_state and key in states and states[key] is not None:
                    try:
                        panel.restore_state(states[key])
                    except Exception:
                        pass

            if sashes:
                self.master.after(60, lambda: self._apply_sashes(sashes))
        finally:
            self._building = False
        if self.on_change:
            self.on_change()

    def _fill_area(self, area, pane):
        for key in self.layout[area]:
            panel = self.panels[key]
            holder = ttk.Frame(pane)
            pane.add(holder, weight=1)

            header = tk.Label(holder, text=panel.title, anchor="w",
                              bg=theme.BG_DARK, fg=theme.FG_DIM,
                              font=theme.FONT_BOLD, padx=8, pady=5,
                              cursor="fleur")
            header.pack(fill="x")
            panel.header = header
            header.bind("<ButtonPress-1>", lambda e, k=key: self._drag_start(e, k))
            header.bind("<B1-Motion>", self._drag_move)
            header.bind("<ButtonRelease-1>", self._drag_end)
            header.bind("<Button-3>", lambda e, k=key: self._header_menu(e, k))

            body = ttk.Frame(holder)
            body.pack(fill="both", expand=True)
            self._area_frames[key] = holder
            panel.factory(body)

    def _panes_ready(self):
        """분할선을 놓을 수 있을 만큼 창이 실제로 그려졌는가.

        창이 아직 배치되기 전에는 폭/높이가 1 이하다. 그 상태에서 sashpos 를
        부르면 값이 0 으로 잘려 모든 패널이 접혀 버린다 - 레이아웃이 초기화된
        것처럼 보이는 원인이었다.
        """
        panes = [self.outer, self.top_row] + list(self._area_panes.values())
        for pane in panes:
            if pane is None:
                continue
            try:
                if pane.winfo_width() <= 1 or pane.winfo_height() <= 1:
                    return False
            except tk.TclError:
                return False
        return True

    def _apply_sashes(self, sashes, attempt=0):
        if not sashes:
            return
        if not self._panes_ready():
            if attempt < 60:        # 최대 3초 정도 기다린다
                self.master.after(50,
                                  lambda: self._apply_sashes(sashes, attempt + 1))
            return

        def place(pane, values, horizontal):
            if pane is None or not values:
                return
            try:
                limit = pane.winfo_width() if horizontal else pane.winfo_height()
                count = len(pane.panes()) - 1
                for index, value in enumerate(values):
                    if index >= count:
                        break
                    # 창이 저장 당시보다 작아졌을 수 있다. 범위 안으로 당겨 준다.
                    value = max(24, min(int(value), max(24, limit - 24)))
                    pane.sashpos(index, value)
            except tk.TclError:
                pass

        place(self.outer, sashes.get("outer"), horizontal=False)
        place(self.top_row, sashes.get("top"), horizontal=True)
        for area, pane in self._area_panes.items():
            place(pane, sashes.get(area), horizontal=False)

    # ------------------------------------------------------------------ 이동

    def _area_at(self, x_root, y_root):
        """화면 좌표가 어느 영역 위인지."""
        for area, pane in self._area_panes.items():
            try:
                px = pane.winfo_rootx()
                py = pane.winfo_rooty()
                pw = pane.winfo_width()
                ph = pane.winfo_height()
            except tk.TclError:
                continue
            if px <= x_root < px + pw and py <= y_root < py + ph:
                return area
        # 빈 영역도 놓을 수 있게 창 가장자리로 판정
        try:
            rx = self.master.winfo_rootx()
            ry = self.master.winfo_rooty()
            rw = self.master.winfo_width()
            rh = self.master.winfo_height()
        except tk.TclError:
            return None
        if not (rx <= x_root < rx + rw and ry <= y_root < ry + rh):
            return None
        if y_root > ry + rh * 0.78:
            return "bottom"
        if x_root < rx + rw * 0.22:
            return "left"
        if x_root > rx + rw * 0.78:
            return "right"
        return "center"

    def _drag_start(self, event, key):
        self._drag = {"key": key, "moved": False}

    def _drag_move(self, event):
        if not self._drag:
            return
        if not self._drag["moved"]:
            self._drag["moved"] = True
            panel = self.panels[self._drag["key"]]
            self._ghost = tk.Toplevel(self.master)
            self._ghost.overrideredirect(True)
            self._ghost.attributes("-topmost", True)
            self._ghost.attributes("-alpha", 0.9)
            self._ghost_label = tk.Label(
                self._ghost, text=panel.title, bg=theme.ACCENT_DARK,
                fg="#ffffff", font=theme.FONT_BOLD, padx=10, pady=5)
            self._ghost_label.pack()
        area = self._area_at(event.x_root, event.y_root)
        panel = self.panels[self._drag["key"]]
        if area:
            self._ghost_label.configure(
                text=u"%s  →  %s" % (panel.title, AREA_LABELS[area]),
                bg=theme.ACCENT_DARK)
        else:
            self._ghost_label.configure(text=u"%s  (창 밖)" % panel.title,
                                        bg="#6b3030")
        self._ghost.geometry("+%d+%d" % (event.x_root + 14, event.y_root + 14))

    def _drag_end(self, event):
        drag = self._drag
        self._drag = None
        if self._ghost is not None:
            self._ghost.destroy()
            self._ghost = None
        if not drag or not drag["moved"]:
            return
        area = self._area_at(event.x_root, event.y_root)
        if area:
            self.move_panel(drag["key"], area)

    def move_panel(self, key, area):
        if area not in AREAS or key not in self.panels:
            return
        current = self.area_of(key)
        if current == area:
            return
        # 마지막 남은 가운데 패널을 비우지 않는다
        if current and len(self.layout[current]) == 1 and current == "center" \
                and not self.layout["center"][:0]:
            pass
        if current:
            self.layout[current].remove(key)
        self.layout[area].append(key)
        self.rebuild()

    def area_of(self, key):
        for area in AREAS:
            if key in self.layout[area]:
                return area
        return None

    def _header_menu(self, event, key):
        menu = tk.Menu(self.master, tearoff=0)
        theme.style_menu(menu)
        current = self.area_of(key)
        for area in AREAS:
            label = u"%s 으로 보내기" % AREA_LABELS[area]
            if area == current:
                menu.add_command(label=u"● %s (현재)" % AREA_LABELS[area],
                                 state="disabled")
            else:
                menu.add_command(label=label,
                                 command=lambda a=area, k=key: self.move_panel(k, a))
        menu.tk_popup(event.x_root, event.y_root)

    def reset(self):
        self.layout = self.default_layout()
        self.rebuild()
