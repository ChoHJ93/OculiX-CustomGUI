# -*- coding: utf-8 -*-
"""편집기 다크 테마.

ttk 위젯은 'clam' 테마를 바탕으로 색을 다시 지정한다. clam이 색 지정을
가장 폭넓게 받아들이기 때문이다. Listbox/Text/Canvas/Menu 같은 순수 tk
위젯은 ttk 스타일이 닿지 않으므로 개별로 칠한다.

Windows에서 메뉴 '막대' 자체는 OS가 그리므로 완전히 칠할 수 없다.
드롭다운 메뉴는 칠해진다.
"""

import tkinter as tk
from tkinter import ttk


# ------------------------------------------------------------------ 팔레트

BG_DARKEST = "#151519"     # 캔버스, 로그 등 가장 어두운 바닥
BG_DARK = "#1c1c21"        # 패널 바닥
BG = "#232329"             # 기본 창 배경
BG_LIGHT = "#2b2b33"       # 입력 위젯, 카드
BG_LIGHTER = "#35353f"     # hover
BORDER = "#3a3a45"

FG = "#e6e6ec"             # 기본 글자
FG_DIM = "#9a9aa8"         # 보조 글자
FG_FAINT = "#6e6e7c"       # 더 흐린 글자

ACCENT = "#4c9aff"         # 선택/포커스
ACCENT_DARK = "#2f6dbf"
OK = "#5fd18c"
WARN = "#ffcc55"
ERR = "#ff7b72"

SELECT_BG = "#2f4a6d"
SELECT_FG = "#ffffff"

FONT = ("맑은 고딕", 9)
FONT_BOLD = ("맑은 고딕", 9, "bold")
FONT_TITLE = ("맑은 고딕", 10, "bold")
FONT_MONO = ("Consolas", 9)


def apply(root):
    """루트 창과 그 아래 ttk 스타일 전체에 다크 테마를 건다."""
    root.configure(bg=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".",
                    background=BG, foreground=FG,
                    fieldbackground=BG_LIGHT, bordercolor=BORDER,
                    lightcolor=BG_LIGHT, darkcolor=BG_DARK,
                    troughcolor=BG_DARK, focuscolor=ACCENT,
                    font=FONT)

    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=BG_DARK)

    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_TITLE)
    style.configure("Header.TLabel", background=BG_DARK, foreground=FG_DIM,
                    font=FONT_BOLD, padding=(8, 5))

    style.configure("TButton",
                    background=BG_LIGHT, foreground=FG,
                    bordercolor=BORDER, focusthickness=1, focuscolor=ACCENT,
                    padding=(8, 4), relief="flat")
    style.map("TButton",
              background=[("pressed", ACCENT_DARK), ("active", BG_LIGHTER),
                          ("disabled", BG_DARK)],
              foreground=[("disabled", FG_FAINT)])

    style.configure("Accent.TButton", background=ACCENT_DARK, foreground="#ffffff")
    style.map("Accent.TButton",
              background=[("pressed", "#24568f"), ("active", ACCENT)])

    style.configure("TMenubutton",
                    background=BG_LIGHT, foreground=FG,
                    bordercolor=BORDER, padding=(8, 4), relief="flat", arrowcolor=FG)
    style.map("TMenubutton", background=[("active", BG_LIGHTER)])

    style.configure("TEntry",
                    fieldbackground=BG_LIGHT, foreground=FG,
                    bordercolor=BORDER, insertcolor=FG, padding=3)
    style.map("TEntry",
              bordercolor=[("focus", ACCENT)],
              fieldbackground=[("disabled", BG_DARK)])

    style.configure("TCombobox",
                    fieldbackground=BG_LIGHT, background=BG_LIGHT,
                    foreground=FG, arrowcolor=FG, bordercolor=BORDER, padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_LIGHT)],
              bordercolor=[("focus", ACCENT)])
    # 콤보박스 드롭다운은 tk 리스트박스라 옵션 데이터베이스로만 칠해진다
    root.option_add("*TCombobox*Listbox.background", BG_LIGHT)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", SELECT_FG)

    style.configure("TCheckbutton", background=BG, foreground=FG,
                    indicatorcolor=BG_LIGHT, focuscolor=ACCENT)
    style.map("TCheckbutton",
              background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT)])

    style.configure("TLabelframe", background=BG, foreground=FG_DIM,
                    bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=FG_DIM,
                    font=FONT_BOLD)

    style.configure("TPanedwindow", background=BG_DARKEST)
    style.configure("Sash", background=BG_DARKEST, gripcount=0)

    style.configure("TSeparator", background=BORDER)

    style.configure("Treeview",
                    background=BG_LIGHT, fieldbackground=BG_LIGHT,
                    foreground=FG, bordercolor=BORDER, rowheight=22)
    style.map("Treeview",
              background=[("selected", SELECT_BG)],
              foreground=[("selected", SELECT_FG)])
    style.configure("Treeview.Heading",
                    background=BG_DARK, foreground=FG_DIM,
                    relief="flat", font=FONT_BOLD, padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", BG_LIGHTER)])

    style.configure("Vertical.TScrollbar",
                    background=BG_LIGHT, troughcolor=BG_DARK,
                    bordercolor=BG_DARK, arrowcolor=FG_DIM, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BG_LIGHTER)])
    style.configure("Horizontal.TScrollbar",
                    background=BG_LIGHT, troughcolor=BG_DARK,
                    bordercolor=BG_DARK, arrowcolor=FG_DIM, relief="flat")
    style.map("Horizontal.TScrollbar", background=[("active", BG_LIGHTER)])

    style.configure("TNotebook", background=BG_DARK, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=BG_DARK, foreground=FG_DIM,
                    padding=(12, 5), bordercolor=BORDER)
    style.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", FG)])

    return style


def style_listbox(widget):
    widget.configure(background=BG_LIGHT, foreground=FG,
                     selectbackground=SELECT_BG, selectforeground=SELECT_FG,
                     highlightthickness=0, borderwidth=0, relief="flat",
                     activestyle="none", font=FONT)


def style_text(widget, mono=True):
    widget.configure(background=BG_DARKEST, foreground=FG,
                     insertbackground=FG, selectbackground=SELECT_BG,
                     selectforeground=SELECT_FG, highlightthickness=0,
                     borderwidth=0, relief="flat",
                     font=FONT_MONO if mono else FONT)


def style_menu(menu):
    menu.configure(background=BG_LIGHT, foreground=FG,
                   activebackground=SELECT_BG, activeforeground=SELECT_FG,
                   borderwidth=0, relief="flat", font=FONT)


def style_canvas(widget, background=BG_DARKEST):
    widget.configure(background=background, highlightthickness=0,
                     borderwidth=0, relief="flat")
