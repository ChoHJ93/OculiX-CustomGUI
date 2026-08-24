# -*- coding: utf-8 -*-
"""프로젝트 패널 - Unity Editor의 Project 창에 해당.

Macros 폴더의 구조와 리소스(매크로 정의, 이미지)를 트리로 보여주고,
이미지를 고르면 미리보기와 크기를 표시한다.

이미지 미리보기는 tkinter 기본 PhotoImage로 처리한다 (외부 라이브러리 없음).
"""

import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import imagecache
import theme


ICON_FOLDER = u"📁"
ICON_MACRO = u"🧩"
ICON_IMAGE = u"🖼"
ICON_FILE = u"📄"

IMAGE_EXT = (".png", ".gif")


class ProjectPanel(ttk.Frame):

    def __init__(self, master, app, root_dir):
        ttk.Frame.__init__(self, master)
        self.app = app
        self.root_dir = root_dir
        self.paths = {}          # tree item id -> 절대 경로
        self._pending_expanded = None   # None = 지정 없음, [] = 전부 접기

        # 제목줄은 도킹 매니저가 그린다 (끌어서 옮길 수 있어야 하므로)
        body = ttk.Frame(self, style="Panel.TFrame")
        body.pack(fill="both", expand=True)

        tree_box = ttk.Frame(body)
        tree_box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_box, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.tag_configure("folder", foreground=theme.FG)
        self.tree.tag_configure("macro", foreground="#9ecbff")
        self.tree.tag_configure("image", foreground="#c3e88d")
        self.tree.tag_configure("other", foreground=theme.FG_FAINT)

        # 미리보기
        preview = ttk.Frame(self, style="Panel.TFrame")
        preview.pack(fill="x")
        ttk.Label(preview, text=u"미리보기", style="Header.TLabel").pack(fill="x")
        self.preview_canvas = tk.Canvas(preview, height=140)
        theme.style_canvas(self.preview_canvas, theme.BG_DARKEST)
        self.preview_canvas.pack(fill="x", padx=6, pady=(4, 2))
        self.info = ttk.Label(preview, text=u"", style="Dim.TLabel",
                              anchor="w", padding=(8, 2, 8, 6))
        self.info.pack(fill="x")
        self._preview_ref = None

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text=u"새로고침", command=self.refresh).pack(
            side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(buttons, text=u"탐색기", command=self.reveal_selected).pack(
            side="left", fill="x", expand=True, padx=(2, 0))

        self.refresh()

    # ------------------------------------------------------------------ 트리

    def refresh(self, keep_path=None):
        keep_path = keep_path or self.selected_path()

        # 어떤 펼침 상태를 적용할지 먼저 정한다.
        #   pending 이 있으면 그것 (명시적으로 지정된 값. 빈 목록 = 전부 접기)
        #   없으면 지금 화면 상태를 그대로 유지
        #   둘 다 없으면(최초) None -> 최상위만 펼친다
        if self._pending_expanded is not None:
            target = list(self._pending_expanded)
            self._pending_expanded = None
        elif self.paths:
            target = self.get_expanded()
        else:
            target = None

        self.tree.delete(*self.tree.get_children())
        self.paths.clear()
        if not os.path.isdir(self.root_dir):
            return
        self._insert_dir("", self.root_dir)

        if target is None:
            for item in self.tree.get_children(""):
                self.tree.item(item, open=True)
        else:
            self._apply_expanded(target)
        if keep_path:
            # 펼침 상태를 명시적으로 적용한 경우에는 see() 로 부모를 자동으로
            # 펼치지 않는다. 그러면 방금 접은 폴더가 다시 열려 버린다.
            self.select_path(keep_path, reveal=(target is None))

    # ------------------------------------------------------------ 펼침 상태

    def get_expanded(self):
        """펼쳐 둔 폴더들의 상대 경로 목록."""
        out = []
        for item, full in self.paths.items():
            if not os.path.isdir(full):
                continue
            try:
                if self.tree.item(item, "open"):
                    out.append(os.path.relpath(full, self.root_dir).replace("\\", "/"))
            except Exception:
                continue
        return sorted(out)

    def set_expanded(self, relative_paths):
        """펼침 상태를 지정한다. 빈 목록은 '전부 접기'라는 뜻이다.

        트리를 아직 안 그렸으면 다음 refresh 때 적용되도록 기억해 둔다.
        """
        wanted = list(relative_paths or [])
        if self.paths:
            self._apply_expanded(wanted)
            self._pending_expanded = None
        else:
            self._pending_expanded = wanted

    def _apply_expanded(self, relative_paths):
        wanted = set(relative_paths or [])
        for item, full in self.paths.items():
            if not os.path.isdir(full):
                continue
            rel = os.path.relpath(full, self.root_dir).replace("\\", "/")
            try:
                self.tree.item(item, open=(rel in wanted))
            except Exception:
                continue

    def _insert_dir(self, parent, path):
        try:
            entries = sorted(os.listdir(path), key=lambda n: (not os.path.isdir(
                os.path.join(path, n)), n.lower()))
        except OSError:
            return
        for name in entries:
            full = os.path.join(path, name)
            if os.path.isdir(full):
                item = self.tree.insert(parent, "end",
                                        text=u"%s %s" % (ICON_FOLDER, name),
                                        tags=("folder",))
                self.paths[item] = full
                self._insert_dir(item, full)
            else:
                lower = name.lower()
                if lower == "macro.json":
                    icon, tag = ICON_MACRO, "macro"
                elif lower.endswith(IMAGE_EXT):
                    icon, tag = ICON_IMAGE, "image"
                else:
                    icon, tag = ICON_FILE, "other"
                item = self.tree.insert(parent, "end",
                                        text=u"%s %s" % (icon, name), tags=(tag,))
                self.paths[item] = full

    def selected_path(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.paths.get(selection[0])

    def select_path(self, path, reveal=True):
        """경로로 항목을 선택. reveal 이 True 면 부모를 펼쳐 보이게 한다."""
        target = os.path.normcase(os.path.abspath(path))
        for item, full in self.paths.items():
            if os.path.normcase(os.path.abspath(full)) == target:
                self.tree.selection_set(item)
                if reveal:
                    self.tree.see(item)
                return True
        return False

    # -------------------------------------------------------------- 미리보기

    def _on_select(self, _event=None):
        path = self.selected_path()
        self.preview_canvas.delete("all")
        self._preview_ref = None
        if not path:
            self.info.config(text=u"")
            return
        if os.path.isdir(path):
            count = 0
            try:
                count = len(os.listdir(path))
            except OSError:
                pass
            self.info.config(text=u"폴더 · 항목 %d개" % count)
            return
        if path.lower().endswith(IMAGE_EXT):
            self._show_image(path)
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        self.info.config(text=u"%s · %d bytes" % (os.path.basename(path), size))

    def _show_image(self, path):
        thumb = imagecache.thumbnail(path, 220, 130)
        original = imagecache.size_of(path)
        if thumb is None:
            self.info.config(text=u"미리보기 실패: %s" % os.path.basename(path))
            return
        self._preview_ref = thumb
        width = self.preview_canvas.winfo_width() or 240
        self.preview_canvas.create_image(width / 2, 68, image=thumb, anchor="center")
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if original:
            self.info.config(text=u"%s · %d x %d · %d bytes"
                             % (os.path.basename(path), original[0], original[1], size))
        else:
            self.info.config(text=os.path.basename(path))

    # ------------------------------------------------------------------ 동작

    def _on_double_click(self, _event=None):
        path = self.selected_path()
        if not path or os.path.isdir(path):
            return
        if os.path.basename(path).lower() == "macro.json":
            self.app.open_macro_path(path)
        elif path.lower().endswith(IMAGE_EXT):
            self.app.assign_image_to_selected(path)

    def _on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
        path = self.selected_path()
        if not path:
            return
        menu = tk.Menu(self, tearoff=0)
        theme.style_menu(menu)
        name = os.path.basename(path)

        if os.path.isdir(path):
            menu.add_command(label=u"탐색기에서 열기",
                             command=lambda: self._reveal(path))
        elif name.lower() == "macro.json":
            menu.add_command(label=u"매크로 열기",
                             command=lambda: self.app.open_macro_path(path))
            menu.add_command(label=u"탐색기에서 열기",
                             command=lambda: self._reveal(path))
        elif path.lower().endswith(IMAGE_EXT):
            menu.add_command(label=u"선택한 노드의 이미지로 지정",
                             command=lambda: self.app.assign_image_to_selected(path))
            menu.add_separator()
            menu.add_command(label=u"이름 변경...",
                             command=lambda: self._rename(path))
            menu.add_command(label=u"삭제", command=lambda: self._delete(path))
            menu.add_separator()
            menu.add_command(label=u"탐색기에서 열기",
                             command=lambda: self._reveal(path))
        else:
            menu.add_command(label=u"탐색기에서 열기",
                             command=lambda: self._reveal(path))
        menu.tk_popup(event.x_root, event.y_root)

    def reveal_selected(self):
        path = self.selected_path() or self.root_dir
        self._reveal(path)

    @staticmethod
    def _reveal(path):
        try:
            if os.path.isdir(path):
                subprocess.Popen(["explorer", os.path.normpath(path)])
            else:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        except Exception:
            pass

    def _rename(self, path):
        old = os.path.basename(path)
        new = simpledialog.askstring(u"이름 변경", u"새 파일 이름",
                                     initialvalue=old, parent=self)
        if not new or new == old:
            return
        if not new.lower().endswith(IMAGE_EXT):
            new += os.path.splitext(old)[1]
        target = os.path.join(os.path.dirname(path), new)
        if os.path.exists(target):
            messagebox.showerror(u"이름 변경", u"같은 이름의 파일이 이미 있습니다.")
            return
        users = self.app.find_image_users(path)
        if users and not messagebox.askyesno(
                u"이름 변경",
                u"이 이미지를 참조하는 단계가 %d곳 있습니다.\n"
                u"이름을 바꾸면 그 참조도 함께 고칩니다. 계속할까요?" % len(users)):
            return
        try:
            os.rename(path, target)
        except OSError as exc:
            messagebox.showerror(u"이름 변경 실패", str(exc))
            return
        imagecache.forget(path)
        self.app.rename_image_references(old, new, path)
        self.refresh(target)
        self.app.log_line(u"이미지 이름 변경: %s -> %s" % (old, new), "ok")

    def _delete(self, path):
        name = os.path.basename(path)
        users = self.app.find_image_users(path)
        message = u"'%s' 파일을 삭제합니다." % name
        if users:
            message += u"\n\n이 이미지를 참조하는 단계가 %d곳 있습니다. " \
                       u"삭제하면 그 단계가 실패합니다." % len(users)
        message += u"\n\n되돌릴 수 없습니다. 계속할까요?"
        if not messagebox.askyesno(u"이미지 삭제", message):
            return
        try:
            os.remove(path)
        except OSError as exc:
            messagebox.showerror(u"삭제 실패", str(exc))
            return
        imagecache.forget(path)
        self.refresh()
        self.app.log_line(u"이미지 삭제: %s" % name, "err")
