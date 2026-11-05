# -*- coding: utf-8 -*-
"""OculiX 매크로 편집기.

코드를 쓰지 않고 매크로를 만든다. 저장 결과는 Macros/<이름>/macro.json 이고
Scripts/Runner/RunMacro.sikuli 가 그대로 실행한다.

실행: python macro_editor.py
"""

import json
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog


def _flatten_tree(steps):
    """트리 형식 매크로의 중첩 단계를 평평하게 편다."""
    out = []
    for step in steps or []:
        out.append(step)
        for key in ("then", "else", "steps"):
            out.extend(_flatten_tree(step.get(key)))
    return out

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJECT = r"D:\Programming\Oculix-Automation"
MACROS_DIR = os.path.join(PROJECT, "Macros")

# 선택 오버레이와 편집기 창을 치운 뒤 화면이 다시 그려질 때까지 기다리는 시간.
# 이 대기가 없으면 아직 지워지지 않은 창이 캡처에 그대로 찍힌다.
CAPTURE_SETTLE_SEC = 0.35
sys.path.insert(0, os.path.join(PROJECT, "Scripts", "Common"))

# find_macro_callers 가 감시 목록(handlers)의 참조를 돌려줄 때 노드 id 대신
# 쓰는 자리 표시. 노드 id 는 "n1" 꼴이라 겹치지 않는다.
_HANDLER_SLOT = u"감시목록[%d]"


def _crash_log(text):
    """시작 중 죽었을 때 흔적을 남긴다.

    pythonw 로 띄우면 콘솔이 없어서 traceback 이 어디에도 남지 않는다.
    "창이 안 뜨는데 이유를 알 수 없는" 상황을 막으려고 파일로 적는다.
    """
    import tempfile
    # editor-error.log 를 쓰지 않는다. 실행기가 그 이름을 stderr 로 열어 두면
    # 편집기가 떠 있는 내내 잠겨서 여기서 쓸 수 없다.
    targets = [os.path.join(PROJECT, "Logs", "editor-crash.log"),
               os.path.join(tempfile.gettempdir(), "oculix-editor-crash.log")]
    for path in targets:
        try:
            folder = os.path.dirname(path)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(text)
            return path
        except Exception:
            continue              # 다음 후보로
    return None                   # 로그조차 못 쓰면 더 할 수 있는 게 없다


def _crash_report(stage):
    import datetime
    import traceback
    return (u"\n===== %s %s =====\n"
            u"python      : %s\n"
            u"실행파일    : %s\n"
            u"작업디렉터리: %s\n"
            u"%s\n" % (
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), stage,
                sys.version.replace("\n", " "), sys.executable, os.getcwd(),
                traceback.format_exc()))


# import 는 main() 보다 먼저 실행되므로 여기서 따로 감싼다.
try:
    import docking
    import graph_model
    import hotkey
    import imagecache
    import imagepicker
    import keypicker
    import model
    import node_canvas
    import notify
    import pickers
    import project_panel
    import runner
    import runlog
    import schema
    import screenutil
    import settings
    import theme
except Exception:
    _crash_log(_crash_report(u"편집기 import 실패"))
    raise


PAUSE_LABEL = u"⏸ 일시정지 (F6)"
RESUME_LABEL = u"▶ 재개 (F6)"


def _beep(frequency):
    """짧은 소리. 소리를 못 내도 실행에는 영향이 없어야 한다."""
    try:
        import winsound
        winsound.Beep(frequency, 120)
    except Exception:
        pass


# ============================================================ 조건 편집기

class ConditionEditor(ttk.Frame):
    """조건 하나를 편집한다. not/all/any 때문에 자기 자신을 재귀적으로 쓴다."""

    def __init__(self, master, app, get_cond, set_cond, depth=0):
        ttk.Frame.__init__(self, master)
        self.app = app
        self.get_cond = get_cond
        self.set_cond = set_cond
        self.depth = depth
        self.rebuild()

    def rebuild(self):
        # 조건 종류를 바꾸면 아래 칸들이 통째로 갈린다. build_properties 와
        # 같은 이유로, 부수기 전에 아직 안 들어간 입력을 먼저 반영한다.
        self.app.flush_property_edits()
        for child in self.winfo_children():
            child.destroy()

        cond = self.get_cond() or {}
        if not isinstance(cond, dict):
            cond = {}

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text=u"조건").pack(side="left")

        types = list(schema.CONDITION_TYPES.items())
        labels = [spec["label"] for _t, spec in types]
        keys = [t for t, _spec in types]
        combo = ttk.Combobox(header, values=labels, state="readonly", width=18)
        current = cond.get("type")
        if current in keys:
            combo.current(keys.index(current))
        combo.pack(side="left", padx=6)

        def on_type(_e=None, keys=keys):
            new_type = keys[combo.current()]
            if new_type != (self.get_cond() or {}).get("type"):
                self.set_cond(schema.new_condition(new_type))
                self.rebuild()
                self.app.refresh_tree_labels()
        combo.bind("<<ComboboxSelected>>", on_type)

        ctype = cond.get("type")
        if not ctype:
            return

        body = ttk.Frame(self)
        body.pack(fill="x", padx=(14, 0), pady=(4, 0))

        for field in schema.CONDITION_TYPES[ctype]["fields"]:
            if not self.app.field_visible(field):
                continue
            if field["type"] == "condition":
                sub = ttk.LabelFrame(body, text=field["label"])
                sub.pack(fill="x", pady=3)
                ConditionEditor(
                    sub, self.app,
                    lambda f=field: (self.get_cond() or {}).get(f["name"]),
                    lambda v, f=field: self._set_sub(f["name"], v),
                    self.depth + 1).pack(fill="x", padx=6, pady=4)
            elif field["type"] == "condition_list":
                self._build_list(body, field)
            else:
                self.app.build_field(body, field, self.get_cond(),
                                     on_change=self.app.refresh_tree_labels)

    def _set_sub(self, name, value):
        cond = self.get_cond() or {}
        cond[name] = value
        self.set_cond(cond)

    def _build_list(self, parent, field):
        cond = self.get_cond() or {}
        items = cond.setdefault(field["name"], [])

        frame = ttk.LabelFrame(parent, text=field["label"])
        frame.pack(fill="x", pady=3)

        listbox = tk.Listbox(frame, height=max(2, min(6, len(items) + 1)))
        listbox.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        for item in items:
            listbox.insert("end", schema.describe_condition(item))

        buttons = ttk.Frame(frame)
        buttons.pack(side="left", padx=4)

        def add():
            new = schema.new_condition("imageExists")
            if self._edit_dialog(new):
                items.append(new)
                self.app.mark_dirty()
                self.rebuild()

        def edit():
            sel = listbox.curselection()
            if not sel:
                return
            index = sel[0]
            if self._edit_dialog(items[index]):
                self.app.mark_dirty()
                self.rebuild()

        def remove():
            sel = listbox.curselection()
            if not sel:
                return
            items.pop(sel[0])
            self.app.mark_dirty()
            self.rebuild()

        ttk.Button(buttons, text=u"추가", width=6, command=add).pack(pady=1)
        ttk.Button(buttons, text=u"편집", width=6, command=edit).pack(pady=1)
        ttk.Button(buttons, text=u"삭제", width=6, command=remove).pack(pady=1)

    def _edit_dialog(self, cond):
        dialog = tk.Toplevel(self)
        dialog.title(u"조건 편집")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        holder = {"cond": cond}

        editor = ConditionEditor(
            dialog, self.app,
            lambda: holder["cond"],
            lambda v: holder.update(cond=v),
            self.depth + 1)
        editor.pack(fill="both", expand=True, padx=10, pady=10)

        result = {"ok": False}

        def confirm():
            # 먼저 사본을 뜬다. 종류를 바꾸지 않으면 set_cond 가 불리지 않아
            # holder["cond"] 가 cond 와 **같은 객체**로 남는다. 그 상태에서
            # cond.clear() 를 하면 원본까지 비워져 빈 조건 {} 이 되고,
            # type 이 없으니 'AND/OR 조건들' 목록에 'None' 으로 뜨면서
            # 실행하면 'unknown condition type: None' 으로 죽는다.
            # 종류를 바꾸면 새 dict 가 들어와서 멀쩡했던 탓에, 기본값
            # (이미지가 있으면) 그대로 추가할 때만 터졌다.
            picked = dict(holder["cond"])
            cond.clear()
            cond.update(picked)
            result["ok"] = True
            dialog.destroy()

        bar = ttk.Frame(dialog)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text=u"확인", command=confirm).pack(side="right", padx=3)
        ttk.Button(bar, text=u"취소", command=dialog.destroy).pack(side="right")
        self.wait_window(dialog)
        return result["ok"]


# ============================================================ 메인 앱

class MacroEditorApp(object):

    def __init__(self, root):
        self.root = root
        self.macro = model.Macro()
        self.graph = None                 # 그래프 형식일 때만 채워진다
        self.mode = "tree"                # "tree" | "graph"
        self.item_paths = {}
        self.path_items = {}
        self.current_path = None
        self.current_step_obj = None      # 속성 패널이 편집 중인 dict
        self.job = None
        self.runlog = None                # 실행 중일 때만 열려 있는 로그 파일
        self.log_queue = queue.Queue()

        # 속성 패널에서 아직 반영되지 않았을 수 있는 입력칸들.
        # (아직 안 넣었나? 함수, 넣는 함수) 짝을 담는다. flush_property_edits 참조.
        self._prop_commits = []
        self._flushing_props = False

        # 패널은 도킹 매니저가 만들 때 채워진다. 그 전에 참조될 수 있으니 비워 둔다.
        self.dock = None
        self.library_list = None
        self.submacro_list = None
        self.submacro_header = None
        self.submacro_parent_btn = None
        self._submacro_refs = []
        self.project = None
        self.canvas_view = None
        self.tree_view = None
        self.tree = None
        self.prop_frame = None
        self.resume_button = None
        self.pause_button = None
        self.paused = False               # 일시정지를 요청한 상태
        self.pause_hotkey = None          # 실행 중에만 등록한다 (hotkey 참조)
        self.log = None
        self.view_label = None
        self._library_refs = []
        self._drag_ref = None
        self._drag_active = False
        self._drag_ghost = None

        self.config = settings.load()
        # 실행이 끝났을 때 Windows 알림을 띄울지. 메뉴의 체크 항목과 묶인다.
        self.notify_var = tk.BooleanVar(
            value=bool(self.config.get("notify_on_done", True)))
        self._log_buffer = []
        self._saved_expanded = self.config.get("expanded") or []
        self.macro = model.Macro(graph_model.blank(u"새 매크로"))

        root.title(u"OculiX 매크로 편집기")
        geometry, window_moved = screenutil.fit_geometry(
            self.config.get("geometry") or "1320x860")
        root.geometry(geometry)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_menu()
        self._build_toolbar()
        self._build_status()          # 아래쪽에 먼저 붙여 둔다
        self._build_body()
        self.dock.set_layout(self.config.get("layout"))
        if window_moved:
            self.log_line(u"저장된 창 위치가 지금 화면 밖이라 주 모니터로 "
                          u"옮겼습니다 (모니터 구성이 바뀐 경우)", "info")

        self.root.after(80, self._drain_log)
        self._check_environment()

    # --------------------------------------------------------------- 레이아웃

    def _build_menu(self):
        bar = tk.Menu(self.root)
        theme.style_menu(bar)

        m_file = tk.Menu(bar, tearoff=0)
        theme.style_menu(m_file)
        m_file.add_command(label=u"새 매크로", accelerator="Ctrl+N", command=self.new_macro)
        m_file.add_command(label=u"열기...", accelerator="Ctrl+O", command=self.open_macro)
        m_file.add_separator()
        m_file.add_command(label=u"저장", accelerator="Ctrl+S", command=self.save_macro)
        m_file.add_command(label=u"다른 이름으로 저장...", command=self.save_macro_as)
        m_file.add_separator()
        m_file.add_command(label=u"끝내기", command=self.on_close)
        bar.add_cascade(label=u"파일", menu=m_file)

        m_tools = tk.Menu(bar, tearoff=0)
        theme.style_menu(m_tools)
        m_tools.add_command(label=u"매크로 검사", command=self.validate_macro)
        m_tools.add_command(label=u"매크로 설정...", command=self.edit_settings)
        m_tools.add_command(label=u"감시 설정...", command=self.edit_watch)
        m_tools.add_separator()
        m_tools.add_command(label=u"그래프로 변환 (트리 형식 → 노드)",
                            command=self.convert_to_graph)
        m_tools.add_command(label=u"노드 자동 정렬",
                            command=lambda: self.canvas_view.auto_layout()
                            if self.mode == "graph" else None)
        m_tools.add_command(label=u"노드 보기 초기화",
                            command=lambda: self.canvas_view.reset_view()
                            if self.mode == "graph" else None)
        m_tools.add_separator()
        m_tools.add_command(label=u"좌표계 대조 (OculiX와 비교)",
                            command=self.verify_coordinates)
        m_tools.add_command(label=u"화면 정보", command=self.show_screen_info)
        m_tools.add_separator()
        m_tools.add_command(label=u"실행 로그 폴더 열기",
                            command=self.open_log_folder)
        m_tools.add_checkbutton(
            label=u"실행이 끝나면 Windows 알림",
            variable=self.notify_var, command=self._on_notify_toggle,
            state="normal" if notify.available() else "disabled")
        bar.add_cascade(label=u"도구", menu=m_tools)

        m_view = tk.Menu(bar, tearoff=0)
        theme.style_menu(m_view)
        for key, title in ((u"library", u"매크로 라이브러리"),
                           (u"submacros", u"하위 매크로"), (u"project", u"프로젝트"),
                           (u"graph", u"노드 그래프"), (u"properties", u"속성"),
                           (u"log", u"실행 로그")):
            sub = tk.Menu(m_view, tearoff=0)
            theme.style_menu(sub)
            for area in docking.AREAS:
                sub.add_command(
                    label=docking.AREA_LABELS[area],
                    command=lambda k=key, a=area: self.dock.move_panel(k, a))
            m_view.add_cascade(label=u"%s 위치" % title, menu=sub)
        m_view.add_separator()
        m_view.add_command(label=u"레이아웃 초기화", command=self.reset_layout)
        m_view.add_command(label=u"레이아웃 지금 저장", command=self.save_settings)
        bar.add_cascade(label=u"보기", menu=m_view)

        self.root.config(menu=bar)
        self.root.bind("<Control-n>", lambda e: self.new_macro())
        self.root.bind("<Control-o>", lambda e: self.open_macro())
        self.root.bind("<Control-s>", lambda e: self.save_macro())
        self.root.bind("<F5>", lambda e: self.run_macro())
        self.root.bind("<Shift-F5>", lambda e: self.run_from_selected_node())
        self.root.bind("<Control-F5>", lambda e: self.resume_macro())
        # 전역 단축키가 등록돼 있으면 F6 은 여기까지 오지 않는다. 다른 프로그램이
        # 이 키를 선점해 등록이 실패했을 때 편집기 안에서라도 쓰게 하는 예비다.
        self.root.bind("<F6>", lambda e: self.toggle_pause())

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill="x")

        add_button = ttk.Menubutton(bar, text=u"단계 추가 ▾")
        menu = tk.Menu(add_button, tearoff=0)
        theme.style_menu(menu)
        for group, entries in schema.grouped_types().items():
            sub = tk.Menu(menu, tearoff=0)
            theme.style_menu(sub)
            for stype, label in entries:
                sub.add_command(label=label,
                                command=lambda t=stype: self.add_step(t))
            menu.add_cascade(label=group, menu=sub)
        add_button["menu"] = menu
        add_button.pack(side="left")

        # 삭제 / 위로 / 아래로 는 버튼으로 쓰지 않는다.
        # 노드는 우클릭이나 Delete 키로, 트리는 우클릭 메뉴로 처리한다.
        for text, command in ((u"복제 (Ctrl+D)", self.duplicate_step),
                              (u"사용/해제", self.toggle_step)):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(6, 0))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        self.run_button = ttk.Button(bar, text=u"▶ 실행 (F5)", command=self.run_macro)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(bar, text=u"■ 중지", command=self.stop_macro,
                                      state="disabled")
        self.stop_button.pack(side="left", padx=(6, 0))
        self.pause_button = ttk.Button(bar, text=PAUSE_LABEL,
                                       command=self.toggle_pause,
                                       state="disabled")
        self.pause_button.pack(side="left", padx=(6, 0))
        # 지난 실행이 실패로 끝났고 지나온 체크포인트가 있을 때만 켜진다.
        self.resume_button = ttk.Button(bar, text=u"⏭ 이어서 실행 (Ctrl+F5)",
                                        command=self.resume_macro,
                                        state="disabled")
        self.resume_button.pack(side="left", padx=(6, 0))

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text=u"⌖ 시작 노드로 이동",
                   command=self.goto_entry_node).pack(side="left")

    def _build_body(self):
        """패널을 도킹 매니저에 등록한다. 실제 배치는 저장된 레이아웃을 따른다."""
        container = ttk.Frame(self.root, padding=(8, 0, 8, 6))
        container.pack(fill="both", expand=True)

        self.dock = docking.DockManager(container,
                                        on_change=self._after_dock_change,
                                        on_before_rebuild=self._before_dock_rebuild)
        self.dock.register("library", u"매크로 라이브러리", self._panel_library,
                           save_state=self._save_library_state,
                           restore_state=self._restore_library_state)
        self.dock.register("submacros", u"하위 매크로", self._panel_submacros)
        self.dock.register("project", u"프로젝트", self._panel_project,
                           save_state=self._save_project_state,
                           restore_state=self._restore_project_state)
        self.dock.register("graph", u"노드 그래프", self._panel_graph,
                           save_state=self._save_graph_state,
                           restore_state=self._restore_graph_state)
        self.dock.register("properties", u"속성", self._panel_properties)
        self.dock.register("log", u"실행 로그", self._panel_log,
                           save_state=self._save_log_state,
                           restore_state=self._restore_log_state)

    # ------------------------------------------------------------ 패널 내용

    def _panel_library(self, parent):
        lib_box = ttk.Frame(parent)
        lib_box.pack(fill="both", expand=True)
        self.library_list = tk.Listbox(lib_box, exportselection=False)
        theme.style_listbox(self.library_list)
        lib_sb = ttk.Scrollbar(lib_box, orient="vertical",
                               command=self.library_list.yview)
        self.library_list.configure(yscrollcommand=lib_sb.set)
        self.library_list.pack(side="left", fill="both", expand=True)
        lib_sb.pack(side="left", fill="y")
        # 더블클릭은 편집하러 여는 동작. 호출 노드는 끌어다 놓거나 버튼/우클릭으로.
        self.library_list.bind("<Double-Button-1>",
                               lambda e: self.open_selected_library())
        self.library_list.bind("<Button-3>", self._on_library_right_click)
        self.library_list.bind("<ButtonPress-1>", self._on_library_press)
        self.library_list.bind("<B1-Motion>", self._on_library_drag)
        self.library_list.bind("<ButtonRelease-1>", self._on_library_drop)

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text=u"호출 노드 추가", style="Accent.TButton",
                   command=self.insert_call_node).pack(fill="x")
        self.refresh_library()

    def _panel_submacros(self, parent):
        """하위 매크로 패널 - UE 블루프린트의 '함수' 목록에 해당한다.

        지금 열린 매크로 가족(부모 + 하위들)만 보인다. 라이브러리와 달리
        여기 매크로들은 부모와 형제만 호출할 수 있는 사유물이다.
        """
        self.submacro_header = ttk.Label(parent, text=u"", style="Dim.TLabel",
                                         wraplength=280, justify="left")
        self.submacro_header.pack(fill="x", pady=(0, 2))
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True)
        self.submacro_list = tk.Listbox(box, exportselection=False)
        theme.style_listbox(self.submacro_list)
        sb = ttk.Scrollbar(box, orient="vertical",
                           command=self.submacro_list.yview)
        self.submacro_list.configure(yscrollcommand=sb.set)
        self.submacro_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        # 라이브러리와 같은 조작감: 더블클릭 = 열기, 끌어다 놓기 = 호출 노드.
        # 드래그/드롭 처리는 _drag_ref 만 쓰므로 라이브러리 것을 그대로 쓴다.
        self.submacro_list.bind("<Double-Button-1>",
                                lambda e: self.open_selected_submacro())
        self.submacro_list.bind("<Button-3>", self._on_submacro_right_click)
        self.submacro_list.bind("<ButtonPress-1>", self._on_submacro_press)
        self.submacro_list.bind("<B1-Motion>", self._on_library_drag)
        self.submacro_list.bind("<ButtonRelease-1>", self._on_library_drop)

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(4, 0))
        self.submacro_parent_btn = ttk.Button(buttons, text=u"⬑ 부모 매크로 열기",
                                              command=self.open_parent_macro)
        self.submacro_parent_btn.pack(fill="x", pady=(0, 2))
        ttk.Button(buttons, text=u"새 하위 매크로",
                   command=self.new_submacro).pack(fill="x")
        ttk.Button(buttons, text=u"호출 노드 추가", style="Accent.TButton",
                   command=self.insert_submacro_call).pack(fill="x", pady=(2, 0))
        self.refresh_submacros()

    def _panel_project(self, parent):
        self.project = project_panel.ProjectPanel(parent, self, MACROS_DIR)
        self.project.pack(fill="both", expand=True)
        if self._saved_expanded:
            self.project.set_expanded(self._saved_expanded)
            self.project.refresh()

    def _panel_graph(self, parent):
        self.view_label = ttk.Label(parent, text=u"", style="Dim.TLabel")
        self.canvas_view = node_canvas.NodeCanvas(parent, self)
        self.tree_view = ttk.Frame(parent)
        self.tree = ttk.Treeview(self.tree_view, columns=("state",),
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text=u"단계")
        self.tree.heading("state", text=u"사용")
        self.tree.column("state", width=48, anchor="center", stretch=False)
        vsb = ttk.Scrollbar(self.tree_view, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<Delete>", lambda e: self.delete_step())
        # Ctrl+D 는 캔버스와 트리 각각에 건다. 루트에 걸면 속성칸에 글자를
        # 치는 중에도 복제가 일어난다.
        self.tree.bind("<Control-d>", lambda e: (self.duplicate_step(), "break")[1])
        self.tree.bind("<Control-D>", lambda e: (self.duplicate_step(), "break")[1])
        self.tree.tag_configure("disabled", foreground=theme.FG_FAINT)
        self.tree.tag_configure("container", foreground=theme.ACCENT)
        if self.macro is not None:
            self.apply_mode()

    def _panel_properties(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        theme.style_canvas(canvas, theme.BG)
        pscroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.prop_frame = ttk.Frame(canvas)
        self.prop_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._prop_window = canvas.create_window((0, 0), window=self.prop_frame,
                                                 anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._prop_window, width=e.width))
        canvas.configure(yscrollcommand=pscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        pscroll.pack(side="left", fill="y")
        self.build_properties()

    def _panel_log(self, parent):
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=8, wrap="none", state="disabled")
        theme.style_text(self.log)
        lsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="left", fill="y")
        self.log.tag_configure("err", foreground=theme.ERR)
        self.log.tag_configure("ok", foreground=theme.OK)
        self.log.tag_configure("info", foreground=theme.ACCENT)
        for text, tag in self._log_buffer:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n", tag or ())
            self.log.configure(state="disabled")
        self.log.see("end")

    # ------------------------- 레이아웃이 바뀔 때 유지할 상태 (부모 변경 불가)

    def _save_library_state(self):
        try:
            selection = self.library_list.curselection()
            return {"selection": selection[0] if selection else None}
        except Exception:
            return None

    def _restore_library_state(self, state):
        index = (state or {}).get("selection")
        if index is not None and index < self.library_list.size():
            self.library_list.selection_set(index)

    def _save_project_state(self):
        try:
            return {"expanded": self.project.get_expanded(),
                    "selected": self.project.selected_path()}
        except Exception:
            return None

    def _restore_project_state(self, state):
        if not state:
            return
        self.project.set_expanded(state.get("expanded") or [])
        self.project.refresh(state.get("selected"))

    def _save_graph_state(self):
        try:
            return {"zoom": self.canvas_view.zoom,
                    "origin": list(self.canvas_view.origin),
                    "selected": self.canvas_view.selected_node,
                    "selected_all": list(self.canvas_view.selected_nodes)}
        except Exception:
            return None

    def _restore_graph_state(self, state):
        if not state:
            return
        self.canvas_view.zoom = state.get("zoom", 1.0)
        self.canvas_view.origin = list(state.get("origin") or [40.0, 40.0])
        self.canvas_view.selected_node = state.get("selected")
        # 다중 선택도 되살린다. selected_node 대입이 선택을 하나로 줄이므로 뒤에 온다.
        if state.get("selected_all"):
            self.canvas_view.set_selection(state["selected_all"],
                                           active=state.get("selected"),
                                           notify=False)
        self.canvas_view.redraw()

    def _save_log_state(self):
        return {"lines": list(self._log_buffer)}

    def _restore_log_state(self, _state):
        return

    def _before_dock_rebuild(self):
        """패널이 파괴되기 직전. 남아 있는 위젯 참조를 전부 비운다.

        비우지 않으면 다시 짓는 도중에 이미 파괴된 위젯을 건드려
        'bad window path name' 오류가 난다.
        """
        self.library_list = None
        self.submacro_list = None
        self.submacro_header = None
        self.submacro_parent_btn = None
        self.project = None
        self.canvas_view = None
        self.tree_view = None
        self.tree = None
        self.prop_frame = None
        self.log = None
        self.view_label = None

    def _after_dock_change(self):
        """패널이 옮겨진 뒤. 제목줄 문구를 현재 상태에 맞춘다."""
        self._sync_view_title()

    def _build_status(self):
        self.status = tk.StringVar(value=u"준비")
        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w", padding=(8, 3)).pack(fill="x", side="bottom")

    def _check_environment(self):
        ok, missing = runner.available()
        if not ok:
            self.log_line(u"경고: 다음 파일이 없어 실행이 불가능합니다: %s"
                          % ", ".join(missing), "err")
        self.log_line(screenutil.describe(), "info")

    # ------------------------------------------------------- 매크로 라이브러리

    @staticmethod
    def _ref_label(ref, name):
        return ref if name == ref else u"%s  —  %s" % (ref, name)

    def available_macros(self):
        """Macros 폴더 아래의 매크로 목록 [(참조이름, 표시이름)]."""
        try:
            return [(ref, name)
                    for ref, name, _path in graph_model.list_macros(MACROS_DIR)]
        except Exception:
            return []

    def refresh_project(self):
        if self.project is not None:
            self.project.refresh()

    def refresh_library(self):
        self._library_refs = self.available_macros()
        if self.library_list is None:
            return
        self.library_list.delete(0, "end")
        for ref, name in self._library_refs:
            mark = u"● " if self._is_self_reference(ref) else u"   "
            # Macros 루트에 그냥 놓인 파일만 경고한다. 자기 폴더 안에 있으면
            # 파일 이름이 macro.json 이 아니어도 이미지 경로는 정상이다.
            suffix = u"   ⚠ Macros 루트" if self._is_loose_in_root(ref) else u""
            self.library_list.insert("end",
                                     mark + self._ref_label(ref, name) + suffix)
        if not self._library_refs:
            self.library_list.insert("end", u"   (Macros 폴더가 비어 있습니다)")

    def _selected_library_ref(self):
        selection = self.library_list.curselection()
        if not selection or not self._library_refs:
            return None
        index = selection[0]
        if index >= len(self._library_refs):
            return None
        return self._library_refs[index][0]

    def insert_call_node(self):
        ref = self._selected_library_ref()
        if not ref:
            self.status.set(u"라이브러리에서 매크로를 먼저 고르세요")
            return
        if self.mode != "graph":
            messagebox.showinfo(u"노드 모드 필요",
                                u"호출 노드는 노드 그래프에서만 추가할 수 있습니다.\n"
                                u"[도구 > 그래프로 변환]을 먼저 하세요.")
            return
        if os.path.normcase(os.path.join(MACROS_DIR, ref)) == \
                os.path.normcase(self.macro.folder or ""):
            if not messagebox.askyesno(
                    u"자기 자신 호출",
                    u"지금 편집 중인 매크로를 호출하려 합니다.\n"
                    u"순환 호출이 되어 실행이 중단됩니다. 그래도 추가할까요?"):
                return
        node = self.canvas_view.add_node("call")
        node["macro"] = ref
        node["label"] = ref.split("/")[-1]
        self.canvas_view.redraw()
        self.on_node_selected(node["id"])
        self.status.set(u"호출 노드 추가: %s" % ref)

    def open_selected_library(self):
        ref = self._selected_library_ref()
        if not ref:
            return
        path = self._macro_path(ref)
        if not os.path.isfile(path):
            self.log_line(u"매크로 파일이 없습니다: %s" % path, "err")
            return
        if not self._confirm_discard():
            return
        try:
            self.macro = model.Macro.load(path)
        except Exception as exc:
            messagebox.showerror(u"열기 실패", u"%s\n\n%s" % (path, exc))
            return
        self.current_path = None
        self.apply_mode()
        self.focus_opened_macro()
        self.status.set(u"열림: %s" % path)

    # ------------------------------------------------ 라이브러리 끌어다 놓기

    def _on_library_press(self, event):
        index = self.library_list.nearest(event.y)
        if index < 0 or index >= len(self._library_refs):
            self._drag_ref = None
            return
        self.library_list.selection_clear(0, "end")
        self.library_list.selection_set(index)
        self._drag_ref = self._library_refs[index][0]
        self._drag_active = False

    def _on_library_drag(self, event):
        if not self._drag_ref:
            return
        if not self._drag_active:
            self._drag_active = True
            self._drag_ghost = tk.Toplevel(self.root)
            self._drag_ghost.overrideredirect(True)
            self._drag_ghost.attributes("-topmost", True)
            self._drag_ghost.attributes("-alpha", 0.85)
            tk.Label(self._drag_ghost, text=u"  ⟶  %s  " % self._drag_ref,
                     bg=theme.ACCENT_DARK, fg="#ffffff",
                     font=theme.FONT_BOLD, padx=6, pady=3).pack()
        self._drag_ghost.geometry("+%d+%d" % (event.x_root + 14, event.y_root + 12))

    def _on_library_drop(self, event):
        ref = self._drag_ref
        active = self._drag_active
        self._drag_ref = None
        self._drag_active = False
        if self._drag_ghost is not None:
            self._drag_ghost.destroy()
            self._drag_ghost = None
        if not ref or not active:
            return
        target = self.root.winfo_containing(event.x_root, event.y_root)
        if target is None:
            return
        # 캔버스(또는 그 안의 자식) 위에 놓았는지 확인
        widget = target
        on_canvas = False
        while widget is not None:
            if widget is self.canvas_view.canvas:
                on_canvas = True
                break
            widget = getattr(widget, "master", None)
        if not on_canvas:
            return
        if self.mode != "graph":
            self.status.set(u"노드 모드에서만 호출 노드를 놓을 수 있습니다")
            return
        if self._is_self_reference(ref) and not messagebox.askyesno(
                u"자기 자신 호출",
                u"편집 중인 매크로를 호출하려 합니다.\n"
                u"순환 호출이 되어 실행이 중단됩니다. 그래도 추가할까요?"):
            return
        node = self.canvas_view.drop_call_node(ref, event.x_root, event.y_root)
        if node is not None:
            self.status.set(u"호출 노드 추가: %s" % ref)

    def _is_self_reference(self, ref):
        if not self.macro.path:
            return False
        return os.path.normcase(os.path.abspath(self._macro_path(ref))) == \
            os.path.normcase(os.path.abspath(self.macro.path))

    # ---------------------------------------------- 라이브러리 우클릭 메뉴

    def _on_library_right_click(self, event):
        index = self.library_list.nearest(event.y)
        if index < 0 or index >= len(self._library_refs):
            return
        self.library_list.selection_clear(0, "end")
        self.library_list.selection_set(index)
        ref = self._library_refs[index][0]

        menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(menu)
        menu.add_command(label=u"편집 (열기)",
                         command=lambda: self.open_macro_ref(ref))
        menu.add_command(label=u"호출 노드로 추가",
                         command=self.insert_call_node)
        menu.add_separator()
        menu.add_command(label=u"이름 변경...",
                         command=lambda: self.rename_macro(ref))
        menu.add_command(label=u"복제", command=lambda: self.duplicate_macro(ref))
        menu.add_command(label=u"삭제", command=lambda: self.delete_macro(ref))
        if self._is_loose_in_root(ref):
            menu.add_separator()
            menu.add_command(label=u"폴더로 정리 (권장)",
                             command=lambda: self.foldarize_macro(ref))
        menu.add_separator()
        menu.add_command(label=u"탐색기에서 열기",
                         command=lambda: project_panel.ProjectPanel._reveal(
                             self._macro_path(ref)))
        menu.tk_popup(event.x_root, event.y_root)

    def foldarize_macro(self, ref):
        """Macros 루트에 놓인 파일 하나짜리 매크로를 자기 폴더로 옮긴다.

        이미지를 매크로 옆에 두려면 폴더형이어야 한다.
        """
        if not graph_model.is_standalone_ref(ref):
            return
        source = self._macro_path(ref)
        folder_name = os.path.splitext(os.path.basename(ref))[0]
        parent = os.path.dirname(source)
        target_dir = os.path.join(parent, folder_name)
        target = os.path.join(target_dir, "macro.json")

        if os.path.exists(target_dir):
            messagebox.showerror(u"폴더로 정리",
                                 u"'%s' 폴더가 이미 있습니다." % folder_name)
            return

        callers = self.find_macro_callers(ref)
        new_ref = os.path.relpath(target_dir, MACROS_DIR).replace("\\", "/")
        message = (u"'%s' 를 폴더로 옮깁니다.\n\n"
                   u"  %s\n     ↓\n  %s\\macro.json\n\n"
                   u"이러면 이 매크로가 쓰는 이미지를 같은 폴더에 둘 수 있습니다."
                   % (ref, ref, new_ref))
        if callers:
            message += u"\n\n호출하는 곳 %d군데의 참조도 함께 고칩니다." % len(callers)
        if not messagebox.askyesno(u"폴더로 정리", message):
            return

        editing_this = self._is_self_reference(ref)
        if editing_this and self.macro.dirty and not self._confirm_discard():
            return
        self._flush_last_selected()   # 끝나면 디스크에서 다시 읽는다

        try:
            os.makedirs(target_dir)
            shutil.move(source, target)
        except Exception as exc:
            messagebox.showerror(u"폴더로 정리 실패", str(exc))
            return

        updated = self._rewrite_call_refs(callers, new_ref)
        self.refresh_library()
        self.refresh_project()
        if editing_this:
            try:
                self.macro = model.Macro.load(target)
                self.apply_mode()
            except Exception as exc:
                self.log_line(u"정리 후 다시 열기 실패: %s" % exc, "err")
        self.log_line(u"폴더로 정리: %s -> %s (참조 %d곳 갱신)"
                      % (ref, new_ref, updated), "ok")

    def _macro_folder(self, ref):
        return os.path.join(MACROS_DIR, ref)

    def _macro_path(self, ref):
        """참조 이름 -> 실제 macro json 파일 경로."""
        if ref and ref.startswith("./"):
            # 하위 매크로 참조. 지금 열린 매크로의 가족 기준이다.
            base = self.macro.folder or MACROS_DIR
            resolved = graph_model.resolve_macro_ref(ref, base)
            if resolved:
                return resolved
            # 파일이 아직/이미 없어도 경로는 만들어 준다 (삭제 확인 등에 쓰인다)
            return os.path.join(graph_model.family_root(base),
                                ref[2:].strip("/"), "macro.json")
        if graph_model.is_standalone_ref(ref):
            return os.path.join(MACROS_DIR, ref)
        return os.path.join(MACROS_DIR, ref, "macro.json")

    def _is_loose_in_root(self, ref):
        """Macros 루트에 폴더 없이 놓인 매크로인가.

        이 경우에만 문제가 된다 - 이미지 기준 폴더가 Macros 루트가 되어
        여러 매크로의 이미지가 한곳에 뒤섞인다.
        자기 폴더 안에 있으면 파일 이름이 macro.json 이 아니어도 문제 없다.
        """
        if not graph_model.is_standalone_ref(ref):
            return False
        parent = os.path.dirname(os.path.abspath(self._macro_path(ref)))
        return os.path.normcase(parent) == os.path.normcase(
            os.path.abspath(MACROS_DIR))

    def find_macro_callers(self, ref):
        """이 매크로를 호출하는 (매크로 참조, 노드 id, 파일경로) 목록."""
        # 폴더가 아니라 파일 경로로 비교한다. 파일 하나짜리 매크로는 여럿이
        # 같은 폴더(Macros 루트)에 있어서 폴더로 비교하면 서로 오인된다.
        target = os.path.normcase(os.path.abspath(self._macro_path(ref)))
        callers = []
        # 하위 매크로도 호출자가 될 수 있으므로 라이브러리 목록이 아니라
        # 모든 매크로 파일을 훑는다.
        for other_ref, _name, path in graph_model.list_macros(
                MACROS_DIR, include_subs=True):
            try:
                handle = open(path, "rb")
                try:
                    data = json.loads(handle.read().decode("utf-8"))
                finally:
                    handle.close()
            except Exception:
                continue
            folder = os.path.dirname(path)
            for node in data.get("nodes") or []:
                if node.get("type") != "call":
                    continue
                resolved = graph_model.resolve_macro_ref(node.get("macro"), folder)
                if resolved and os.path.normcase(os.path.abspath(resolved)) == target:
                    callers.append((other_ref, node.get("id"), path))
            # 감시 목록도 참조다. 빠뜨리면 이름을 바꾼 감시 매크로가 걸려
            # 있던 매크로들이 실행 전 검사에서 전부 막힌다.
            for index, handler in enumerate(graph_model.handler_refs(data)):
                resolved = graph_model.resolve_macro_ref(handler, folder)
                if resolved and os.path.normcase(os.path.abspath(resolved)) == target:
                    callers.append((other_ref, _HANDLER_SLOT % index, path))
        return callers

    def rename_macro(self, ref):
        standalone = graph_model.is_standalone_ref(ref)
        old_source = self._macro_path(ref)
        old_name = os.path.basename(ref)
        if standalone:
            old_name = os.path.splitext(old_name)[0]

        new_name = simpledialog.askstring(
            u"매크로 이름 변경",
            u"새 파일 이름" if standalone else u"새 폴더 이름",
            initialvalue=old_name, parent=self.root)
        if not new_name or new_name == old_name:
            return
        bad = set('\\/:*?"<>|')
        if bad & set(new_name):
            messagebox.showerror(u"이름 변경", u"이름에 쓸 수 없는 문자가 있습니다.")
            return

        prefix = ref.rsplit("/", 1)[0] + "/" if "/" in ref else ""
        if standalone:
            old_folder = old_source
            new_folder = os.path.join(os.path.dirname(old_source), new_name + ".json")
            new_ref = prefix + new_name + ".json"
        else:
            old_folder = self._macro_folder(ref)
            new_folder = os.path.join(os.path.dirname(old_folder), new_name)
            new_ref = prefix + new_name
        if os.path.exists(new_folder):
            messagebox.showerror(u"이름 변경", u"같은 이름이 이미 있습니다.")
            return

        callers = self.find_macro_callers(ref)

        message = u"'%s' 을 '%s' 로 바꿉니다." % (ref, new_ref)
        if callers:
            message += u"\n\n이 매크로를 호출하는 곳이 %d군데 있습니다. " \
                       u"그 참조도 함께 고칩니다." % len(callers)
        if not messagebox.askyesno(u"매크로 이름 변경", message):
            return

        editing_this = self._is_self_reference(ref)
        if editing_this and self.macro.dirty and not self._confirm_discard():
            return
        self._flush_last_selected()   # 끝나면 디스크에서 다시 읽는다

        try:
            os.rename(old_folder, new_folder)
        except OSError as exc:
            messagebox.showerror(u"이름 변경 실패", str(exc))
            return

        updated = self._rewrite_call_refs(callers, new_ref)
        self.refresh_library()
        self.refresh_project()
        if editing_this:
            reopened = new_folder if standalone \
                else os.path.join(new_folder, "macro.json")
            try:
                self.macro = model.Macro.load(reopened)
                self.apply_mode()
            except Exception as exc:
                self.log_line(u"이름 변경 후 다시 열기 실패: %s" % exc, "err")
        self.log_line(u"매크로 이름 변경: %s -> %s (참조 %d곳 갱신)"
                      % (ref, new_ref, updated), "ok")

    def _rewrite_call_refs(self, callers, new_ref):
        """호출 노드들의 macro 값을 새 이름으로 고친다."""
        by_path = {}
        for _ref, node_id, path in callers:
            by_path.setdefault(path, []).append(node_id)
        updated = 0
        for path, node_ids in by_path.items():
            try:
                handle = open(path, "rb")
                try:
                    data = json.loads(handle.read().decode("utf-8"))
                finally:
                    handle.close()
                for node in data.get("nodes") or []:
                    if node.get("id") in node_ids and node.get("type") == "call":
                        node["macro"] = new_ref
                        updated += 1
                handlers = data.get("handlers")
                if isinstance(handlers, list):
                    for index in range(len(handlers)):
                        if (_HANDLER_SLOT % index) in node_ids:
                            handlers[index] = new_ref
                            updated += 1
                out = open(path, "wb")
                try:
                    out.write(json.dumps(data, ensure_ascii=False,
                                         indent=2).encode("utf-8"))
                finally:
                    out.close()
            except Exception as exc:
                self.log_line(u"참조 갱신 실패 (%s): %s" % (path, exc), "err")
        return updated

    def duplicate_macro(self, ref):
        standalone = graph_model.is_standalone_ref(ref)
        source = self._macro_path(ref) if standalone else self._macro_folder(ref)
        stem, ext = os.path.splitext(source) if standalone else (source, "")
        base = source
        index = 2
        while os.path.exists(base):
            base = "%s_%d%s" % (stem, index, ext)
            index += 1
        try:
            if standalone:
                shutil.copyfile(source, base)
            else:
                shutil.copytree(source, base)
        except Exception as exc:
            messagebox.showerror(u"복제 실패", str(exc))
            return
        self.refresh_library()
        self.refresh_project()
        self.log_line(u"매크로 복제: %s" % os.path.basename(base), "ok")

    def delete_macro(self, ref):
        standalone = graph_model.is_standalone_ref(ref)
        folder = self._macro_path(ref) if standalone else self._macro_folder(ref)
        callers = self.find_macro_callers(ref)
        if standalone:
            message = u"'%s' 파일을 삭제합니다.\n%s" % (ref, folder)
        else:
            message = u"'%s' 폴더를 통째로 삭제합니다.\n%s" % (ref, folder)
            # 부모를 지우면 그 안의 하위 매크로도 함께 사라진다. 폴더 하나로
            # 보여서 놓치기 쉬우므로 몇 개가 딸려 가는지 먼저 알린다.
            subs = graph_model.list_sub_macros(folder)
            if subs:
                message += u"\n\n하위 매크로 %d개도 함께 지워집니다: %s" % (
                    len(subs), u", ".join(r[2:] for r, _n, _p in subs))
        if callers:
            message += u"\n\n이 매크로를 호출하는 곳이 %d군데 있습니다. " \
                       u"삭제하면 그 호출이 실패합니다." % len(callers)
        message += u"\n\n이 프로젝트는 버전 관리를 쓰지 않아 되돌릴 수 없습니다. 계속할까요?"
        if not messagebox.askyesno(u"매크로 삭제", message):
            return
        if self._is_self_reference(ref):
            messagebox.showinfo(u"매크로 삭제",
                                u"지금 편집 중인 매크로입니다. 다른 매크로를 연 뒤 삭제하세요.")
            return
        try:
            if standalone:
                os.remove(folder)
            else:
                shutil.rmtree(folder)
        except Exception as exc:
            messagebox.showerror(u"삭제 실패", str(exc))
            return
        self.refresh_library()
        self.refresh_project()
        self.log_line(u"매크로 삭제: %s" % ref, "err")

    # ---------------------------------------------- 하위 매크로 (UE의 '함수')

    def _family_state(self):
        """(가족 루트 폴더, 하위 매크로 편집 중인가).

        폴더형(macro.json)으로 저장되기 전에는 (None, False) - 파일 하나짜리
        매크로는 폴더를 여럿이 공유해서 하위 매크로를 둘 수 없다.
        """
        if not self.macro.path or \
                os.path.basename(self.macro.path).lower() != "macro.json":
            return None, False
        folder = os.path.abspath(self.macro.folder)
        root = graph_model.family_root(folder)
        return root, os.path.normcase(root) != os.path.normcase(folder)

    def resource_dir(self):
        """이미지가 놓이는 폴더. 하위 매크로면 부모 매크로 폴더다."""
        return self.macro.resource_folder

    def refresh_submacros(self):
        self._submacro_refs = []
        widget = self.submacro_list
        if widget is None:
            return
        widget.delete(0, "end")
        root, editing_sub = self._family_state()
        if self.submacro_parent_btn is not None:
            self.submacro_parent_btn.configure(
                state="normal" if editing_sub else "disabled")
        if root is None:
            if self.macro.path:
                text = u"폴더형 매크로에서만 하위 매크로를 쓸 수 있습니다"
            else:
                text = u"매크로를 저장하면 하위 매크로를 만들 수 있습니다"
            if self.submacro_header is not None:
                self.submacro_header.configure(text=text)
            return
        self._submacro_refs = graph_model.list_sub_macros(root)
        if self.submacro_header is not None:
            self.submacro_header.configure(
                text=u"'%s' 의 하위 매크로 — 이 가족 안에서만 호출됩니다"
                     % os.path.basename(root))
        current = os.path.normcase(os.path.abspath(self.macro.path))
        for ref, name, path in self._submacro_refs:
            mark = u"● " if os.path.normcase(os.path.abspath(path)) == current \
                else u"   "
            plain = ref[2:]
            display = plain if name == plain else u"%s  —  %s" % (plain, name)
            widget.insert("end", mark + display)
        if not self._submacro_refs:
            widget.insert("end", u"   (없음 — [새 하위 매크로]로 추가)")

    def _selected_submacro_ref(self):
        if self.submacro_list is None or not self._submacro_refs:
            return None
        selection = self.submacro_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(self._submacro_refs):
            return None
        return self._submacro_refs[index][0]

    def open_selected_submacro(self):
        ref = self._selected_submacro_ref()
        if not ref:
            return
        self.open_macro_path(self._macro_path(ref))

    def open_parent_macro(self):
        root, editing_sub = self._family_state()
        if not editing_sub:
            return
        self.open_macro_path(os.path.join(root, "macro.json"))

    def _on_submacro_press(self, event):
        index = self.submacro_list.nearest(event.y)
        if index < 0 or index >= len(self._submacro_refs):
            self._drag_ref = None
            return
        self.submacro_list.selection_clear(0, "end")
        self.submacro_list.selection_set(index)
        self._drag_ref = self._submacro_refs[index][0]
        self._drag_active = False

    def _on_submacro_right_click(self, event):
        index = self.submacro_list.nearest(event.y)
        if index < 0 or index >= len(self._submacro_refs):
            return
        self.submacro_list.selection_clear(0, "end")
        self.submacro_list.selection_set(index)
        ref = self._submacro_refs[index][0]

        menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(menu)
        menu.add_command(label=u"편집 (열기)",
                         command=self.open_selected_submacro)
        menu.add_command(label=u"호출 노드로 추가",
                         command=self.insert_submacro_call)
        menu.add_separator()
        menu.add_command(label=u"이름 변경...",
                         command=lambda: self.rename_submacro(ref))
        menu.add_command(label=u"복제",
                         command=lambda: self.duplicate_submacro(ref))
        menu.add_command(label=u"삭제",
                         command=lambda: self.delete_submacro(ref))
        menu.add_separator()
        menu.add_command(label=u"탐색기에서 열기",
                         command=lambda: project_panel.ProjectPanel._reveal(
                             self._macro_path(ref)))
        menu.tk_popup(event.x_root, event.y_root)

    def insert_submacro_call(self):
        ref = self._selected_submacro_ref()
        if not ref:
            self.status.set(u"하위 매크로를 먼저 고르세요")
            return
        if self.mode != "graph":
            messagebox.showinfo(u"노드 모드 필요",
                                u"호출 노드는 노드 그래프에서만 추가할 수 있습니다.\n"
                                u"[도구 > 그래프로 변환]을 먼저 하세요.")
            return
        if self._is_self_reference(ref) and not messagebox.askyesno(
                u"자기 자신 호출",
                u"지금 편집 중인 매크로를 호출하려 합니다.\n"
                u"순환 호출이 되어 실행이 중단됩니다. 그래도 추가할까요?"):
            return
        node = self.canvas_view.add_node("call")
        node["macro"] = ref
        node["label"] = ref[2:]
        self.canvas_view.redraw()
        self.on_node_selected(node["id"])
        self.status.set(u"호출 노드 추가: %s" % ref)

    def new_submacro(self):
        if not self.macro.path:
            messagebox.showinfo(u"먼저 저장",
                                u"하위 매크로를 둘 폴더가 필요합니다.\n"
                                u"매크로를 먼저 저장해 주세요.")
            return
        root, _editing_sub = self._family_state()
        if root is None:
            messagebox.showinfo(u"하위 매크로",
                                u"폴더형 매크로(Macros\\이름\\macro.json)에서만\n"
                                u"하위 매크로를 만들 수 있습니다.\n"
                                u"라이브러리 우클릭 [폴더로 정리]를 먼저 하세요.")
            return
        name = simpledialog.askstring(
            u"새 하위 매크로",
            u"하위 매크로 이름을 입력하세요.\n"
            u"%s\\<이름>\\macro.json 으로 만들어지고,\n"
            u"이미지는 부모 폴더의 것을 함께 씁니다." % os.path.basename(root),
            parent=self.root)
        if not name:
            return
        name = name.strip()
        bad = set('\\/:*?"<>|')
        if not name or bad & set(name):
            messagebox.showerror(u"새 하위 매크로",
                                 u"이름이 비었거나 쓸 수 없는 문자가 있습니다.")
            return
        target_dir = os.path.join(root, name)
        if os.path.exists(target_dir):
            messagebox.showerror(u"새 하위 매크로", u"같은 이름이 이미 있습니다.")
            return
        data = graph_model.blank(name)
        # 하위 매크로는 부모 설정을 상속한다. 자기 settings 를 남겨 두면
        # 편집기에서 값을 고쳐도 실행에 반영되지 않아 헷갈리므로 아예 뺀다.
        data.pop("settings", None)
        try:
            os.makedirs(target_dir)
            handle = open(os.path.join(target_dir, "macro.json"), "wb")
            try:
                handle.write(json.dumps(data, ensure_ascii=False,
                                        indent=2).encode("utf-8"))
            finally:
                handle.close()
        except Exception as exc:
            messagebox.showerror(u"새 하위 매크로", str(exc))
            return
        self.refresh_submacros()
        self.refresh_project()
        self.log_line(u"하위 매크로 생성: %s" % name, "ok")
        if messagebox.askyesno(u"새 하위 매크로",
                               u"'%s' 를 만들었습니다. 지금 열어서 편집할까요?"
                               % name):
            self.open_macro_path(os.path.join(target_dir, "macro.json"))

    def rename_submacro(self, ref):
        root, _editing_sub = self._family_state()
        if root is None:
            return
        old_name = ref[2:]
        old_folder = os.path.join(root, old_name)
        new_name = simpledialog.askstring(u"하위 매크로 이름 변경", u"새 이름",
                                          initialvalue=old_name, parent=self.root)
        if not new_name or new_name == old_name:
            return
        new_name = new_name.strip()
        bad = set('\\/:*?"<>|')
        if not new_name or bad & set(new_name):
            messagebox.showerror(u"이름 변경", u"이름에 쓸 수 없는 문자가 있습니다.")
            return
        new_folder = os.path.join(root, new_name)
        if os.path.exists(new_folder):
            messagebox.showerror(u"이름 변경", u"같은 이름이 이미 있습니다.")
            return

        callers = self.find_macro_callers(ref)
        message = u"하위 매크로 '%s' 을 '%s' 로 바꿉니다." % (old_name, new_name)
        if callers:
            message += u"\n\n호출하는 곳 %d군데의 참조도 함께 고칩니다." % len(callers)
        if not messagebox.askyesno(u"하위 매크로 이름 변경", message):
            return

        # 지금 열린 매크로가 이름을 바꾸는 당사자이거나 그 호출자면, 참조
        # 갱신이 디스크에만 적히고 메모리에는 남지 않는다. 저장/버림을 먼저
        # 정리하고 갱신 후 디스크에서 다시 읽는다.
        current = os.path.normcase(os.path.abspath(self.macro.path))
        editing_this = self._is_self_reference(ref)
        involved = editing_this or any(
            os.path.normcase(os.path.abspath(p)) == current
            for _r, _n, p in callers)
        if involved and self.macro.dirty and not self._confirm_discard():
            return
        self._flush_last_selected()   # 끝나면 디스크에서 다시 읽는다

        try:
            os.rename(old_folder, new_folder)
        except OSError as exc:
            messagebox.showerror(u"이름 변경 실패", str(exc))
            return

        updated = self._rewrite_call_refs(callers, "./" + new_name)
        reopen = None
        if editing_this:
            reopen = os.path.join(new_folder, "macro.json")
        elif involved:
            reopen = self.macro.path
        if reopen:
            try:
                self.macro = model.Macro.load(reopen)
                self.apply_mode()
            except Exception as exc:
                self.log_line(u"이름 변경 후 다시 열기 실패: %s" % exc, "err")
        self.refresh_submacros()
        self.refresh_project()
        self.log_line(u"하위 매크로 이름 변경: %s -> %s (참조 %d곳 갱신)"
                      % (old_name, new_name, updated), "ok")

    def duplicate_submacro(self, ref):
        root, _editing_sub = self._family_state()
        if root is None:
            return
        source = os.path.join(root, ref[2:])
        base = source
        index = 2
        while os.path.exists(base):
            base = "%s_%d" % (source, index)
            index += 1
        try:
            shutil.copytree(source, base)
        except Exception as exc:
            messagebox.showerror(u"복제 실패", str(exc))
            return
        self.refresh_submacros()
        self.refresh_project()
        self.log_line(u"하위 매크로 복제: %s" % os.path.basename(base), "ok")

    def delete_submacro(self, ref):
        root, _editing_sub = self._family_state()
        if root is None:
            return
        if self._is_self_reference(ref):
            messagebox.showinfo(u"하위 매크로 삭제",
                                u"지금 편집 중인 매크로입니다. "
                                u"부모를 연 뒤 삭제하세요.")
            return
        name = ref[2:]
        folder = os.path.join(root, name)
        callers = self.find_macro_callers(ref)
        message = u"하위 매크로 '%s' 폴더를 통째로 삭제합니다.\n%s" % (name, folder)
        if callers:
            message += u"\n\n호출하는 곳이 %d군데 있습니다. " \
                       u"삭제하면 그 호출이 실패합니다." % len(callers)
        message += u"\n\n이 프로젝트는 버전 관리를 쓰지 않아 되돌릴 수 없습니다. 계속할까요?"
        if not messagebox.askyesno(u"하위 매크로 삭제", message):
            return
        try:
            shutil.rmtree(folder)
        except Exception as exc:
            messagebox.showerror(u"삭제 실패", str(exc))
            return
        self.refresh_submacros()
        self.refresh_project()
        self.log_line(u"하위 매크로 삭제: %s" % name, "err")

    # ---------------------------------------------- 프로젝트 패널 연동

    def open_macro_path(self, path):
        if not os.path.isfile(path):
            self.log_line(u"파일이 없습니다: %s" % path, "err")
            return
        if not self._confirm_discard():
            return
        try:
            self.macro = model.Macro.load(path)
        except Exception as exc:
            messagebox.showerror(u"열기 실패", u"%s\n\n%s" % (path, exc))
            return
        self.current_path = None
        self.apply_mode()
        self.focus_opened_macro()
        self.status.set(u"열림: %s" % path)

    def open_macro_ref(self, ref):
        if not ref:
            return
        base = self.macro.folder or MACROS_DIR
        path = graph_model.resolve_macro_ref(ref, base)
        if not path:
            self.log_line(u"매크로를 찾을 수 없습니다: %s" % ref, "err")
            return
        self.open_macro_path(path)

    def assign_image_to_selected(self, path):
        """프로젝트 패널에서 고른 이미지를 지금 선택된 단계의 이미지로 지정."""
        step = self.current_step_obj
        if step is None:
            self.status.set(u"이미지를 지정할 노드를 먼저 선택하세요")
            return
        if "image" not in [f["name"] for f in schema.fields_for(step.get("type"))]:
            self.status.set(u"'%s' 노드에는 이미지 매개변수가 없습니다"
                            % schema.step_label(step.get("type")))
            return
        folder = self.resource_dir()
        if not folder:
            self.status.set(u"매크로를 먼저 저장해야 이미지를 지정할 수 있습니다")
            return
        path = graph_model.base_image_path(path)
        in_folder = os.path.normcase(os.path.dirname(os.path.abspath(path))) == \
            os.path.normcase(os.path.abspath(folder))
        if in_folder:
            value = os.path.basename(path)
        else:
            # 바깥 이미지는 절대 경로로 참조하지 않고 복사해 온다.
            # 절대 경로로 두면 매크로 폴더를 옮기는 순간 깨진다.
            if not messagebox.askyesno(
                    u"이미지 복사",
                    u"이 이미지는 다른 폴더에 있습니다.\n"
                    u"'%s' 로 복사해서 쓸까요?\n\n"
                    u"복사하지 않으면 매크로를 옮겼을 때 깨집니다."
                    % os.path.basename(folder)):
                return
            value = imagepicker.copy_into_folder(self.root, folder, path)
            if not value:
                return
        step["image"] = value
        self.mark_dirty()
        self.build_properties()
        if self.mode == "graph":
            self.canvas_view.redraw()
        else:
            self.refresh_tree_labels()
        self.log_line(u"이미지 지정: %s" % value, "ok")

    def find_image_users(self, path):
        """이 이미지 파일을 참조하는 (매크로 경로, 단계 id) 목록."""
        # 노드는 이름으로 참조한다. `@폴더` 의 변종이라도 사용처는 같다
        target = os.path.normcase(os.path.abspath(
            graph_model.base_image_path(path)))
        users = []
        for _ref, _name, macro_path in graph_model.list_macros(
                MACROS_DIR, include_subs=True):
            # 하위 매크로의 이미지 기준은 자기 폴더가 아니라 부모 폴더다.
            # 이걸 빼먹으면 부모 이미지를 쓰는 하위가 검색에서 빠져서,
            # '아무도 안 쓰는 이미지'로 오인해 지우는 사고가 난다.
            folder = graph_model.family_root(os.path.dirname(macro_path))
            try:
                handle = open(macro_path, "rb")
                try:
                    data = json.loads(handle.read().decode("utf-8"))
                finally:
                    handle.close()
            except Exception:
                continue
            steps = data.get("nodes") or []
            if not steps:
                steps = [s for s in _flatten_tree(data.get("steps") or [])]
            for step in steps:
                name = step.get("image")
                if not name:
                    continue
                full = name if os.path.isabs(name) else os.path.join(folder, name)
                if os.path.normcase(os.path.abspath(full)) == target:
                    users.append((macro_path, step.get("id")))
            # 감시 조건의 이미지도 사용처다. 빠뜨리면 감시에만 쓰는 이미지가
            # '아무도 안 쓰는 이미지'로 보여 지워진다.
            for name in schema.condition_images(data.get("watch")):
                full = name if os.path.isabs(name) else os.path.join(folder, name)
                if os.path.normcase(os.path.abspath(full)) == target:
                    users.append((macro_path, u"감시 조건"))
        return users

    def rename_image_references(self, old_name, new_name, old_path):
        """이미지 이름이 바뀌었을 때 참조하는 단계들을 고친다."""
        folder = os.path.normcase(os.path.abspath(os.path.dirname(old_path)))
        changed = 0
        for _ref, _name, macro_path in graph_model.list_macros(
                MACROS_DIR, include_subs=True):
            # 이미지 폴더(부모)가 같은 가족 전체가 대상이다. 하위 매크로는
            # 부모 폴더의 이미지를 이름만으로 참조하기 때문이다.
            macro_folder = os.path.normcase(
                graph_model.family_root(os.path.dirname(macro_path)))
            if macro_folder != folder:
                continue
            try:
                handle = open(macro_path, "rb")
                try:
                    data = json.loads(handle.read().decode("utf-8"))
                finally:
                    handle.close()
                touched = False
                for step in (data.get("nodes") or []) + _flatten_tree(data.get("steps") or []):
                    if step.get("image") == old_name:
                        step["image"] = new_name
                        touched = True
                        changed += 1
                watch = data.get("watch")
                if old_name in schema.condition_images(watch):
                    schema.rewrite_condition_images(watch, {old_name: new_name})
                    touched = True
                    changed += 1
                if touched:
                    out = open(macro_path, "wb")
                    try:
                        out.write(json.dumps(data, ensure_ascii=False,
                                             indent=2).encode("utf-8"))
                    finally:
                        out.close()
            except Exception:
                continue
        if changed and self.macro.path:
            try:
                self.macro = model.Macro.load(self.macro.path)
                self.apply_mode()
            except Exception:
                pass
        return changed

    def _warn_missing_call(self, ref):
        if not ref:
            return
        base = self.macro.folder or MACROS_DIR
        if graph_model.resolve_macro_ref(ref, base) is None:
            self.log_line(u"주의: 호출 대상을 찾을 수 없습니다: %s" % ref, "err")

    def check_call_targets(self, only=None):
        """호출 노드가 가리키는 매크로의 존재와 순환을 확인한다.

        `only` 에 노드 id 집합을 주면 그 노드들만 본다. 노드를 붙여넣은
        직후처럼 방금 들어온 것만 짚어야 할 때 쓴다.
        """
        problems = []
        if self.mode != "graph" or self.graph is None:
            return problems
        base = self.macro.folder or MACROS_DIR
        for node in self.graph.nodes:
            if node.get("type") != "call":
                continue
            if only is not None and node.get("id") not in only:
                continue
            ref = node.get("macro")
            if not ref:
                problems.append(u"노드 %s: 호출할 매크로가 지정되지 않았습니다"
                                % node.get("id"))
                continue
            resolved = graph_model.resolve_macro_ref(ref, base)
            if resolved is None:
                problems.append(u"노드 %s: 호출 대상을 찾을 수 없습니다 (%s)"
                                % (node.get("id"), ref))
                continue
            # 하위 매크로는 그 부모/형제만 부를 수 있다. 엔진도 거부하지만
            # 실행할 때가 아니라 지금 알아야 한다.
            target_dir = os.path.dirname(os.path.abspath(resolved))
            target_owner = graph_model.family_root(target_dir)
            if target_owner != target_dir and \
                    os.path.normcase(target_owner) != \
                    os.path.normcase(graph_model.family_root(base)):
                problems.append(
                    u"노드 %s: '%s' 는 다른 매크로의 하위 매크로입니다. "
                    u"하위 매크로는 부모와 형제만 호출할 수 있습니다"
                    % (node.get("id"), ref))
                continue
            cycle = graph_model.find_call_cycle(ref, base)
            if cycle:
                names = [os.path.basename(os.path.dirname(p)) for p in cycle]
                problems.append(u"노드 %s: 순환 호출 (%s)"
                                % (node.get("id"), u" -> ".join(names)))
                continue
            # 넘기는 값이 대상의 선언과 맞는지. 대상 매크로에서 이름을 바꾸면
            # 여기 값이 고아가 되는데, 실행할 때가 아니라 지금 알아야 한다.
            target = self.load_macro_data(ref)
            if target is None:
                continue
            # 반복 변수 참조($이름)는 아직 값이 아니다. 여기서는 이름이
            # 대상에 선언돼 있는지만 보고, 값 검사는 실행에 맡긴다.
            _values, trouble = graph_model.bind_params(
                target, node.get("args"), allow_refs=True)
            for line in trouble:
                problems.append(u"노드 %s (%s): %s"
                                % (node.get("id"), ref, line))
        return problems

    def check_handler_targets(self):
        """이 매크로가 건 감시 매크로를 실제 파일과 대조한다. (오류, 경고).

        엔진도 실행 전에 같은 검사로 거부하지만, 실행할 때가 아니라 지금
        알아야 한다. 트리 형식은 Graph.validate 를 거치지 않으므로 선언
        검사도 여기서 함께 한다.
        """
        warnings = []
        errors = []
        if self.mode != "graph":
            errors.extend(graph_model.validate_handler_decl(self.macro.data,
                                                            warnings))
        base = self.macro.folder or MACROS_DIR
        found, cautions = graph_model.check_handler_refs(
            self.macro.data, base, self.macro.path)
        return errors + found, warnings + cautions

    def watch_candidates(self):
        """감시로 걸 수 있는 매크로 [(참조, 표시이름)]. 자기 자신은 뺀다.

        라이브러리 매크로와, 지금 매크로가 가족 안에 있으면 그 가족의 하위
        매크로 중 감시 조건(watch)을 가진 것만 고른다.
        """
        own = os.path.normcase(os.path.abspath(self.macro.path)) \
            if self.macro.path else None
        found = []
        entries = []
        try:
            entries.extend(graph_model.list_macros(MACROS_DIR))
        except Exception:
            pass
        root, _sub = self._family_state()
        if root:
            entries.extend(graph_model.list_sub_macros(root))
        for ref, name, path in entries:
            if own and os.path.normcase(os.path.abspath(path)) == own:
                continue
            data = graph_model.read_macro_file(path)
            if data is not None and graph_model.is_watch_macro(data):
                found.append((ref, name))
        return found

    # ------------------------------------------------------- 모드 (트리/그래프)

    def apply_mode(self):
        """매크로 형식에 맞춰 가운데 화면을 노드 캔버스 / 트리 중 하나로 바꾼다."""
        # 매크로가 바뀌면 [이어서 실행] 도 그 매크로 기준으로 다시 본다
        self.refresh_resume_button()
        if self.macro.is_graph:
            self.mode = "graph"
            self.graph = graph_model.Graph(self.macro.data)
        else:
            self.mode = "tree"
            self.graph = None

        # 패널이 아직 안 지어졌을 수 있다 (도킹 재구성 중 순서 문제)
        if getattr(self, "canvas_view", None) is not None:
            if self.mode == "graph":
                self.view_label.pack_forget()
                self.tree_view.pack_forget()
                self.canvas_view.pack(fill="both", expand=True)
                # 썸네일도 실행기와 같은 곳에서 찾는다 - 하위 매크로면 부모 폴더
                self.canvas_view.set_graph(self.graph, self.resource_dir())
            else:
                self.canvas_view.pack_forget()
                self.view_label.pack(fill="x")
                self.view_label.config(
                    text=u"트리 형식 — [도구 > 그래프로 변환] 으로 노드 편집 가능")
                self.tree_view.pack(fill="both", expand=True)
                self.refresh_tree()
        self._sync_view_title()
        self.current_step_obj = None
        if getattr(self, "prop_frame", None) is not None:
            self.build_properties()
        if getattr(self, "library_list", None) is not None:
            self.refresh_library()
        if getattr(self, "submacro_list", None) is not None:
            self.refresh_submacros()

    def focus_opened_macro(self):
        """막 연 매크로의 그래프 화면 위치를 잡는다.

        `apply_mode` 에 넣지 않는다 - 그쪽은 이름을 바꾼 뒤 다시 읽을 때나
        패널을 다시 지을 때도 불리는데, 그때는 보던 자리가 그대로여야 한다.
        """
        if self.mode == "graph" and getattr(self, "canvas_view", None) is not None:
            self.canvas_view.focus_opened()

    def _flush_last_selected(self):
        """떠나는 매크로의 마지막 선택 노드를 파일에 남긴다.

        기록은 편의 기능이므로 실패해도 매크로를 떠나는 일을 막지 않는다.
        """
        try:
            self.macro.store_last_selected()
        except (OSError, ValueError) as exc:
            self.log_line(u"마지막 선택 노드를 기록하지 못했습니다: %s" % exc, "err")

    def _sync_view_title(self):
        """가운데 패널 제목줄을 현재 모드에 맞춘다."""
        dock = getattr(self, "dock", None)
        if dock is None:
            return
        panel = dock.panels.get("graph")
        if panel is None or panel.header is None:
            return
        name = self.macro.data.get("name") or u"(이름 없음)"
        _root, editing_sub = self._family_state()
        if editing_sub:
            name = u"%s › %s" % (os.path.basename(_root), name)
        kind = u"노드 그래프" if self.mode == "graph" else u"단계 트리"
        try:
            panel.header.configure(text=u"%s — %s" % (kind, name))
        except tk.TclError:
            pass

    def on_node_selected(self, node_id):
        """노드 캔버스가 선택을 알려줄 때."""
        if node_id is None or self.graph is None:
            self.current_step_obj = None
        else:
            self.current_step_obj = self.graph.node(node_id)
        self.build_properties()
        if self.current_step_obj is not None:
            self.status.set(u"선택: %s" % schema.summarize(self.current_step_obj))

    def focus_properties(self):
        self.build_properties()

    def convert_to_graph(self):
        if self.macro.is_graph:
            messagebox.showinfo(u"변환", u"이미 그래프 형식입니다.")
            return
        if not messagebox.askyesno(
                u"그래프로 변환",
                u"트리 형식을 노드 그래프로 바꿉니다.\n"
                u"중첩 구조가 실행 연결로 펼쳐지며 동작은 같습니다.\n\n"
                u"변환 후 [다른 이름으로 저장]을 권합니다 (원본 보존)."):
            return
        converted = graph_model.from_tree(self.macro.data)
        path = self.macro.path
        self.macro = model.Macro(converted.data, path)
        self.macro.dirty = True
        self.apply_mode()
        if self.mode == "graph":
            self.canvas_view.auto_layout()
        self.log_line(u"그래프로 변환: 노드 %d개" % self.macro.count(), "ok")
        self._update_title()

    # ------------------------------------------------------------------ 트리

    def refresh_tree(self, keep_path=None):
        if self.tree is None:
            return
        keep_path = keep_path or self.current_path
        self.tree.delete(*self.tree.get_children())
        self.item_paths.clear()
        self.path_items.clear()
        self._insert_children("", self.macro.steps, ())
        for item in self.item_paths:
            self.tree.item(item, open=True)
        if keep_path and keep_path in self.path_items:
            item = self.path_items[keep_path]
            self.tree.selection_set(item)
            self.tree.see(item)
        else:
            self.current_path = None
            self.build_properties()
        self._update_title()

    def _insert_children(self, parent_item, steps, prefix):
        for index, step in enumerate(steps):
            path = prefix + (index,)
            enabled = step.get("enabled") is not False
            tags = []
            if not enabled:
                tags.append("disabled")
            if schema.containers_for(step.get("type")):
                tags.append("container")
            item = self.tree.insert(
                parent_item, "end",
                text=schema.summarize(step),
                values=(u"O" if enabled else u"—",),
                tags=tuple(tags))
            self.item_paths[item] = path
            self.path_items[path] = item

            for key in schema.containers_for(step.get("type")):
                children = step.get(key) or []
                label = schema.container_label(step.get("type"), key)
                bucket = self.tree.insert(item, "end",
                                          text=u"[%s]" % label, values=("",),
                                          tags=("container",))
                bucket_path = path + (key,)
                self.item_paths[bucket] = bucket_path
                self.path_items[bucket_path] = bucket
                self._insert_children(bucket, children, path + (key,))

    def refresh_tree_labels(self):
        if self.mode == "graph":
            self.canvas_view.redraw()
            self.mark_dirty()
            return
        for item, path in self.item_paths.items():
            if isinstance(path[-1], int):
                try:
                    self.tree.item(item, text=schema.summarize(self.macro.get(path)))
                except model.MacroError:
                    pass
        self.mark_dirty()

    def selected_path(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.item_paths.get(selection[0])

    def safe_get(self, path):
        """경로가 낡았을 수 있는 자리에서 쓰는 조회. 실패하면 None.

        트리 선택과 매크로가 어긋나는 순간(삭제 직후 등)에 편집기가 죽지 않게 한다.
        """
        if not path:
            return None
        try:
            return self.macro.get(path)
        except model.MacroError:
            return None

    def on_select(self, _event=None):
        path = self.selected_path()
        self.current_path = path
        self.build_properties()

    def _on_tree_right_click(self, event):
        """툴바에서 뺀 삭제/이동을 트리에서도 쓸 수 있게 한다."""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.on_select()
        path = self.selected_path()
        if not path:
            return
        menu = tk.Menu(self.root, tearoff=0)
        theme.style_menu(menu)
        if isinstance(path[-1], int):
            menu.add_command(label=u"위로", command=lambda: self.move_step(-1))
            menu.add_command(label=u"아래로", command=lambda: self.move_step(1))
            menu.add_command(label=u"복제 (Ctrl+D)", command=self.duplicate_step)
            menu.add_command(label=u"사용/해제", command=self.toggle_step)
            menu.add_separator()
            menu.add_command(label=u"삭제", command=self.delete_step)
        else:
            menu.add_command(label=u"(이 자리에 단계 추가는 상단 [단계 추가])",
                             state="disabled")
        menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------- 단계 편집

    def _insert_target(self):
        """새 단계가 들어갈 자리를 (부모경로, 컨테이너키) 또는 (None, None)으로."""
        path = self.selected_path()
        if not path:
            return None, None
        if isinstance(path[-1], str):
            # [참일 때] 같은 컨테이너 표시줄을 고른 상태
            if self.safe_get(path[:-1]) is None:
                return None, None
            return path[:-1], path[-1]
        step = self.safe_get(path)
        if step is None:
            return None, None
        containers = schema.containers_for(step.get("type"))
        if containers:
            return path, containers[0]
        return None, None

    def add_step(self, stype):
        if self.mode == "graph":
            self.canvas_view.add_node(stype)
            self.status.set(u"노드 추가: %s" % schema.step_label(stype))
            return
        step = schema.new_step(stype)
        parent, key = self._insert_target()
        if parent is not None:
            new_path = self.macro.append(parent, key, step)
        else:
            path = self.selected_path()
            if path and isinstance(path[-1], int):
                new_path = self.macro.insert(path[:-1] + (path[-1] + 1,), step)
            else:
                new_path = self.macro.append(None, None, step)
        self.current_path = new_path
        self.refresh_tree(new_path)
        self.status.set(u"추가: %s" % schema.step_label(stype))

    def delete_step(self):
        if self.mode == "graph":
            self.canvas_view.delete_selection()
            return
        path = self.selected_path()
        if not path or not isinstance(path[-1], int):
            return
        step = self.safe_get(path)
        if step is None:
            return
        if schema.containers_for(step.get("type")):
            has_children = any(step.get(k) for k in schema.containers_for(step.get("type")))
            if has_children and not messagebox.askyesno(
                    u"확인", u"자식 단계가 함께 삭제됩니다. 계속할까요?"):
                return
        self.macro.remove(path)
        self.current_path = None
        self.refresh_tree()
        self.status.set(u"삭제됨")

    def move_step(self, delta):
        if self.mode == "graph":
            self.status.set(u"노드 모드에서는 노드를 드래그해서 옮깁니다")
            return
        path = self.selected_path()
        if not path or not isinstance(path[-1], int) or self.safe_get(path) is None:
            return
        new_path = self.macro.move(path, delta)
        self.current_path = new_path
        self.refresh_tree(new_path)

    def duplicate_step(self):
        if self.mode == "graph":
            self.canvas_view.duplicate_selection()
            return
        path = self.selected_path()
        if not path or not isinstance(path[-1], int) or self.safe_get(path) is None:
            return
        new_path = self.macro.duplicate(path)
        self.current_path = new_path
        self.refresh_tree(new_path)
        self.status.set(u"복제됨")

    def toggle_step(self):
        if self.mode == "graph":
            if self.canvas_view.selected_node:
                self.canvas_view._toggle(self.canvas_view.selected_node)
                self.build_properties()
            return
        path = self.selected_path()
        if not path or not isinstance(path[-1], int):
            return
        step = self.safe_get(path)
        if step is None:
            return
        step["enabled"] = step.get("enabled") is False
        if step["enabled"]:
            del step["enabled"]
        self.mark_dirty()
        self.refresh_tree(path)

    # ------------------------------------------------------------- 속성 패널

    def _watch_field(self, widget, read, commit):
        """타이핑으로 고치는 칸 하나를 '아직 안 넣었을 수 있는 것'으로 등록한다.

        반환한 함수를 <FocusOut>/<Return> 에 걸면 된다.

        <FocusOut> 만으로는 부족하다. 캔버스에서 다른 노드를 클릭하면
        `_on_press` 가 `focus_set()` 을 부르지만 Tk 는 FocusOut 이벤트를
        이벤트 루프 뒤쪽에서 보낸다. 그 전에 선택이 바뀌면서 속성 패널이
        통째로 다시 지어져 입력칸이 파괴되고, 이벤트는 끝내 오지 않는다.
        Enter 를 치지 않고 노드를 클릭하면 방금 친 값이 조용히 사라졌던 이유다.
        그래서 패널을 지우기(그리고 저장/실행하기) 직전에 여기 등록된 것을
        먼저 반영한다.

        `widget` 을 함께 들고 있는 이유: 위젯이 사라진 뒤에도 StringVar 는
        살아 있어서 read() 가 계속 값을 돌려준다. 그대로 두면 이미 닫힌
        조건 편집 창의 입력칸이 나중에 flush 될 때 그 창이 쓰던 dict 에
        값을 다시 써 넣는다. 위젯이 죽으면 등록도 버린다.
        """
        state = {"was": read()}

        def commit_now(_event=None):
            commit()
            # 반영이 끝났으면 기준값을 새로 잡는다. 나중에 flush 가 돌 때
            # 같은 값을 두 번 쓰지 않게 하려는 것이다. 값이 잘못돼서
            # commit 이 거절했다면 그 글자가 기준이 되고, 다시 시도해도
            # 같은 이유로 거절되므로 반복 경고가 나지 않는다.
            try:
                state["was"] = read()
            except tk.TclError:
                pass

        def pending():
            return read() != state["was"]

        self._prop_commits.append((widget, pending, commit_now))
        return commit_now

    def flush_property_edits(self):
        """속성 패널에서 아직 반영되지 않은 입력을 지금 반영한다.

        건드리지 않은 칸은 건너뛴다 - 값이 그대로인데 commit 을 부르면
        반복 노드의 '횟수/조건' 처럼 서로를 지우는 필드가 엉킬 수 있다.
        """
        if self._flushing_props:
            return
        # 살아 있는 등록은 남긴다. 여기서 목록을 통째로 비우면 아직 화면에
        # 있는 칸을 다음 flush 가 놓친다. 목록은 build_properties 가 비운다.
        self._flushing_props = True
        try:
            alive = []
            for entry in list(self._prop_commits):
                widget, is_pending, commit_now = entry
                try:
                    if not widget.winfo_exists():
                        continue          # 위젯이 사라졌다 - 등록을 버린다
                    changed = is_pending()
                except tk.TclError:
                    continue
                alive.append(entry)
                if not changed:
                    continue
                try:
                    commit_now()
                except tk.TclError:
                    pass
            self._prop_commits = alive
        finally:
            self._flushing_props = False

    def build_properties(self):
        if self.prop_frame is None:
            return
        # 위젯을 부수기 전에 먼저 반영한다. 순서가 반대면 값이 사라진다.
        self.flush_property_edits()
        try:
            children = self.prop_frame.winfo_children()
        except tk.TclError:
            self.prop_frame = None
            self._prop_commits = []
            return
        self._prop_commits = []
        for child in children:
            child.destroy()

        if self.mode == "graph":
            step = self.current_step_obj
            if step is None:
                ttk.Label(self.prop_frame,
                          text=u"노드를 선택하세요.\n\n"
                               u"빈 곳 우클릭 → 노드 추가\n"
                               u"출력 핀에서 드래그 → 다른 노드에 놓으면 연결\n"
                               u"연결선 클릭 후 Delete → 연결 삭제\n"
                               u"가운데 버튼 드래그 → 화면 이동, 휠 → 확대/축소",
                          padding=12, justify="left").pack(anchor="w")
                return
        else:
            path = self.current_path
            if not path:
                ttk.Label(self.prop_frame,
                          text=u"단계를 선택하세요.",
                          padding=12).pack(anchor="w")
                return
            if isinstance(path[-1], str):
                parent = self.safe_get(path[:-1])
                if parent is None:
                    return
                ttk.Label(self.prop_frame,
                          text=u"'%s' 안에 넣을 단계를 [단계 추가]로 고르세요."
                               % schema.container_label(parent.get("type"), path[-1]),
                          padding=12, wraplength=320).pack(anchor="w")
                return
            step = self.safe_get(path)
            if step is None:
                ttk.Label(self.prop_frame, text=u"단계를 선택하세요.",
                          padding=12).pack(anchor="w")
                return
            self.current_step_obj = step
        stype = step.get("type")

        header = ttk.Frame(self.prop_frame, padding=(10, 10, 10, 4))
        header.pack(fill="x")
        ttk.Label(header, text=schema.step_label(stype),
                  font=("", 11, "bold")).pack(anchor="w")

        body = ttk.Frame(self.prop_frame, padding=(10, 0, 10, 10))
        body.pack(fill="both", expand=True)

        for field in schema.fields_for(stype):
            if field["type"] == "condition":
                box = ttk.LabelFrame(body, text=field["label"], padding=6)
                box.pack(fill="x", pady=4)
                ConditionEditor(
                    box, self,
                    lambda f=field: step.get(f["name"]),
                    lambda v, f=field: self._set_step_value(step, f["name"], v)
                ).pack(fill="x")
                if field.get("help"):
                    ttk.Label(box, text=field["help"], foreground="#666666",
                              wraplength=300).pack(anchor="w", pady=(4, 0))
            elif field["type"] == "target":
                box = ttk.LabelFrame(body, text=field["label"], padding=6)
                box.pack(fill="x", pady=4)
                sub = step.setdefault(field["name"], {})
                self.build_field(box, {"name": "image", "type": "image",
                                       "label": u"이미지"}, sub)
                self.build_field(box, {"name": "point", "type": "point",
                                       "label": u"좌표"}, sub)
                self.build_field(box, {"name": "targetOffset", "type": "point",
                                       "label": u"오프셋",
                                       "help": u"이미지를 찾았을 때 그 중앙에서 "
                                               u"이만큼 떨어진 곳을 잡는다. "
                                               u"좌표를 직접 준 경우에는 쓰이지 "
                                               u"않는다"}, sub)
            elif self.field_visible(field):
                self.build_field(body, field, step)

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8)
        for field in schema.COMMON_FIELDS:
            self.build_field(body, field, step)

    def field_visible(self, field):
        """좌표 기준은 해상도 대응을 쓰는 매크로에서만 뜻이 있다."""
        return field["name"] != "space" or self.macro.scaling is not None

    def _set_step_value(self, step, name, value):
        step[name] = value
        if name == "while" and step.get("type") == "repeat":
            self._repeat_mode_condition(step)
        self.mark_dirty()

    def _repeat_mode_condition(self, step):
        """반복을 '조건' 방식으로 굳힌다.

        times 와 while 이 함께 남으면 실행기가 거부한다. 예전에는 times 가
        조용히 이겨서, 조건을 넣어 둔 반복이 조건을 보지도 않고 끝났다.
        조건을 고르는 순간 횟수를 치운다.
        """
        dropped = [label for key, label in (("times", u"반복 횟수"),
                                            ("forEach", u"값 목록"))
                   if key in step]
        step.pop("times", None)
        step.pop("forEach", None)
        if "maxIterations" not in step:
            # 조건 반복에는 필수다. 비워 두면 검사에서 막혀 진행이 끊긴다.
            step["maxIterations"] = 100
        if dropped:
            self.status.set(u"조건 반복으로 바꿨습니다 - '%s'을 비웠습니다"
                            % u"', '".join(dropped))
        # 지금은 조건 위젯의 콜백 안이다. 여기서 패널을 다시 만들면 호출 중인
        # 위젯이 사라진다. 콜백이 끝난 뒤로 미룬다.
        self.root.after_idle(self.build_properties)

    def build_field(self, parent, field, target, on_change=None):
        """스키마 필드 하나에 해당하는 위젯을 만든다."""
        if target is None:
            return
        ftype = field["type"]
        name = field["name"]

        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=field["label"], width=13).pack(side="left", anchor="n")

        def changed():
            self.mark_dirty()
            if on_change:
                on_change()
            else:
                self.refresh_tree_labels()

        if ftype == "bool":
            var = tk.BooleanVar(value=bool(target.get(name, field.get("default", False))))

            def toggle():
                default = field.get("default")
                if default is not None and var.get() == default:
                    target.pop(name, None)
                else:
                    target[name] = var.get()
                changed()
            ttk.Checkbutton(row, variable=var, command=toggle).pack(side="left")

        elif ftype == "choice":
            options = field["options"]
            labels = [lbl for _v, lbl in options]
            values = [v for v, _lbl in options]
            combo = ttk.Combobox(row, values=labels, state="readonly", width=22)
            current = target.get(name, field.get("default", ""))
            if current in values:
                combo.current(values.index(current))
            combo.pack(side="left", fill="x", expand=True)

            def on_choice(_e=None):
                value = values[combo.current()]
                if value == "" or value == field.get("default"):
                    target.pop(name, None)
                else:
                    target[name] = value
                changed()
            combo.bind("<<ComboboxSelected>>", on_choice)

        elif ftype == "keycombo":
            # key 와 modifiers 를 한 필드로 다룬다. 타이핑 대신 선택 창을 쓴다.
            display = tk.Label(row, anchor="w", padx=8, pady=4,
                               bg=theme.BG_DARKEST, fg=theme.ACCENT,
                               font=("Consolas", 10, "bold"))
            display.pack(side="left", fill="x", expand=True)

            def refresh_display():
                display.configure(
                    text=keypicker.describe(target.get("key"),
                                            target.get("modifiers")))
            refresh_display()

            def choose():
                picked = keypicker.ask_key(self.root, target.get("key"),
                                           target.get("modifiers"))
                if picked is None:
                    return
                target["key"] = picked["key"]
                if picked["modifiers"]:
                    target["modifiers"] = picked["modifiers"]
                else:
                    target.pop("modifiers", None)
                refresh_display()
                changed()
            ttk.Button(row, text=u"선택...", width=8, style="Accent.TButton",
                       command=choose).pack(side="left", padx=(4, 0))

        elif ftype == "macro_ref":
            refs = self.available_macros()
            labels = [self._ref_label(r, n) for r, n in refs]
            combo = ttk.Combobox(row, values=labels, width=20)
            combo.set(target.get(name, "") or "")
            combo.pack(side="left", fill="x", expand=True)

            def commit_ref(_e=None):
                text = combo.get().strip()
                ref = text.split(u"  —  ")[0].strip()
                if ref:
                    target[name] = ref
                else:
                    target.pop(name, None)
                combo.set(ref)
                changed()
                self._warn_missing_call(ref)
            watched_ref = self._watch_field(combo, lambda: combo.get(), commit_ref)
            combo.bind("<<ComboboxSelected>>", watched_ref)
            combo.bind("<FocusOut>", watched_ref)
            combo.bind("<Return>", watched_ref)

            def open_ref():
                ref = (target.get(name) or "").strip()
                if not ref:
                    return
                base = self.macro.folder or MACROS_DIR
                path = graph_model.resolve_macro_ref(ref, base)
                if not path:
                    self.log_line(u"매크로를 찾을 수 없습니다: %s" % ref, "err")
                    return
                if not self._confirm_discard():
                    return
                try:
                    self.macro = model.Macro.load(path)
                except Exception as exc:
                    self.log_line(u"열기 실패: %s" % exc, "err")
                    return
                self.current_path = None
                self.apply_mode()
                self.focus_opened_macro()
                self.status.set(u"열림: %s" % path)
            ttk.Button(row, text=u"열기", width=6, command=open_ref).pack(
                side="left", padx=(4, 0))

        elif ftype == "param_name":
            # 이 매크로가 선언한 매개변수만 고를 수 있다. 직접 타이핑하게 두면
            # 이름을 바꿨을 때 조건이 조용히 어긋난다.
            # 선언된 매개변수 + forEach 반복이 만드는 변수
            names = graph_model.scope_param_names(self.macro.data)
            combo = ttk.Combobox(row, values=names, state="readonly", width=22)
            current = target.get(name)
            if current in names:
                combo.current(names.index(current))
            elif current:
                # 선언에서 사라진 이름. 지우지 않고 보여 줘야 사용자가 안다.
                combo.configure(state="normal")
                combo.set(current)
            combo.pack(side="left", fill="x", expand=True)

            def on_param(_e=None):
                target[name] = combo.get()
                changed()
            combo.bind("<<ComboboxSelected>>", on_param)
            if not names:
                ttk.Label(row, text=u"(선언된 매개변수 없음)",
                          style="Dim.TLabel").pack(side="left", padx=(6, 0))

        elif ftype == "foreach":
            self._build_foreach(parent, row, target, changed)

        elif ftype == "call_args":
            self._build_call_args(parent, row, target, changed)

        elif ftype == "text":
            widget = tk.Text(row, height=3, width=28, wrap="word")
            widget.insert("1.0", target.get(name, "") or "")
            widget.pack(side="left", fill="x", expand=True)

            def on_text(_e=None):
                value = widget.get("1.0", "end-1c")
                if value:
                    target[name] = value
                else:
                    target.pop(name, None)
                changed()
            watched_text = self._watch_field(
                widget, lambda: widget.get("1.0", "end-1c"), on_text)
            widget.bind("<FocusOut>", watched_text)
            widget.bind("<KeyRelease>", watched_text)

        else:
            var = tk.StringVar(value=self._value_to_text(target.get(name)))
            entry = ttk.Entry(row, textvariable=var)
            entry.pack(side="left", fill="x", expand=True)

            def commit(_e=None):
                text = var.get().strip()
                if text == "":
                    target.pop(name, None)
                    changed()
                    return
                try:
                    value = self._text_to_value(ftype, text)
                except ValueError as exc:
                    self.status.set(u"%s: %s" % (field["label"], exc))
                    return
                # 값이 실제로 바뀌었을 때만 상대 필드를 건드린다. 칸을 지나치기만
                # 해도 FocusOut 으로 commit 이 도는데, 그때 조건이 지워지면 안 된다.
                same = name in target and target[name] == value
                target[name] = value
                if (not same and name == "times"
                        and target.get("type") == "repeat"
                        and ("while" in target or "forEach" in target)):
                    gone = [label for key, label in (("while", u"조건"),
                                                     ("forEach", u"값 목록"))
                            if key in target]
                    target.pop("while", None)
                    target.pop("maxIterations", None)
                    target.pop("forEach", None)
                    self.status.set(
                        u"횟수 반복으로 바꿨습니다 - '%s'을 비웠습니다"
                        % u"', '".join(gone))
                    self.root.after_idle(self.build_properties)
                changed()
            watched = self._watch_field(entry, lambda: var.get(), commit)
            entry.bind("<FocusOut>", watched)
            entry.bind("<Return>", watched)

            self._add_field_buttons(row, field, target, var, commit)

        if field.get("help"):
            ttk.Label(parent, text=field["help"], foreground="#666666",
                      wraplength=330, font=("", 8)).pack(anchor="w", padx=(96, 0))

    def load_macro_data(self, ref):
        """호출 대상 매크로의 원본 dict. 못 읽으면 None."""
        if not ref:
            return None
        base = self.macro.folder or MACROS_DIR
        path = graph_model.resolve_macro_ref(ref, base)
        if not path:
            return None
        try:
            with open(path, encoding="utf-8-sig") as handle:
                return json.loads(handle.read())
        except Exception:
            return None

    def _build_foreach(self, parent, row, node, changed):
        """값 목록으로 도는 반복을 편집한다.

        변수 이름 / 타입 / 값 목록 세 칸이다. 이름을 비우면 forEach 자체를
        지워서 다시 횟수 반복으로 돌아간다 - 빈 껍데기가 남으면 검사에서
        '값이 하나 이상 필요합니다' 로만 보여 원인을 알기 어렵다.
        """
        ttk.Label(row, text=u"").pack(side="left")     # 라벨 줄만 차지한다
        box = ttk.Frame(parent)
        box.pack(fill="x", padx=(96, 0))

        spec = node.get("forEach")
        if not isinstance(spec, dict):
            spec = {}

        name_var = tk.StringVar(value=spec.get("param") or "")
        type_var = tk.StringVar(value=spec.get("type") or "int")
        values_var = tk.StringVar(
            value=", ".join(u"%s" % v for v in (spec.get("values") or [])))

        def commit(_e=None):
            name = name_var.get().strip()
            if not name:
                if "forEach" in node:
                    node.pop("forEach", None)
                    changed()
                return
            ptype = type_var.get()
            raw = [t.strip() for t in values_var.get().split(",")]
            raw = [t for t in raw if t != ""]
            if not raw:
                self.status.set(u"값을 하나 이상 적으세요 (쉼표로 구분)")
                return
            values = []
            for index, text in enumerate(raw):
                try:
                    values.append(graph_model.coerce_param(
                        text, ptype, u"%d번째 값" % (index + 1)))
                except graph_model.ParamError as exc:
                    self.status.set(u"%s" % exc)
                    return
            if name in graph_model.param_names(self.macro.data):
                self.status.set(
                    u"'%s' 는 선언된 매개변수와 이름이 같습니다. 다른 이름을 쓰세요"
                    % name)
                return
            # 값 반복은 횟수/조건과 함께 쓸 수 없다. 고른 쪽만 남긴다.
            gone = [label for key, label in (("times", u"반복 횟수"),
                                             ("while", u"조건"))
                    if key in node]
            for key in ("times", "while", "maxIterations", "allowMaxIterations"):
                node.pop(key, None)
            node["forEach"] = {"param": name, "type": ptype, "values": values}
            if gone:
                self.status.set(u"값 목록 반복으로 바꿨습니다 - '%s'을 비웠습니다"
                                % u"', '".join(gone))
            changed()

        line = ttk.Frame(box)
        line.pack(fill="x", pady=2)
        ttk.Label(line, text=u"변수 이름", width=12).pack(side="left")
        name_entry = ttk.Entry(line, textvariable=name_var, width=18)
        name_entry.pack(side="left")
        ttk.Label(line, text=u"타입", width=6).pack(side="left", padx=(8, 0))
        type_combo = ttk.Combobox(line, textvariable=type_var, width=8,
                                  state="readonly",
                                  values=list(graph_model.PARAM_TYPES))
        type_combo.pack(side="left")

        line2 = ttk.Frame(box)
        line2.pack(fill="x", pady=2)
        ttk.Label(line2, text=u"값 목록", width=12).pack(side="left")
        values_entry = ttk.Entry(line2, textvariable=values_var)
        values_entry.pack(side="left", fill="x", expand=True)

        ttk.Label(box, text=u"쉼표로 구분합니다. 예: 2, 3, 4, 5, 6",
                  style="Dim.TLabel").pack(anchor="w", padx=(96, 0))
        if name_var.get():
            ttk.Label(box,
                      text=u"호출 노드의 '넘길 값'에 $%s 라고 적으면 전달됩니다"
                           % name_var.get(),
                      style="Dim.TLabel").pack(anchor="w", padx=(96, 0))

        for entry in (name_entry, values_entry):
            watched = self._watch_field(
                entry,
                lambda nv=name_var, vv=values_var: (nv.get(), vv.get()), commit)
            entry.bind("<FocusOut>", watched)
            entry.bind("<Return>", watched)
        type_combo.bind("<<ComboboxSelected>>", commit)

    def _build_call_args(self, parent, row, node, changed):
        """호출 노드가 넘길 값을 편집한다.

        칸을 스키마가 아니라 **대상 매크로의 선언**에서 만든다. 그래서 대상을
        바꾸면 칸도 따라 바뀐다. 선언에 없는데 남아 있는 값은 지우지 않고
        따로 보여 준다 - 조용히 버리면 이름을 바꿨을 때 알아채지 못한다.
        """
        ttk.Label(row, text=u"").pack(side="left")     # 라벨 줄만 차지한다
        box = ttk.Frame(parent)
        box.pack(fill="x", padx=(96, 0))

        data = self.load_macro_data(node.get("macro"))
        if data is None:
            ttk.Label(box, text=u"대상 매크로를 먼저 고르세요",
                      style="Dim.TLabel").pack(anchor="w")
            return

        declared = graph_model.declared_params(data)
        args = node.setdefault("args", {})
        if not declared:
            ttk.Label(box, text=u"이 매크로는 매개변수를 선언하지 않았습니다",
                      style="Dim.TLabel").pack(anchor="w")
        for param in declared:
            pname = param.get("name")
            if not pname:
                continue
            ptype = param.get("type")
            label = u"%s (%s)" % (pname, graph_model.PARAM_TYPE_LABELS.get(
                ptype, ptype))
            if "default" in param:
                label += u" 기본 %s" % (param["default"],)
            if graph_model.loop_params(self.macro.data):
                label += u"  ($이름 으로 반복 변수)"
            line = ttk.Frame(box)
            line.pack(fill="x", pady=2)
            ttk.Label(line, text=label, width=26).pack(side="left")
            var = tk.StringVar(value=self._value_to_text(args.get(pname)))
            entry = ttk.Entry(line, textvariable=var)
            entry.pack(side="left", fill="x", expand=True)

            def commit(_e=None, pname=pname, ptype=ptype, var=var):
                text = var.get().strip()
                if text == "":
                    args.pop(pname, None)
                    changed()
                    return
                if text.startswith("$"):
                    # 반복 변수를 그대로 넘긴다. 값이 아니라 이름이므로
                    # 여기서 타입 변환을 하지 않는다 - 실행 시점에 맞춘다.
                    ref = text[1:].strip()
                    known = graph_model.scope_param_names(self.macro.data)
                    if ref not in known:
                        self.status.set(
                            u"'%s' 는 이 매크로에 없는 이름입니다 (쓸 수 있는 것: %s)"
                            % (ref, u", ".join(known) or u"없음"))
                        return
                    args[pname] = graph_model.param_ref(ref)
                    changed()
                    return
                try:
                    args[pname] = graph_model.coerce_param(text, ptype, pname)
                except graph_model.ParamError as exc:
                    self.status.set(u"%s" % exc)
                    return
                changed()
            watched = self._watch_field(entry, lambda v=var: v.get(), commit)
            entry.bind("<FocusOut>", watched)
            entry.bind("<Return>", watched)

        known = set(p.get("name") for p in declared)
        stale = [k for k in sorted(args.keys()) if k not in known]
        for key in stale:
            line = ttk.Frame(box)
            line.pack(fill="x", pady=2)
            ttk.Label(line, text=u"⚠ %s = %s" % (key, args[key]),
                      foreground=theme.WARN).pack(side="left")
            ttk.Label(line, text=u"대상에 없는 값",
                      style="Dim.TLabel").pack(side="left", padx=(6, 0))

            def drop(key=key):
                args.pop(key, None)
                changed()
                self.build_properties()
            ttk.Button(line, text=u"지우기", width=7, command=drop).pack(
                side="left", padx=(6, 0))

    def _add_field_buttons(self, row, field, target, var, commit):
        ftype = field["type"]
        name = field["name"]

        if ftype == "image":
            ttk.Button(row, text=u"캡처", width=6,
                       command=lambda: self._capture_image(target, name, var, commit)
                       ).pack(side="left", padx=(4, 0))
            ttk.Button(row, text=u"선택", width=6,
                       command=lambda: self._browse_image(target, name, var, commit)
                       ).pack(side="left", padx=(2, 0))

        elif ftype == "point":
            ttk.Button(row, text=u"찍기", width=6,
                       command=lambda: self._pick_point(var, commit, target)
                       ).pack(side="left", padx=(4, 0))

        elif ftype == "points":
            # 찍을 때마다 뒤에 이어 붙인다. 경유지는 순서가 의미를 갖는다.
            def add_point():
                point = self.run_with_window_hidden(
                    lambda: pickers.pick_point(self.root))
                if not point:
                    return
                stored = self._stored_point(point, target)
                if stored is None:
                    return
                try:
                    current = self._text_to_value("points", var.get() or "")
                except ValueError:
                    current = []          # 손으로 잘못 적어 뒀으면 새로 시작한다
                current.append([stored[0], stored[1]])
                var.set(self._value_to_text(current))
                commit()
                self._warn_if_offscreen(point)
            ttk.Button(row, text=u"추가", width=6, command=add_point
                       ).pack(side="left", padx=(4, 0))
            ttk.Button(row, text=u"지우기", width=7,
                       command=lambda: (var.set(""), commit())
                       ).pack(side="left", padx=(2, 0))

        elif ftype == "rgb":
            swatch = tk.Label(row, width=3, relief="sunken")
            swatch.pack(side="left", padx=(4, 0))
            self._paint_swatch(swatch, target.get(name))

            def pick():
                result = pickers.pick_color(self.root)
                if not result:
                    return
                stored = self._stored_point(result["point"], target)
                if stored is None:
                    return
                var.set(self._value_to_text(result["rgb"]))
                commit()
                self._paint_swatch(swatch, result["rgb"])
                # 좌표 필드가 같이 있으면 함께 채워준다
                if "point" in target or True:
                    target["point"] = list(stored)
                    self.mark_dirty()
                    self.build_properties()
            ttk.Button(row, text=u"찍기", width=6, command=pick).pack(side="left", padx=(2, 0))

        elif ftype == "region":
            ttk.Button(row, text=u"드래그", width=7,
                       command=lambda: self._pick_region(var, commit, target)
                       ).pack(side="left", padx=(4, 0))

    @staticmethod
    def _paint_swatch(widget, rgb):
        try:
            r, g, b = [int(v) for v in rgb]
            widget.configure(background="#%02x%02x%02x" % (r, g, b))
        except Exception:
            widget.configure(background="#f0f0f0")

    @staticmethod
    def _value_to_text(value):
        if value is None:
            return ""
        if graph_model.is_param_ref(value):
            return "$%s" % value.get(graph_model.PARAM_REF)
        if isinstance(value, (list, tuple)):
            if value and all(isinstance(v, (list, tuple)) for v in value):
                # 좌표가 여러 개다. 점 안은 쉼표, 점끼리는 세미콜론으로 끊는다.
                return " ; ".join(", ".join(str(n) for n in v) for v in value)
            return ", ".join(str(v) for v in value)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _text_to_value(ftype, text):
        if ftype == "int":
            return int(text)
        if ftype == "float":
            return float(text)
        if ftype in ("point", "rgb", "region"):
            parts = [p.strip() for p in text.replace(",", " ").split()]
            expected = {"point": 2, "rgb": 3, "region": 4}[ftype]
            if len(parts) != expected:
                raise ValueError(u"숫자 %d개가 필요합니다" % expected)
            return [int(float(p)) for p in parts]
        if ftype == "points":
            if not text.strip():
                return []
            out = []
            for chunk in text.split(";"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                parts = chunk.replace(",", " ").split()
                if len(parts) != 2:
                    raise ValueError(
                        u"경유지는 'x,y' 형식이고 세미콜론으로 구분합니다")
                out.append([int(float(p)) for p in parts])
            return out
        if ftype == "tolerance":
            parts = [p.strip() for p in text.replace(",", " ").split()]
            if len(parts) == 1:
                return int(float(parts[0]))
            if len(parts) == 3:
                return [int(float(p)) for p in parts]
            raise ValueError(u"숫자 1개 또는 3개")
        return text

    # ------------------------------------------------------------- 피커 연동

    def run_with_window_hidden(self, func):
        """편집기 창을 잠시 숨기고 화면 선택 작업을 한다.

        withdraw() 뒤에 deiconify() 하면 최대화 상태가 풀리고 창 크기/위치가
        초기값으로 돌아간다. 상태와 기하 정보를 기억했다가 되돌린다.
        """
        state = None
        geometry = None
        try:
            state = self.root.state()
            geometry = self.root.geometry()
        except tk.TclError:
            pass

        self.root.withdraw()
        try:
            return func()
        finally:
            try:
                if state == "withdrawn":
                    pass          # 원래 숨어 있던 창은 그대로 둔다
                else:
                    self.root.deiconify()
                    if state == "zoomed":
                        self.root.state("zoomed")
                    elif geometry:
                        self.root.geometry(geometry)
                    self.root.update_idletasks()
            except tk.TclError:
                pass

    def _pick_point(self, var, commit, target=None):
        point = self.run_with_window_hidden(
            lambda: pickers.pick_point(self.root))
        if point:
            stored = self._stored_point(point, target)
            if stored is None:
                return
            var.set("%d, %d" % tuple(stored))
            commit()
            self._warn_if_offscreen(point)

    def _pick_region(self, var, commit, target=None):
        region = self.run_with_window_hidden(
            lambda: pickers.pick_region(self.root))
        if region:
            stored = self._stored_region(region, target)
            if stored is None:
                return
            var.set("%d, %d, %d, %d" % tuple(stored))
            commit()
            self._warn_if_offscreen(region[:2])

    # ------------------------------------------------------------ 해상도 대응

    def _coordinate_view(self, target=None):
        """찍은 값을 저장 값(기준 좌표)으로 되돌릴 변환. (변환, 문제) 를 준다.

        변환이 None 이면 찍은 값을 그대로 저장한다. 문제가 있으면 저장하면
        안 된다 - 변환 없이 넣으면 틀린 값이 조용히 기준 좌표로 들어간다.

        노드의 조각(드래그의 시작/끝)은 `space` 를 노드에 두므로 선택된 노드도 본다.
        """
        spec = self.macro.scaling
        if not spec:
            return None, None
        selected = self.current_step_obj or {}
        space = ((target or {}).get("space") or selected.get("space")
                 or self.macro.data.get("space") or graph_model.SPACE_WINDOW)
        screen = screenutil.logical_screen_size()
        if space == graph_model.SPACE_SCREEN:
            return graph_model.screen_view(spec, screen), None
        client = screenutil.game_client(spec["window"])
        if client is not None:
            return graph_model.Transform(spec["client"], client), None
        if graph_model.same_size(screen, spec["screen"]):
            return None, None     # 기준 환경. 게임을 안 띄운 채 고치는 경우다
        return None, (u"게임 창을 찾지 못해 찍은 값을 기준 좌표로 바꿀 수 "
                      u"없습니다. 게임을 띄운 뒤 다시 찍어 주세요")

    def _refuse_stored(self, problem):
        self.log_line(problem, "err")
        self.status.set(problem)

    def _stored_point(self, point, target=None):
        """찍은 좌표를 저장할 값으로. 저장하면 안 되면 None."""
        view, problem = self._coordinate_view(target)
        if problem:
            self._refuse_stored(problem)
            return None
        if view is None or view.identity:
            return tuple(point)
        stored = tuple(view.inverse_point(point))
        self.log_line(u"찍은 좌표 %s -> 저장 값 %s (기준 좌표)"
                      % (tuple(point), stored), "info")
        return stored

    def _stored_region(self, region, target=None):
        """찍은 영역을 저장할 값으로. 저장하면 안 되면 None."""
        view, problem = self._coordinate_view(target)
        if problem:
            self._refuse_stored(problem)
            return None
        if view is None or view.identity:
            return tuple(region)
        stored = tuple(view.inverse_region(region))
        self.log_line(u"찍은 영역 %s -> 저장 값 %s (기준 좌표)"
                      % (tuple(region), stored), "info")
        return stored

    def _capture_destination(self, filename):
        """캡처를 저장할 경로.

        기준 화면에서는 매크로 폴더에 바로 둔다. 다른 화면에서는 `@가로x세로`
        폴더에 둔다 - 같은 이름의 기준 이미지를 덮어쓰면 기준 환경이 망가진다.
        """
        folder = self.resource_dir()
        spec = self.macro.scaling
        if not spec:
            return os.path.join(folder, filename)
        screen = screenutil.logical_screen_size()
        client = screenutil.game_client(spec["window"])
        if graph_model.same_size(screen, spec["screen"]):
            if client is not None and not graph_model.Transform(
                    spec["client"], client).identity:
                self.log_line(u"주의: 게임 창이 기준 크기가 아닙니다. 이 캡처는 "
                              u"기준 이미지로 저장되므로 배율이 어긋납니다", "err")
            return os.path.join(folder, filename)
        target = os.path.join(folder, graph_model.capture_folder_name(screen))
        graph_model.write_capture_info(target, screen, client)
        return os.path.join(target, filename)

    def _scaling_text(self, spec):
        """이 해상도 대응 설정의 지금 상태를 설명하는 글."""
        if not spec:
            return u"꺼짐 - 좌표와 이미지를 저장된 값 그대로 씁니다."
        window = spec["window"]
        lines = [u"기준 창: %s" % (window.get("title") or window.get("class")),
                 u"기준 화면 %d x %d, 창 안쪽 %d x %d"
                 % (spec["screen"][0], spec["screen"][1],
                    spec["client"][2], spec["client"][3])]
        client = screenutil.game_client(window)
        if client is None:
            lines.append(u"지금 기준 창을 찾을 수 없습니다.")
        else:
            view = graph_model.Transform(spec["client"], client)
            lines.append(u"지금: 기준과 같은 크기" if view.identity
                         else u"지금: %s" % view.describe())
        return u"\n".join(lines)

    def _scaling_warnings(self):
        """매크로 검사에 보탤 경고."""
        spec = self.macro.scaling
        client = screenutil.game_client(spec["window"]) if spec else None
        if client is None:
            return []
        view = graph_model.Transform(spec["client"], client)
        if view.aspect_drift() <= graph_model.ASPECT_WARN:
            return []
        return [u"게임 창의 가로세로비가 기준과 %.1f%% 다릅니다. 게임 UI 배치가 "
                u"비례를 벗어나 좌표가 어긋날 수 있습니다"
                % (view.aspect_drift() * 100)]

    def _build_scaling_editor(self, box, dialog):
        """매크로 설정의 해상도 대응 칸. [확인] 때 값을 넣을 함수를 돌려준다."""
        data = self.macro.data
        _root, editing_sub = self._family_state()
        pending = {"scaling": self.macro.scaling}
        state = ttk.Label(box, style="Dim.TLabel", wraplength=420,
                          justify="left",
                          text=self._scaling_text(pending["scaling"]))
        state.pack(anchor="w", pady=(0, 6))

        def show():
            state.configure(text=self._scaling_text(pending["scaling"]))

        def register():
            """창을 찍어서 그 창의 지금 크기를 기준으로 삼는다."""
            dialog.withdraw()
            try:
                point = self.run_with_window_hidden(
                    lambda: pickers.pick_point(self.root))
            finally:
                dialog.deiconify()
            if not point:
                return
            found = screenutil.window_at(*point)
            if found is None:
                messagebox.showerror(u"기준 창 등록",
                                     u"그 자리에서 창을 찾지 못했습니다.")
                return
            width, height = screenutil.logical_screen_size()
            pending["scaling"] = {
                "window": {"class": found["class"], "title": found["title"]},
                "client": found["client"],
                "screen": [width, height],
            }
            show()

        def clear():
            pending["scaling"] = None
            show()

        row = ttk.Frame(box)
        row.pack(fill="x")
        button_state = "disabled" if editing_sub else "normal"
        ttk.Button(row, text=u"기준 창 등록", command=register,
                   state=button_state).pack(side="left")
        ttk.Button(row, text=u"해제", command=clear,
                   state=button_state).pack(side="left", padx=4)
        if editing_sub:
            ttk.Label(row, style="Dim.TLabel",
                      text=u"하위 매크로는 부모 설정을 씁니다").pack(side="left")

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=u"이 매크로의 좌표 기준").pack(side="left")
        labels = [u"게임 창 (창 크기에 맞춰 변환)", u"화면 (자리만 비례, 이미지 그대로)"]
        combo = ttk.Combobox(row, values=labels, state="readonly", width=30)
        combo.current(1 if data.get("space") == graph_model.SPACE_SCREEN else 0)
        combo.pack(side="left", padx=4)

        def apply_scaling():
            if not editing_sub:
                settings = data.setdefault("settings", {})
                if pending["scaling"]:
                    settings["scaling"] = pending["scaling"]
                else:
                    settings.pop("scaling", None)
            if combo.current() == 1:
                data["space"] = graph_model.SPACE_SCREEN
            else:
                data.pop("space", None)
        return apply_scaling

    def _warn_if_offscreen(self, point):
        w, h = screenutil.logical_screen_size()
        x, y = point
        if not (0 <= x < w and 0 <= y < h):
            self.log_line(
                u"주의: (%d, %d)는 주 모니터(0,0 %dx%d) 밖입니다. "
                u"이 프로젝트는 Screen(0) 기준으로 동작하므로 매칭이 어긋날 수 있습니다."
                % (x, y, w, h), "err")

    def _browse_image(self, target, name, var, commit):
        """이미 있는 이미지를 썸네일로 보고 고른다.

        바깥 파일은 절대 경로로 참조하지 않고 매크로 폴더로 복사한다.
        그래야 매크로 폴더만 옮겨도 그대로 동작한다.
        """
        if not self.macro.path:
            messagebox.showinfo(u"먼저 저장",
                                u"이미지를 둘 폴더가 필요합니다. 매크로를 먼저 저장해 주세요.")
            self.save_macro()
            if not self.macro.path:
                return

        picked = imagepicker.ask_image(
            self.root, self.resource_dir(), MACROS_DIR,
            current=target.get(name),
            on_capture=lambda: self._capture_image(target, name, var, commit))
        if not picked:
            return
        var.set(picked)
        commit()
        self.refresh_project()
        self.log_line(u"이미지 지정: %s" % picked, "ok")

    def _capture_image(self, target, name, var, commit):
        if not self.macro.path:
            messagebox.showinfo(u"먼저 저장", u"이미지를 저장할 위치가 필요합니다.\n"
                                             u"매크로를 먼저 저장해 주세요.")
            self.save_macro()
            if not self.macro.path:
                return

        default_name = var.get().strip() or (u"image_%d.png" % (self.macro.count() + 1))
        filename = simpledialog.askstring(u"이미지 이름", u"저장할 파일 이름",
                                          initialvalue=default_name, parent=self.root)
        if not filename:
            return
        if not filename.lower().endswith(".png"):
            filename += ".png"

        # 하위 매크로의 이미지는 부모 폴더에 저장한다 - 가족이 공유한다
        dest = self._capture_destination(filename)

        def pick_then_capture():
            """영역 선택과 실제 캡처를 **한 번의 숨김 안에서** 끝낸다.

            둘을 나누면 캡처하는 순간 편집기 창이 이미 화면에 돌아와 있다.
            게다가 capture_region 은 JVM 이 끝날 때까지 GUI 스레드를 붙잡아
            창이 다시 그려지지도 못하므로, 되살아난 창이 흰 사각형인 채로
            대상 위에 얹혀 그대로 찍혔다.
            """
            region = pickers.pick_region(self.root)
            if not region:
                return None, False, u""
            # 오버레이를 없앤 화면이 실제로 다시 그려질 때까지 기다린다.
            # 기다리지 않으면 오버레이가 남은 화면이 찍힌다.
            self.root.update()
            time.sleep(CAPTURE_SETTLE_SEC)
            ok, detail = runner.capture_region(
                *region, dest_png=dest,
                on_line=lambda t: self.log_queue.put((t, None)))
            return region, ok, detail

        self.status.set(u"OculiX로 캡처 중... (JVM 기동에 몇 초 걸립니다)")
        self.root.update_idletasks()
        region, ok, detail = self.run_with_window_hidden(pick_then_capture)
        if region is None:
            self.status.set(u"캡처 취소")
            return

        if ok:
            var.set(filename)
            commit()
            self.log_line(u"캡처 저장: %s  영역 %s"
                          % (os.path.relpath(dest, self.resource_dir()), region),
                          "ok")
            self.status.set(u"캡처 완료: %s" % filename)
            self._warn_if_offscreen(region[:2])
        else:
            self.log_line(u"캡처 실패: %s" % detail, "err")
            self.status.set(u"캡처 실패")

    # --------------------------------------------------------------- 파일 조작

    def _confirm_discard(self):
        # 아직 안 들어간 입력이 있으면 dirty 가 아니어서 "저장할까요?" 를
        # 묻지도 않고 그냥 버려진다. 묻기 전에 먼저 반영한다.
        self.flush_property_edits()
        if not self.macro.dirty:
            self._flush_last_selected()
            return True
        answer = messagebox.askyesnocancel(
            u"저장하지 않은 변경", u"변경 내용을 저장할까요?")
        if answer is None:
            return False
        if answer:
            return self.save_macro()
        self._flush_last_selected()
        return True

    def new_macro(self):
        if not self._confirm_discard():
            return
        name = simpledialog.askstring(u"새 매크로", u"매크로 이름",
                                      initialvalue=u"새 매크로", parent=self.root)
        if not name:
            return
        self.macro = model.Macro(graph_model.blank(name))
        self.current_path = None
        self.apply_mode()
        self.status.set(u"새 매크로: %s" % name)
        self.log_line(u"빈 곳을 우클릭해서 첫 노드를 추가하세요.", "info")

    def open_macro(self):
        if not self._confirm_discard():
            return
        if not os.path.isdir(MACROS_DIR):
            os.makedirs(MACROS_DIR)
        path = filedialog.askopenfilename(
            title=u"매크로 열기", initialdir=MACROS_DIR,
            filetypes=[("macro.json", "*.json")])
        if not path:
            return
        try:
            self.macro = model.Macro.load(path)
        except Exception as exc:
            messagebox.showerror(u"열기 실패", u"%s\n\n%s" % (path, exc))
            return
        unknown = sorted({s.get("type") for s in self.macro.all_steps()
                          if s.get("type") not in schema.STEP_TYPES})
        if unknown:
            self.log_line(u"경고: 편집기가 모르는 단계가 있습니다: %s" % ", ".join(unknown), "err")
        self.current_path = None
        self.apply_mode()
        self.focus_opened_macro()
        self.status.set(u"열림: %s" % path)
        if not self.macro.is_graph:
            self.log_line(u"트리 형식 매크로입니다. [도구 > 그래프로 변환]으로 "
                          u"노드 화면에서 편집할 수 있습니다.", "info")
        missing = self.macro.missing_images()
        if missing:
            self.log_line(u"경고: 없는 이미지 %d건 - %s"
                          % (len(missing), ", ".join(n for _p, n in missing)), "err")

    def save_macro(self):
        # 속성칸에 Enter 를 치지 않은 채 Ctrl+S 를 눌러도 방금 친 값이 들어가야 한다.
        self.flush_property_edits()
        if not self.macro.path:
            return self.save_macro_as()
        try:
            self.macro.save()
        except Exception as exc:
            messagebox.showerror(u"저장 실패", str(exc))
            return False
        self.status.set(u"저장됨: %s" % self.macro.path)
        self._update_title()
        self.refresh_library()
        self.refresh_submacros()
        self.refresh_project()
        return True

    def save_macro_as(self):
        """매크로마다 자기 폴더를 만들어 저장한다.

        예전에는 파일 대화상자를 Macros 루트에서 열었는데, 그러면 이름만 바꿔
        저장했을 때 폴더 없이 Macros 루트에 파일이 놓인다. 그 상태는 라이브러리
        규칙에 맞지 않고 이미지 기준 폴더도 어긋난다. 그래서 이름만 받는다.
        """
        if not os.path.isdir(MACROS_DIR):
            os.makedirs(MACROS_DIR)
        suggestion = self.macro.data.get("name") or u"새 매크로"
        suggestion = "".join(c for c in suggestion
                             if c not in '\\/:*?"<>|').strip() or u"Macro"

        while True:
            folder_name = simpledialog.askstring(
                u"매크로 저장",
                u"매크로 이름을 입력하세요.\n"
                u"Macros\\<이름>\\macro.json 으로 저장되고,\n"
                u"이 매크로가 쓰는 이미지도 그 폴더에 놓입니다.",
                initialvalue=suggestion, parent=self.root)
            if not folder_name:
                return False
            folder_name = folder_name.strip()
            bad = set('\\/:*?"<>|')
            if bad & set(folder_name):
                messagebox.showerror(u"저장", u"이름에 쓸 수 없는 문자가 있습니다.")
                continue
            folder = os.path.join(MACROS_DIR, folder_name)
            target = os.path.join(folder, "macro.json")
            if os.path.exists(target):
                if messagebox.askyesno(u"덮어쓰기",
                                       u"'%s' 이 이미 있습니다. 덮어쓸까요?"
                                       % folder_name):
                    break
                suggestion = folder_name
                continue
            break

        try:
            self.macro.save(target)
        except Exception as exc:
            messagebox.showerror(u"저장 실패", str(exc))
            return False
        self.status.set(u"저장됨: %s" % target)
        self._update_title()
        self.refresh_library()
        self.refresh_submacros()
        self.refresh_project()
        # 이제 이미지 폴더가 생겼다. 캔버스가 아직 예전 기준(대개 None)을
        # 들고 있으면 썸네일도, 붙여넣을 때 가져오는 이미지도 갈 곳을 잃는다.
        if self.mode == "graph" and self.canvas_view is not None:
            self.canvas_view.base_dir = self.resource_dir()
            self.canvas_view.redraw()
        self.log_line(u"이미지는 이 폴더에 놓입니다: %s" % self.resource_dir(),
                      "info")
        return True

    def _update_title(self):
        mark = u" *" if self.macro.dirty else u""
        where = self.macro.path or u"(저장 안 됨)"
        self.root.title(u"OculiX 매크로 편집기 — %s%s"
                        % (self.macro.data.get("name", u""), mark))
        self.status_path = where
        self._sync_view_title()

    def mark_dirty(self):
        self.macro.dirty = True
        self._update_title()

    # --------------------------------------------------------------- 도구

    def _build_param_editor(self, parent, dialog):
        """매개변수 선언 목록을 편집한다. UE 의 public variable 목록에 해당한다.

        선언은 macro.json 최상위 `params` 에 저장된다. 설정(settings)이 아니라
        최상위인 이유: 실행 환경 설정이 아니라 이 매크로의 **인터페이스**다.
        """
        for child in parent.winfo_children():
            child.destroy()

        params = self.macro.data.setdefault("params", [])

        head = ttk.Frame(parent)
        head.pack(fill="x")
        for text, width in ((u"이름", 18), (u"타입", 12), (u"기본값", 14)):
            ttk.Label(head, text=text, width=width).pack(side="left")

        type_keys = list(graph_model.PARAM_TYPES)
        type_labels = [graph_model.PARAM_TYPE_LABELS[t] for t in type_keys]

        def redraw():
            self.mark_dirty()
            self._build_param_editor(parent, dialog)

        for index, param in enumerate(params):
            line = ttk.Frame(parent)
            line.pack(fill="x", pady=2)

            name_var = tk.StringVar(value=param.get("name", ""))
            entry = ttk.Entry(line, textvariable=name_var, width=18)
            entry.pack(side="left")

            def rename(_e=None, param=param, name_var=name_var):
                param["name"] = name_var.get().strip()
                self.mark_dirty()
            entry.bind("<FocusOut>", rename)
            entry.bind("<Return>", rename)

            combo = ttk.Combobox(line, values=type_labels, state="readonly",
                                 width=10)
            ptype = param.get("type", "string")
            if ptype in type_keys:
                combo.current(type_keys.index(ptype))
            combo.pack(side="left", padx=2)

            def retype(_e=None, param=param, combo=combo):
                param["type"] = type_keys[combo.current()]
                self.mark_dirty()
            combo.bind("<<ComboboxSelected>>", retype)

            default_var = tk.StringVar(
                value=self._value_to_text(param.get("default"))
                if "default" in param else "")
            dentry = ttk.Entry(line, textvariable=default_var, width=14)
            dentry.pack(side="left", padx=2)

            def set_default(_e=None, param=param, default_var=default_var):
                text = default_var.get().strip()
                if text == "":
                    param.pop("default", None)   # 기본값 없음 = 호출 시 필수
                    self.mark_dirty()
                    return
                try:
                    param["default"] = graph_model.coerce_param(
                        text, param.get("type"), param.get("name") or u"기본값")
                except graph_model.ParamError as exc:
                    messagebox.showerror(u"기본값", u"%s" % exc, parent=dialog)
                    return
                self.mark_dirty()
            dentry.bind("<FocusOut>", set_default)
            dentry.bind("<Return>", set_default)

            def remove(index=index):
                params.pop(index)
                redraw()
            ttk.Button(line, text=u"삭제", width=6, command=remove).pack(
                side="left", padx=(4, 0))

        def add():
            existing = set(graph_model.param_names(self.macro.data))
            number = len(params) + 1
            while ("param%d" % number) in existing:
                number += 1
            params.append({"name": "param%d" % number, "type": "string"})
            redraw()
        ttk.Button(parent, text=u"+ 매개변수 추가", command=add).pack(
            anchor="w", pady=(6, 0))

        if params:
            ttk.Label(parent,
                      text=u"기본값을 비우면 호출할 때 반드시 값을 넘겨야 합니다.",
                      style="Dim.TLabel").pack(anchor="w", pady=(4, 0))

    def edit_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(u"매크로 설정")
        dialog.transient(self.root)
        dialog.grab_set()
        settings = self.macro.data.setdefault("settings", {})

        _root, _editing_sub = self._family_state()
        if _editing_sub:
            ttk.Label(dialog,
                      text=u"⚠ 하위 매크로는 실행 설정(모니터·정확도·시간 등)을 "
                           u"부모의 것으로 상속합니다. 여기의 실행 설정 값은 "
                           u"무시됩니다. 이름과 매개변수는 그대로 쓰입니다.",
                      wraplength=360, padding=(12, 8, 12, 0),
                      foreground="#c8a200").pack(fill="x")

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=u"이름", width=16).grid(row=0, column=0, sticky="w", pady=3)
        name_var = tk.StringVar(value=self.macro.data.get("name", ""))
        ttk.Entry(frame, textvariable=name_var, width=32).grid(row=0, column=1, sticky="we")

        fields = [
            ("screen", u"모니터 번호", "int"),
            ("defaultSimilarity", u"기본 정확도", "float"),
            ("defaultTimeout", u"기본 제한시간(초)", "float"),
            ("stepDelay", u"단계 간 대기(초)", "float"),
            ("defaultSettle", u"기본 멈춤 확인(초)", "float"),
            ("ocrLanguage", u"글자 인식 언어", "str"),
        ]
        vars_ = {}
        for i, (key, label, _kind) in enumerate(fields, start=1):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=self._value_to_text(settings.get(key)))
            if key == "ocrLanguage":
                # 설치된 언어만 쓸 수 있고 한 번에 하나뿐이다.
                # "kor+eng" 같은 조합은 OculiX 가 거부한다.
                ttk.Combobox(frame, textvariable=var, width=30,
                             values=["eng", "kor", "chi_sim", "fra", "hin", "spa"]
                             ).grid(row=i, column=1, sticky="we")
            else:
                ttk.Entry(frame, textvariable=var, width=32).grid(
                    row=i, column=1, sticky="we")
            vars_[key] = var

        row = len(fields) + 1
        ttk.Label(frame, text=u"기본 검색 영역").grid(row=row, column=0, sticky="w", pady=3)
        region_var = tk.StringVar(value=self._value_to_text(settings.get("searchRegion")))
        region_row = ttk.Frame(frame)
        region_row.grid(row=row, column=1, sticky="we")
        ttk.Entry(region_row, textvariable=region_var).pack(side="left", fill="x", expand=True)

        def pick():
            dialog.withdraw()
            try:
                region = self.run_with_window_hidden(
                    lambda: pickers.pick_region(self.root))
            finally:
                dialog.deiconify()
            if region:
                stored = self._stored_region(region)
                if stored is not None:
                    region_var.set("%d, %d, %d, %d" % tuple(stored))
        ttk.Button(region_row, text=u"드래그", command=pick).pack(side="left", padx=4)

        row += 1
        param_box = ttk.LabelFrame(frame, text=u"매개변수 (이 매크로를 호출할 때 넘길 값)",
                                   padding=6)
        param_box.grid(row=row, column=0, columnspan=2, sticky="we", pady=(10, 0))
        self._build_param_editor(param_box, dialog)

        row += 1
        scale_box = ttk.LabelFrame(frame, text=u"해상도 대응", padding=6)
        scale_box.grid(row=row, column=0, columnspan=2, sticky="we", pady=(10, 0))
        apply_scaling = self._build_scaling_editor(scale_box, dialog)

        def apply_():
            self.macro.data["name"] = name_var.get()
            apply_scaling()
            for key, _label, kind in fields:
                text = vars_[key].get().strip()
                if text == "":
                    settings.pop(key, None)
                else:
                    try:
                        settings[key] = self._text_to_value(kind, text)
                    except ValueError as exc:
                        messagebox.showerror(u"입력 오류", u"%s: %s" % (key, exc))
                        return
            text = region_var.get().strip()
            if text == "":
                settings.pop("searchRegion", None)
            else:
                try:
                    settings["searchRegion"] = self._text_to_value("region", text)
                except ValueError as exc:
                    messagebox.showerror(u"입력 오류", str(exc))
                    return
            self.mark_dirty()
            dialog.destroy()

        bar = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        bar.pack(fill="x")
        ttk.Button(bar, text=u"확인", command=apply_).pack(side="right", padx=3)
        ttk.Button(bar, text=u"취소", command=dialog.destroy).pack(side="right")

    def edit_watch(self):
        """감시 설정 - 이 매크로가 거는 감시 목록과, 이 매크로 자신의 감시 조건.

        둘은 서로 다른 역할이다. 위쪽은 '이 매크로가 도는 동안 무엇을
        감시할지', 아래쪽은 '이 매크로를 다른 매크로가 감시로 걸 수 있게
        할지' 다. 한 매크로가 둘 다 가질 수는 있지만, 감시로 불려서 도는
        동안에는 감시하지 않으므로 그때 위쪽 목록은 쓰이지 않는다.
        """
        self.flush_property_edits()
        data = self.macro.data
        dialog = tk.Toplevel(self.root)
        dialog.title(u"감시 설정")
        dialog.transient(self.root)
        dialog.grab_set()
        _root, editing_sub = self._family_state()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)

        # ---------------------------------------------- 이 매크로가 거는 감시
        box = ttk.LabelFrame(frame, text=u"이 매크로가 도는 동안 걸 감시 매크로",
                             padding=8)
        box.pack(fill="x")
        ttk.Label(box, style="Dim.TLabel", wraplength=440, justify="left",
                  text=u"목록 순서대로 확인합니다. 이 매크로를 부른 쪽(부모)의 "
                       u"감시가 먼저 돌고, 이 매크로가 끝나면 이 목록은 "
                       u"걷힙니다. 최상위로 실행하면 실행 내내 걸리는 전역 "
                       u"감시가 됩니다.").pack(anchor="w", pady=(0, 6))

        row = ttk.Frame(box)
        row.pack(fill="x")
        listbox = tk.Listbox(row, height=5, exportselection=False)
        listbox.pack(side="left", fill="both", expand=True)
        buttons = ttk.Frame(row)
        buttons.pack(side="left", padx=(6, 0))

        def refs():
            current = data.get("handlers")
            return current if isinstance(current, list) else []

        def store(new_refs, select=None):
            if new_refs:
                data["handlers"] = new_refs
            else:
                data.pop("handlers", None)
            self.mark_dirty()
            redraw(select)

        def redraw(select=None):
            listbox.delete(0, "end")
            names = dict(self.watch_candidates())
            for ref in refs():
                name = names.get(ref)
                if name is None:
                    label = u"%s   ⚠ 감시 매크로가 아니거나 찾을 수 없음" % ref
                else:
                    label = self._ref_label(ref, name)
                listbox.insert("end", label)
            if select is not None and 0 <= select < listbox.size():
                listbox.selection_set(select)

        def selected():
            picked = listbox.curselection()
            return picked[0] if picked else None

        def add():
            have = set(refs())
            choices = [(r, n) for r, n in self.watch_candidates() if r not in have]
            if not choices:
                messagebox.showinfo(
                    u"감시 추가",
                    u"걸 수 있는 감시 매크로가 없습니다.\n\n감시 매크로를 "
                    u"만들려면 그 매크로를 열고 [도구 → 감시 설정] 아래쪽에서 "
                    u"'감시 매크로로 쓴다' 를 켜고 감시 조건을 정하세요.",
                    parent=dialog)
                return
            picked = self._choose_from(dialog, u"감시 매크로 추가",
                                       [self._ref_label(r, n) for r, n in choices])
            dialog.grab_set()
            if picked is not None:
                store(refs() + [choices[picked][0]], len(refs()))

        def remove():
            index = selected()
            if index is None:
                return
            new_refs = list(refs())
            new_refs.pop(index)
            store(new_refs, min(index, len(new_refs) - 1))

        def move(delta):
            index = selected()
            if index is None:
                return
            target = index + delta
            new_refs = list(refs())
            if not 0 <= target < len(new_refs):
                return
            new_refs[index], new_refs[target] = new_refs[target], new_refs[index]
            store(new_refs, target)

        for text, command in ((u"추가", add), (u"빼기", remove),
                              (u"위로", lambda: move(-1)),
                              (u"아래로", lambda: move(1))):
            ttk.Button(buttons, text=text, width=7, command=command).pack(pady=1)
        redraw()

        interval_row = ttk.Frame(box)
        interval_row.pack(fill="x", pady=(8, 0))
        ttk.Label(interval_row, text=u"확인 간격(초)").pack(side="left")
        settings = data.setdefault("settings", {})
        interval_var = tk.StringVar(
            value=self._value_to_text(settings.get("handlerInterval")))
        interval_entry = ttk.Entry(interval_row, textvariable=interval_var,
                                   width=8)
        interval_entry.pack(side="left", padx=6)
        if editing_sub:
            interval_entry.configure(state="disabled")
            note = u"하위 매크로는 부모의 간격을 따릅니다"
        else:
            note = (u"비우면 %.1f초. 한 바퀴 확인이 끝난 뒤 이만큼 지나야 다시 "
                    u"확인합니다. 최상위로 실행될 때의 값 하나만 쓰입니다"
                    % graph_model.DEFAULT_HANDLER_INTERVAL)
        ttk.Label(box, text=note, style="Dim.TLabel", wraplength=440,
                  justify="left").pack(anchor="w", pady=(2, 0))

        def commit_interval():
            if editing_sub:
                return True
            text = interval_var.get().strip()
            if text == "":
                settings.pop("handlerInterval", None)
                return True
            try:
                value = float(text)
                if value < 0:
                    raise ValueError(u"0 이상이어야 합니다")
            except ValueError as exc:
                messagebox.showerror(u"입력 오류", u"확인 간격: %s" % exc,
                                     parent=dialog)
                return False
            if settings.get("handlerInterval") != value:
                settings["handlerInterval"] = value
                self.mark_dirty()
            return True

        # ---------------------------------------------- 이 매크로의 감시 조건
        watch_box = ttk.LabelFrame(frame, text=u"이 매크로를 감시 매크로로 쓰기",
                                   padding=8)
        watch_box.pack(fill="x", pady=(10, 0))
        enabled = tk.BooleanVar(value=graph_model.is_watch_macro(data))
        holder = ttk.Frame(watch_box)

        def show_condition():
            for child in holder.winfo_children():
                child.destroy()
            if not enabled.get():
                holder.pack_forget()
                return
            holder.pack(fill="x", pady=(6, 0))
            ConditionEditor(holder, self,
                            lambda: data.get("watch"),
                            lambda value: (data.__setitem__("watch", value),
                                           self.mark_dirty())
                            ).pack(fill="x")
            ttk.Label(holder, style="Dim.TLabel", wraplength=440,
                      justify="left",
                      text=u"조건은 기다리지 않고 지금 화면만 봅니다 (제한시간은 "
                           u"쓰이지 않습니다). 참이면 이 매크로의 노드를 처음부터 "
                           u"실행합니다. 확인할 때마다 화면을 읽으므로 영역을 "
                           u"좁게 잡으세요.").pack(anchor="w", pady=(6, 0))

        def toggle():
            if enabled.get():
                if not graph_model.is_watch_macro(data):
                    data["watch"] = schema.new_condition("imageExists")
            else:
                data.pop("watch", None)
            self.mark_dirty()
            show_condition()

        ttk.Checkbutton(watch_box, text=u"감시 매크로로 쓴다 (다른 매크로의 "
                                        u"감시 목록에 걸 수 있게 한다)",
                        variable=enabled, command=toggle).pack(anchor="w")
        show_condition()

        def close():
            self.flush_property_edits()
            if not commit_interval():
                return
            dialog.destroy()
            self.status.set(u"감시 설정을 바꿨습니다 - 저장해야 반영됩니다"
                            if self.macro.dirty else u"감시 설정")

        dialog.protocol("WM_DELETE_WINDOW", close)
        bar = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        bar.pack(fill="x")
        ttk.Button(bar, text=u"닫기", command=close).pack(side="right")

    def _choose_from(self, parent, title, labels):
        """목록에서 하나를 고르게 한다. 고른 위치, 취소하면 None."""
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.transient(parent)
        dialog.grab_set()
        listbox = tk.Listbox(dialog, height=min(12, max(4, len(labels))),
                             width=48, exportselection=False)
        listbox.pack(fill="both", expand=True, padx=10, pady=10)
        for label in labels:
            listbox.insert("end", label)
        listbox.selection_set(0)
        result = {"index": None}

        def confirm(_e=None):
            picked = listbox.curselection()
            if picked:
                result["index"] = picked[0]
            dialog.destroy()

        listbox.bind("<Double-Button-1>", confirm)
        listbox.bind("<Return>", confirm)
        bar = ttk.Frame(dialog, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text=u"추가", command=confirm).pack(side="right", padx=3)
        ttk.Button(bar, text=u"취소", command=dialog.destroy).pack(side="right")
        listbox.focus_set()
        dialog.wait_window()
        return result["index"]

    @staticmethod
    def system_dpi():
        """OculiX 가 보는 시스템 DPI. 96 x 화면 배율 (이 PC 는 125% 라 120).

        투명 템플릿 검사(pnginfo.mask_dpi_risk)의 기준이다. 편집기가 캡처한
        템플릿에는 이 값이 기록된다.
        """
        return 96.0 * screenutil.scale()[0]

    def validate_macro(self):
        self.flush_property_edits()
        warnings = []
        if self.mode == "graph" and self.graph is not None:
            problems, warnings = self.graph.validate()
        else:
            problems = self.macro.validate(warnings)
        missing = self.macro.missing_images()
        problems = list(problems) + self.check_call_targets()
        handler_errors, handler_warnings = self.check_handler_targets()
        problems.extend(handler_errors)
        warnings = list(warnings) + handler_warnings
        warnings.extend(u"이미지 %s (%s): %s" % (name, where, why)
                        for where, name, why
                        in self.macro.risky_images(self.system_dpi()))
        warnings.extend(self._scaling_warnings())

        for w in warnings:
            self.log_line(u"경고: %s" % w, "err")
        if not problems and not missing:
            unit = u"노드" if self.mode == "graph" else u"단계"
            self.log_line(u"검사 통과 - %d%s, 오류 없음" % (self.macro.count(), unit), "ok")
            self.status.set(u"검사 통과%s" % (u" (경고 %d건)" % len(warnings) if warnings else u""))
            return True
        for p in problems:
            self.log_line(u"정의 오류: %s" % p, "err")
        for where, name in missing:
            self.log_line(u"이미지 없음: %s (%s)" % (name, where), "err")
        self.status.set(u"문제 %d건" % (len(problems) + len(missing)))
        return False

    def show_screen_info(self):
        lw, lh = screenutil.logical_screen_size()
        pw, ph = screenutil.physical_screen_size()
        sx, sy = screenutil.scale()
        messagebox.showinfo(
            u"화면 정보",
            u"주 모니터\n"
            u"  논리 해상도 : %d x %d   ← 매크로 좌표는 이 기준\n"
            u"  물리 해상도 : %d x %d\n"
            u"  배율        : %.3f\n\n"
            u"마우스로 찍은 좌표는 논리 좌표이고 OculiX와 같은 좌표계입니다.\n"
            u"화면 캡처는 배율 차이 때문에 OculiX에 맡깁니다.\n\n"
            u"해상도 대응\n%s"
            % (lw, lh, pw, ph, sx, self._scaling_text(self.macro.scaling)))

    def verify_coordinates(self):
        """편집기와 OculiX가 같은 지점을 가리키는지 실제로 대조한다."""
        self.log_line(u"좌표계 대조: 화면에서 한 점을 찍어 주세요.", "info")
        result = self.run_with_window_hidden(
            lambda: pickers.pick_color(self.root))
        if not result:
            return
        x, y = result["point"]
        editor_rgb = tuple(result["rgb"])
        self.log_line(u"편집기 (%d, %d) -> %s" % (x, y, editor_rgb), "info")
        self.status.set(u"OculiX로 같은 좌표 읽는 중...")
        self.root.update_idletasks()
        oculix_rgb = runner.read_pixel_via_oculix(x, y)
        if oculix_rgb is None:
            self.log_line(u"OculiX 읽기 실패", "err")
            return
        self.log_line(u"OculiX  (%d, %d) -> %s" % (x, y, oculix_rgb), "info")
        diff = max(abs(a - b) for a, b in zip(editor_rgb, oculix_rgb))
        if diff <= 8:
            self.log_line(u"좌표계 일치 (최대 채널 차이 %d)" % diff, "ok")
            self.status.set(u"좌표계 일치")
        else:
            self.log_line(
                u"좌표계 불일치 (최대 채널 차이 %d). 화면이 바뀐 것이 아니라면 "
                u"편집기가 찍은 좌표를 OculiX가 다르게 해석하는 것입니다." % diff, "err")
            self.status.set(u"좌표계 불일치")

    # ----------------------------------------------------------------- 보기

    def goto_entry_node(self):
        """시작 노드가 화면 밖에 있어도 찾아갈 수 있게 화면을 그쪽으로 옮긴다.

        다른 매크로를 열면 노드가 저장된 좌표에 그려지므로, 지금 보고 있던
        자리와 멀면 캔버스가 텅 빈 것처럼 보인다. 그때 쓰는 버튼이다.
        배율과 선택은 그대로 두고 보는 위치만 옮긴다.
        """
        if self.mode != "graph" or getattr(self, "canvas_view", None) is None:
            self.status.set(u"노드 모드에서만 됩니다")
            return
        if not self.canvas_view.focus_entry():
            self.status.set(u"시작 노드가 없습니다")
            return
        self.canvas_view.canvas.focus_set()
        self.status.set(u"시작 노드로 이동했습니다")

    # --------------------------------------------------------------- 실행

    def run_from_selected_node(self):
        """노드 하나만 골라 뒀을 때, 그 노드부터 실행한다.

        긴 흐름의 뒷부분만 확인할 때 쓴다. 매크로에 저장된 시작 노드는
        그대로 두고 이번 실행에만 적용한다.
        """
        if self.mode != "graph":
            self.status.set(u"노드 모드에서만 됩니다")
            return
        picked = sorted(self.canvas_view.selected_nodes)
        if len(picked) != 1:
            self.status.set(
                u"노드를 하나만 선택하세요 (지금 %d개)" % len(picked))
            return
        self.run_macro(start_node=picked[0])

    def resume_macro(self):
        """지난 실패 때 남긴 위치 - **실패한 노드** - 부터 이어서 실행한다."""
        saved = runner.read_resume(self.macro.path)
        if not saved:
            self.status.set(u"이어서 실행할 위치가 없습니다")
            return
        if not messagebox.askyesno(
                u"이어서 실행",
                u"실패한 노드부터 이어서 실행합니다.\n\n%s\n\n"
                u"(%s 에 실패: %s)\n\n"
                u"지나고 있던 반복은 각각 그 회차부터 이어서 돕니다.\n"
                u"게임/앱 화면이 실패했던 그 자리에 있어야 합니다. 엉뚱한 "
                u"화면이면 그대로 입력이 들어갈 수 있습니다.\n\n계속할까요?"
                % (runner.describe_resume(saved),
                   saved.get("savedAt") or u"?",
                   saved.get("reason") or u"?")):
            return
        self.run_macro(resume=True)

    def refresh_resume_button(self):
        """[이어서 실행] 을 켤지 정한다. 이 매크로의 실패 기록이 있을 때만 켠다."""
        button = self.resume_button
        if button is None:
            return
        saved = runner.read_resume(self.macro.path)
        if saved:
            state, text = "normal", (u"⏭ 이어서: %s"
                                     % (saved.get("failedName") or u"?"))
        else:
            state, text = "disabled", u"⏭ 이어서 실행 (Ctrl+F5)"
        try:
            button.config(state=state, text=text)
        except tk.TclError:
            pass

    def run_macro(self, start_node=None, resume=False):
        if self.job and self.job.is_running():
            return
        # dirty 판정보다 먼저다. 아직 안 들어간 값이 있으면 dirty 가 아니어서
        # 저장을 건너뛰고 옛 파일이 실행된다.
        self.flush_property_edits()
        if not self.macro.path:
            messagebox.showinfo(u"먼저 저장", u"실행하려면 매크로를 저장해야 합니다.")
            if not self.save_macro():
                return
        elif self.macro.dirty:
            self.save_macro()

        if not self.validate_macro():
            if not messagebox.askyesno(u"문제 발견",
                                       u"검사에서 문제가 나왔습니다. 그래도 실행할까요?"):
                return

        node = self.graph.node(start_node) if (start_node and self.graph) else None
        label = schema.summarize(node) if node else None

        self.log_line(u"", None)
        # 파일을 먼저 연다. 아래 머리말부터 파일에도 함께 들어가야 한다.
        self._open_runlog(start_node, label)
        self.log_line(u"===== 실행: %s =====" % self.macro.path, "info")
        if start_node:
            self.log_line(u"===== 시작 노드: %s (%s) ====="
                          % (start_node, label or start_node), "info")
        self.run_button.config(state="disabled")
        self.stop_button.config(state="normal")
        if self.resume_button is not None:
            self.resume_button.config(state="disabled")
        self.status.set(u"실행 중...%s" % (
            u" (이어서)" if resume
            else (u" (선택 노드부터)" if start_node else u"")))
        if not resume:
            # 처음부터 도는 실행이다. 낡은 기록이 남아 있으면 이번 실행이
            # 성공해도 [이어서 실행] 이 켜진 채로 남는다.
            runner.clear_resume()
        self.job = runner.run_macro(
            self.macro.path,
            lambda text: self.log_queue.put((text, None)),
            lambda code: self.log_queue.put((("__DONE__", code), None)),
            start_node=start_node, resume=resume)
        self._start_pause_controls()

    def stop_macro(self):
        if self.job:
            self.job.stop()

    # ------------------------------------------------------------ 일시정지

    def toggle_pause(self):
        """일시정지 / 재개. 툴바 버튼과 F6 이 함께 쓴다."""
        job = self.job
        if not job or not job.is_running():
            return
        if self.paused:
            job.unpause()
            self.paused = False
            self.pause_button.config(text=PAUSE_LABEL)
            self.status.set(u"실행 중...")
            return
        if not job.pause():
            self.status.set(u"일시정지를 요청하지 못했습니다")
            return
        self.paused = True
        self.pause_button.config(text=RESUME_LABEL)
        # 아직 멈춘 것이 아니다. 엔진이 멈추면 로그 표식으로 알려 온다.
        self.status.set(u"일시정지 요청 - 진행 중인 동작이 끝나면 멈춥니다")

    def _start_pause_controls(self):
        """실행을 시작할 때. 버튼을 켜고 전역 단축키를 등록한다."""
        self.paused = False
        self.pause_button.config(state="normal", text=PAUSE_LABEL)
        if self.pause_hotkey is None:
            # 메시지 스레드에서 불린다. tkinter 를 건드리면 안 되므로 큐로 넘긴다.
            self.pause_hotkey = hotkey.GlobalHotkey(
                hotkey.VK_F6,
                lambda: self.log_queue.put((("__PAUSE_KEY__", None), None)))
        if not self.pause_hotkey.start():
            self.log_line(u"전역 단축키 F6 을 쓸 수 없습니다: %s. 일시정지는 "
                          u"툴바 버튼이나 편집기 창 안에서의 F6 으로 하세요"
                          % self.pause_hotkey.error, "err")

    def _stop_pause_controls(self):
        """실행이 끝났을 때. 끝난 뒤에는 F6 을 다른 프로그램에 돌려준다."""
        self.paused = False
        if self.pause_button is not None:
            self.pause_button.config(state="disabled", text=PAUSE_LABEL)
        if self.pause_hotkey is not None:
            self.pause_hotkey.stop()

    def _note_pause_line(self, text):
        """엔진의 로그 줄에서 정말 멈췄는지 / 다시 가는지를 읽는다.

        게임 창을 보고 있으면 F6 이 먹었는지 눈으로 알 수 없으므로 소리로도
        알린다. 알림 창은 쓰지 않는다 - 화면에 뜨면 매칭을 가릴 수 있다.
        """
        if graph_model.PAUSED_MARK in text and u"주의" not in text:
            self.status.set(u"일시정지됨 - F6 또는 [재개] 로 이어서 진행합니다")
            _beep(880)
        elif graph_model.RESUMED_MARK in text:
            self.status.set(u"실행 중...")
            _beep(660)

    def _drain_log(self):
        try:
            while True:
                payload, _ = self.log_queue.get_nowait()
                if isinstance(payload, tuple) and payload[0] == "__DONE__":
                    self._on_run_done(payload[1])
                elif isinstance(payload, tuple) \
                        and payload[0] == "__PAUSE_KEY__":
                    self.toggle_pause()
                else:
                    tag = None
                    lowered = payload.lower()
                    if "[error]" in lowered or "fail" in lowered:
                        tag = "err"
                    elif "ok ===" in lowered or "정상" in payload:
                        tag = "ok"
                    self.log_line(payload, tag)
                    self._note_pause_line(payload)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_log)

    def _on_run_done(self, code):
        self.run_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self._stop_pause_controls()
        cancelled = bool(self.job and self.job.cancelled)
        if code == 0:
            self.log_line(u"===== 정상 종료 (exit 0) =====", "ok")
            self.status.set(u"정상 종료")
        elif code == 1:
            self.log_line(u"===== 단계 실패로 중단 (exit 1) =====", "err")
            self.status.set(u"실패로 중단")
        else:
            self.log_line(u"===== 종료 코드 %s =====" % code, "err")
            self.status.set(u"오류 (exit %s)" % code)
        self._close_runlog(code, cancelled)
        self.refresh_resume_button()
        self._notify_run_done(code, cancelled)

    def _on_notify_toggle(self):
        """알림 켜기/끄기. 레이아웃 설정에 함께 저장한다."""
        self.config["notify_on_done"] = bool(self.notify_var.get())
        settings.save(self.config)

    def _notify_run_done(self, code, cancelled):
        """매크로가 끝났다고 Windows 알림으로 알린다.

        긴 매크로는 사용자가 다른 창을 보는 동안 돈다. 상태줄과 로그만으로는
        끝난 줄 모른다. 알림이 실패해도 실행 결과 처리에는 영향을 주지 않는다.
        """
        if not self.notify_var.get():
            return
        name = (self.macro.data.get("name")
                or os.path.basename(self.macro.folder or u"")
                or u"매크로")
        if cancelled:
            result = u"중지했습니다"
        elif code == 0:
            result = u"정상 종료"
        elif code == 1:
            result = u"단계 실패로 중단"
        else:
            result = u"오류 (종료 코드 %s)" % code
        notify.notify(u"OculiX 매크로 — %s" % name, result,
                      on_error=lambda text: self.log_line(text, "err"))

    # ----------------------------------------------------------- 실행 로그

    def _open_runlog(self, start_node=None, start_label=None):
        """이번 실행을 기록할 파일을 연다.

        열지 못해도 실행은 계속한다. 로그를 남기려다 매크로를 못 돌리면
        본말이 전도된다.
        """
        self.runlog = None
        try:
            self.runlog = runlog.start(
                self.macro.path,
                macro_name=self.macro.data.get("name"),
                start_node=start_node, start_label=start_label)
        except Exception as exc:
            self.log_line(u"실행 로그 파일을 열지 못했습니다: %s" % exc, "err")

    def _close_runlog(self, code, cancelled):
        """실행 결과를 적고 로그 파일을 닫는다. 경로를 패널에 알려 준다."""
        if not self.runlog:
            return
        path = self.runlog.path
        self.runlog.finish(code, cancelled)
        self.runlog = None
        self.log_line(u"===== 로그 저장: %s =====" % path, "info")

    def open_log_folder(self):
        """실행 로그가 쌓이는 폴더를 탐색기로 연다."""
        try:
            os.startfile(runlog.ensure_dir())
        except Exception as exc:
            self.log_line(u"로그 폴더를 열지 못했습니다: %s" % exc, "err")
            self.status.set(u"로그 폴더를 열지 못했습니다")

    def log_line(self, text, tag=None):
        # 패널이 다시 지어질 때 내용을 잃지 않도록 버퍼에도 남긴다
        self._log_buffer.append((text, tag))
        # 실행 중이면 파일에도 같은 줄을 남긴다 (닫힌 뒤에는 무시된다)
        if self.runlog is not None:
            self.runlog.line(text)
        if len(self._log_buffer) > 2000:
            del self._log_buffer[:1000]
        widget = getattr(self, "log", None)
        if widget is None:
            return
        try:
            widget.config(state="normal")
            widget.insert("end", text + "\n", tag or ())
            widget.see("end")
            widget.config(state="disabled")
        except tk.TclError:
            pass

    # --------------------------------------------------------------- 종료

    def save_settings(self):
        """레이아웃 / 창 크기 / 프로젝트 트리 펼침 상태를 저장한다."""
        data = dict(self.config)
        try:
            data["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        try:
            data["layout"] = self.dock.get_layout()
        except Exception:
            pass
        try:
            data["expanded"] = self.project.get_expanded()
        except Exception:
            pass
        data["last_macro"] = self.macro.path
        self.config = data
        settings.save(data)

    def reset_layout(self):
        if not messagebox.askyesno(u"레이아웃 초기화",
                                   u"패널 배치를 기본값으로 되돌립니다. 계속할까요?"):
            return
        self.dock.reset()
        self.log_line(u"레이아웃을 기본값으로 되돌렸습니다.", "info")

    def on_close(self):
        if self.job and self.job.is_running():
            if not messagebox.askyesno(u"실행 중", u"실행 중입니다. 중지하고 닫을까요?"):
                return
            self.job.stop()
        if not self._confirm_discard():
            return
        self._stop_pause_controls()
        if self.runlog:
            self.runlog.abort(u"편집기를 닫음")
            self.runlog = None
        self.save_settings()
        self.root.destroy()


def _run():
    root = tk.Tk()
    theme.apply(root)
    app = MacroEditorApp(root)

    # python macro_editor.py <macro.json> 으로 바로 열 수 있다
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        try:
            app.macro = model.Macro.load(sys.argv[1])
            app.apply_mode()
            root.update()      # 창이 그려져야 가운데를 잴 수 있다
            app.focus_opened_macro()
            app.status.set(u"열림: %s" % sys.argv[1])
        except Exception as exc:
            app.log_line(u"열기 실패: %s" % exc, "err")

    root.mainloop()


def main():
    try:
        _run()
    except Exception:
        _crash_log(_crash_report(u"편집기 시작 실패"))
        raise


if __name__ == "__main__":
    main()
