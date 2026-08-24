# -*- coding: utf-8 -*-
"""특수키 / 조합키 선택 창.

두 가지 방법을 함께 제공한다.

* **캡처** — 실제로 키를 누르면 그대로 잡는다. 오타가 불가능하고 조합키가 한 번에 된다.
  다만 Windows가 가로채는 키(WIN 단독, PrintScreen, Alt+Tab 등)는 잡히지 않는다.
* **목록** — 캡처로 못 잡는 키를 위해 60개 전체를 그룹별로 고를 수 있다.

키 목록은 추측이 아니라 `Scripts\\Tests\\KeyProbe.sikuli` 로 OculiX 4.0.0에서
직접 뽑은 것이다. `C_` 접두가 붙은 56개는 같은 값의 별칭이라 제외했다.
"""

import tkinter as tk
from tkinter import ttk

import theme


# OculiX 4.0.0에서 확인한 실제 키 상수 60개.
# cMax / cMin / keyboardUS 는 키가 아니라 내부값이라 뺐다.
KEY_GROUPS = [
    (u"자주 쓰는 키", [
        ("ENTER", u"Enter"), ("TAB", u"Tab"), ("SPACE", u"Space"),
        ("BACKSPACE", u"Backspace"), ("DELETE", u"Delete"),
        ("INSERT", u"Insert"), ("ESC", u"Esc"),
    ]),
    (u"이동", [
        ("UP", u"↑"), ("DOWN", u"↓"), ("LEFT", u"←"), ("RIGHT", u"→"),
        ("HOME", u"Home"), ("END", u"End"),
        ("PAGE_UP", u"Page Up"), ("PAGE_DOWN", u"Page Down"),
        ("NEXT", u"Next"),
    ]),
    (u"기능키", [("F%d" % i, u"F%d" % i) for i in range(1, 16)]),
    (u"숫자패드", [
        ("NUM0", u"숫자패드 0"), ("NUM1", u"숫자패드 1"), ("NUM2", u"숫자패드 2"),
        ("NUM3", u"숫자패드 3"), ("NUM4", u"숫자패드 4"), ("NUM5", u"숫자패드 5"),
        ("NUM6", u"숫자패드 6"), ("NUM7", u"숫자패드 7"), ("NUM8", u"숫자패드 8"),
        ("NUM9", u"숫자패드 9"),
        ("ADD", u"+"), ("MINUS", u"-"), ("MULTIPLY", u"*"), ("DIVIDE", u"/"),
        ("DECIMAL", u"."), ("SEPARATOR", u"구분자"), ("NUM_LOCK", u"Num Lock"),
    ]),
    (u"수정키 단독", [
        ("SHIFT", u"Shift"), ("CTRL", u"Ctrl"), ("ALT", u"Alt"),
        ("ALTGR", u"AltGr"), ("WIN", u"Win"), ("CMD", u"Cmd"), ("META", u"Meta"),
    ]),
    (u"시스템", [
        ("PRINTSCREEN", u"Print Screen"), ("SCROLL_LOCK", u"Scroll Lock"),
        ("PAUSE", u"Pause"), ("CAPS_LOCK", u"Caps Lock"),
        ("CONTEXT", u"메뉴(컨텍스트)"),
    ]),
]

ALL_KEYS = [name for _group, entries in KEY_GROUPS for name, _label in entries]

# 조합키. WIN / CMD / META 는 OculiX에서 값이 모두 4로 같다 - 하나만 노출한다.
MODIFIERS = [
    ("CTRL", u"Ctrl"),
    ("SHIFT", u"Shift"),
    ("ALT", u"Alt"),
    ("META", u"Win"),
]

MODIFIER_KEYSYMS = {
    "Control_L": "CTRL", "Control_R": "CTRL",
    "Shift_L": "SHIFT", "Shift_R": "SHIFT",
    "Alt_L": "ALT", "Alt_R": "ALT",
    "Win_L": "META", "Win_R": "META",
    "Super_L": "META", "Super_R": "META",
    "Meta_L": "META", "Meta_R": "META",
}

# tkinter 가 주는 keysym -> OculiX Key 이름
KEYSYM_MAP = {
    "Return": "ENTER", "KP_Enter": "ENTER",
    "Tab": "TAB", "ISO_Left_Tab": "TAB",
    "space": "SPACE",
    "BackSpace": "BACKSPACE",
    "Delete": "DELETE", "KP_Delete": "DELETE",
    "Insert": "INSERT", "KP_Insert": "INSERT",
    "Escape": "ESC",
    "Up": "UP", "Down": "DOWN", "Left": "LEFT", "Right": "RIGHT",
    "KP_Up": "UP", "KP_Down": "DOWN", "KP_Left": "LEFT", "KP_Right": "RIGHT",
    "Home": "HOME", "End": "END", "KP_Home": "HOME", "KP_End": "END",
    "Prior": "PAGE_UP", "Next": "PAGE_DOWN",
    "KP_Prior": "PAGE_UP", "KP_Next": "PAGE_DOWN",
    "Caps_Lock": "CAPS_LOCK", "Num_Lock": "NUM_LOCK",
    "Scroll_Lock": "SCROLL_LOCK", "Pause": "PAUSE",
    "Print": "PRINTSCREEN", "Menu": "CONTEXT", "App": "CONTEXT",
    "KP_Add": "ADD", "KP_Subtract": "MINUS", "KP_Multiply": "MULTIPLY",
    "KP_Divide": "DIVIDE", "KP_Decimal": "DECIMAL", "KP_Separator": "SEPARATOR",
}
for _i in range(1, 16):
    KEYSYM_MAP["F%d" % _i] = "F%d" % _i
for _i in range(10):
    KEYSYM_MAP["KP_%d" % _i] = "NUM%d" % _i


def describe(key, modifiers):
    """'Ctrl + Shift + S' 처럼 사람이 읽을 문자열."""
    labels = dict(MODIFIERS)
    parts = [labels.get(m, m) for m in (modifiers or [])]
    if key:
        pretty = None
        for _group, entries in KEY_GROUPS:
            for name, label in entries:
                if name == key:
                    pretty = label
                    break
            if pretty:
                break
        parts.append(pretty or key)
    if not parts:
        return u"(지정 안 됨)"
    return u" + ".join(parts)


def keysym_to_key(keysym, char):
    """tkinter keysym 을 OculiX 키 이름으로. 일반 문자는 그대로 돌려준다."""
    if keysym in KEYSYM_MAP:
        return KEYSYM_MAP[keysym]
    if len(keysym) == 1:
        return keysym.lower()
    if char and len(char) == 1 and char.isprintable():
        return char.lower()
    return None


class KeyPickerDialog(tk.Toplevel):

    def __init__(self, parent, key="", modifiers=None):
        tk.Toplevel.__init__(self, parent)
        self.title(u"키 선택")
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.resizable(False, False)

        self.result = None
        self.key = key or ""
        self.modifiers = list(modifiers or [])
        self._held = set()

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # --- 미리보기 ---
        ttk.Label(outer, text=u"만들어질 조합", style="Dim.TLabel").pack(anchor="w")
        self.preview = tk.Label(outer, text=u"", bg=theme.BG_DARKEST, fg=theme.ACCENT,
                                font=("Consolas", 15, "bold"), pady=10, padx=12,
                                anchor="w")
        self.preview.pack(fill="x", pady=(2, 10))

        # --- 조합키 ---
        mod_box = ttk.LabelFrame(outer, text=u"조합키", padding=8)
        mod_box.pack(fill="x")
        self._mod_vars = {}
        for name, label in MODIFIERS:
            var = tk.BooleanVar(value=name in self.modifiers)
            self._mod_vars[name] = var
            ttk.Checkbutton(mod_box, text=label, variable=var,
                            command=self._from_checkboxes).pack(side="left", padx=(0, 14))
        ttk.Label(mod_box, text=u"Win = Cmd = Meta (OculiX에서 같은 값)",
                  style="Dim.TLabel").pack(side="left")

        # --- 캡처 ---
        cap = ttk.LabelFrame(outer, text=u"① 키 캡처 — 가장 빠른 방법", padding=8)
        cap.pack(fill="x", pady=(10, 0))
        self.capture_area = tk.Label(
            cap, text=u"여기를 클릭한 뒤 원하는 키를 누르세요",
            bg=theme.BG_LIGHT, fg=theme.FG_DIM, pady=14,
            font=theme.FONT, relief="flat", cursor="hand2")
        self.capture_area.pack(fill="x")
        self.capture_area.bind("<Button-1>", lambda e: self._start_capture())
        self.capture_area.bind("<KeyPress>", self._on_key_press)
        self.capture_area.bind("<KeyRelease>", self._on_key_release)
        self.capture_area.bind("<FocusOut>", lambda e: self._end_capture())
        self.capture_area.configure(takefocus=True)
        ttk.Label(cap, text=u"Windows가 가로채는 키(Win 단독, PrintScreen, Alt+Tab)는 "
                            u"잡히지 않습니다. 아래 목록을 쓰세요.",
                  style="Dim.TLabel", wraplength=430).pack(anchor="w", pady=(6, 0))

        # --- 목록 ---
        pick = ttk.LabelFrame(outer, text=u"② 목록에서 고르기", padding=8)
        pick.pack(fill="both", expand=True, pady=(10, 0))
        lists = ttk.Frame(pick)
        lists.pack(fill="both", expand=True)

        self.group_list = tk.Listbox(lists, height=9, width=16, exportselection=False)
        theme.style_listbox(self.group_list)
        self.group_list.pack(side="left", fill="y")
        for group, _entries in KEY_GROUPS:
            self.group_list.insert("end", group)
        self.group_list.bind("<<ListboxSelect>>", lambda e: self._fill_keys())

        key_box = ttk.Frame(lists)
        key_box.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.key_list = tk.Listbox(key_box, height=9, exportselection=False)
        theme.style_listbox(self.key_list)
        key_sb = ttk.Scrollbar(key_box, orient="vertical", command=self.key_list.yview)
        self.key_list.configure(yscrollcommand=key_sb.set)
        self.key_list.pack(side="left", fill="both", expand=True)
        key_sb.pack(side="left", fill="y")
        self.key_list.bind("<<ListboxSelect>>", lambda e: self._from_list())
        self.key_list.bind("<Double-Button-1>", lambda e: self._confirm())
        self._current_keys = []

        # --- 버튼 ---
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text=u"지우기", command=self._clear).pack(side="left")
        ttk.Button(bar, text=u"확인", style="Accent.TButton",
                   command=self._confirm).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text=u"취소", command=self.destroy).pack(side="right")

        self._select_initial()
        self._refresh_preview()
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.capture_area.focus_set()
        self._start_capture()

    # ------------------------------------------------------------------ 캡처

    def _start_capture(self):
        self._held = set()
        self.capture_area.focus_set()
        self.capture_area.configure(
            text=u"● 키를 누르세요...", bg=theme.ACCENT_DARK, fg="#ffffff")

    def _end_capture(self):
        self.capture_area.configure(
            text=u"여기를 클릭한 뒤 원하는 키를 누르세요",
            bg=theme.BG_LIGHT, fg=theme.FG_DIM)

    def _on_key_press(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self._held.add(MODIFIER_KEYSYMS[keysym])
            self._show_pending()
            return "break"
        name = keysym_to_key(keysym, event.char)
        if not name:
            return "break"
        self.key = name
        self.modifiers = [m for m, _l in MODIFIERS if m in self._held]
        self._sync_checkboxes()
        self._refresh_preview()
        self._select_in_list(name)
        self.capture_area.configure(text=u"✔ %s" % describe(self.key, self.modifiers),
                                    bg=theme.ACCENT_DARK, fg="#ffffff")
        return "break"

    def _on_key_release(self, event):
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self._held.discard(MODIFIER_KEYSYMS[keysym])
        return "break"

    def _show_pending(self):
        held = [m for m, _l in MODIFIERS if m in self._held]
        if held:
            self.capture_area.configure(
                text=u"● %s + ..." % describe(None, held),
                bg=theme.ACCENT_DARK, fg="#ffffff")

    # ------------------------------------------------------------------ 목록

    def _fill_keys(self, select=None):
        selection = self.group_list.curselection()
        index = selection[0] if selection else 0
        _group, entries = KEY_GROUPS[index]
        self.key_list.delete(0, "end")
        self._current_keys = []
        for name, label in entries:
            self._current_keys.append(name)
            self.key_list.insert("end", u"%s   (%s)" % (label, name))
        if select and select in self._current_keys:
            pos = self._current_keys.index(select)
            self.key_list.selection_set(pos)
            self.key_list.see(pos)

    def _select_in_list(self, name):
        for gi, (_group, entries) in enumerate(KEY_GROUPS):
            if name in [n for n, _l in entries]:
                self.group_list.selection_clear(0, "end")
                self.group_list.selection_set(gi)
                self._fill_keys(select=name)
                return True
        return False

    def _select_initial(self):
        if self.key and self._select_in_list(self.key):
            return
        self.group_list.selection_set(0)
        self._fill_keys()

    def _from_list(self):
        selection = self.key_list.curselection()
        if not selection or selection[0] >= len(self._current_keys):
            return
        self.key = self._current_keys[selection[0]]
        self._refresh_preview()

    def _from_checkboxes(self):
        self.modifiers = [name for name, _l in MODIFIERS
                          if self._mod_vars[name].get()]
        self._refresh_preview()

    def _sync_checkboxes(self):
        for name, var in self._mod_vars.items():
            var.set(name in self.modifiers)

    def _clear(self):
        self.key = ""
        self.modifiers = []
        self._sync_checkboxes()
        self._refresh_preview()
        self._end_capture()

    def _refresh_preview(self):
        self.preview.configure(text=u"  " + describe(self.key, self.modifiers))

    def _confirm(self):
        if not self.key:
            self.preview.configure(text=u"  키를 먼저 고르세요", fg=theme.ERR)
            self.after(1200, lambda: (self.preview.configure(fg=theme.ACCENT),
                                      self._refresh_preview()))
            return
        self.result = {"key": self.key, "modifiers": list(self.modifiers)}
        self.destroy()


def ask_key(parent, key="", modifiers=None):
    """{'key': ..., 'modifiers': [...]} 또는 취소 시 None."""
    dialog = KeyPickerDialog(parent, key, modifiers)
    parent.wait_window(dialog)
    return dialog.result
