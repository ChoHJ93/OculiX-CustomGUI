# -*- coding: utf-8 -*-
"""이미지 선택 창.

이미 있는 이미지를 썸네일로 훑어보고 고른다. 세 가지 경로가 있다.

* **이 매크로 폴더** — 그대로 쓴다. 파일 이름만 저장되므로 매크로가 이식 가능하다
* **다른 매크로 폴더** — 고르면 이 매크로 폴더로 **복사**한다
* **파일에서 가져오기** — 아무 위치의 파일을 이 매크로 폴더로 **복사**한다

밖의 파일을 절대 경로로 참조하지 않고 복사하는 이유는, 매크로 폴더만 옮기면
어디서든 돌아가야 하기 때문이다.
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import imagecache
import theme

IMAGE_EXT = (".png", ".gif")
THUMB = 44


def _is_image(name):
    return name.lower().endswith(IMAGE_EXT)


def scan_images(macro_folder, macros_root):
    """(구분, 표시이름, 절대경로) 목록. 이 매크로 폴더가 먼저 온다."""
    here = []
    others = []
    folder_norm = os.path.normcase(os.path.abspath(macro_folder)) \
        if macro_folder else None

    if macro_folder and os.path.isdir(macro_folder):
        for name in sorted(os.listdir(macro_folder)):
            path = os.path.join(macro_folder, name)
            if os.path.isfile(path) and _is_image(name):
                here.append(("here", name, path))

    if macros_root and os.path.isdir(macros_root):
        for dirpath, _dirs, files in os.walk(macros_root):
            if folder_norm and os.path.normcase(os.path.abspath(dirpath)) == folder_norm:
                continue
            for name in sorted(files):
                if not _is_image(name):
                    continue
                path = os.path.join(dirpath, name)
                rel = os.path.relpath(path, macros_root).replace("\\", "/")
                others.append(("other", rel, path))
    return here + others


def copy_into_folder(parent, folder, source):
    """바깥 이미지를 매크로 폴더로 복사하고 파일 이름을 반환. 취소하면 None.

    절대 경로로 참조하는 대신 복사하는 이유: 매크로 폴더만 옮겨도 동작해야 한다.
    """
    # 호출부가 이미 '매크로 저장됨'을 확인한다. 여기서 대화상자를 띄우면
    # 화면 없는 환경(테스트 등)에서 영원히 멈춘다.
    if not folder:
        return None
    name = os.path.basename(source)
    target = os.path.join(folder, name)

    if os.path.exists(target):
        if os.path.normcase(os.path.abspath(source)) == \
                os.path.normcase(os.path.abspath(target)):
            return name          # 이미 이 폴더에 있는 파일이다
        answer = messagebox.askyesnocancel(
            u"이름 충돌",
            u"'%s' 이 이미 이 폴더에 있습니다.\n\n"
            u"예 = 덮어쓰기, 아니오 = 다른 이름으로 저장" % name,
            parent=parent)
        if answer is None:
            return None
        if not answer:
            new_name = simpledialog.askstring(
                u"다른 이름", u"저장할 파일 이름", initialvalue=name, parent=parent)
            if not new_name:
                return None
            if not _is_image(new_name):
                new_name += os.path.splitext(name)[1] or ".png"
            name = new_name
            target = os.path.join(folder, name)
    try:
        shutil.copyfile(source, target)
    except Exception as exc:
        messagebox.showerror(u"복사 실패", str(exc), parent=parent)
        return None
    imagecache.forget(target)
    return name


class ImagePickerDialog(tk.Toplevel):

    def __init__(self, parent, macro_folder, macros_root, current=None,
                 on_capture=None):
        tk.Toplevel.__init__(self, parent)
        self.title(u"이미지 선택")
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.macro_folder = macro_folder
        self.macros_root = macros_root
        self.on_capture = on_capture
        self.result = None
        self._rows = {}
        self._thumbs = []
        self._preview_ref = None

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=u"이 매크로 폴더의 이미지는 파일 이름만 저장됩니다. "
                              u"다른 곳의 이미지는 이 폴더로 복사됩니다.",
                  style="Dim.TLabel", wraplength=560).pack(anchor="w", pady=(0, 8))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        list_box = ttk.Frame(body)
        list_box.pack(side="left", fill="both", expand=True)

        style = ttk.Style(self)
        style.configure("Gallery.Treeview", rowheight=THUMB + 8)
        self.tree = ttk.Treeview(list_box, show="tree", selectmode="browse",
                                 style="Gallery.Treeview")
        scroll = ttk.Scrollbar(list_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-Button-1>", lambda e: self._confirm())

        side = ttk.Frame(body, width=200)
        side.pack(side="left", fill="y", padx=(10, 0))
        ttk.Label(side, text=u"미리보기", style="Dim.TLabel").pack(anchor="w")
        self.preview = tk.Canvas(side, width=200, height=150)
        theme.style_canvas(self.preview, theme.BG_DARKEST)
        self.preview.pack(pady=(2, 6))
        self.info = ttk.Label(side, text=u"", style="Dim.TLabel", wraplength=200)
        self.info.pack(anchor="w")

        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text=u"파일에서 가져오기...",
                   command=self._import_file).pack(side="left")
        if on_capture:
            ttk.Button(bar, text=u"화면 캡처...",
                       command=self._capture).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text=u"확인", style="Accent.TButton",
                   command=self._confirm).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text=u"취소", command=self.destroy).pack(side="right")

        self.reload(select=current)
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.tree.focus_set()

    # ------------------------------------------------------------------ 목록

    def reload(self, select=None):
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        self._thumbs = []

        entries = scan_images(self.macro_folder, self.macros_root)
        if not entries:
            item = self.tree.insert("", "end", text=u"   (이미지가 없습니다)")
            self._rows[item] = None
            return

        here_node = None
        other_node = None
        for kind, label, path in entries:
            thumb = imagecache.thumbnail(path, THUMB, THUMB)
            if thumb is not None:
                self._thumbs.append(thumb)
            if kind == "here":
                parent = ""
                text = u" %s" % label
            else:
                if other_node is None:
                    other_node = self.tree.insert(
                        "", "end", text=u"다른 매크로의 이미지 (고르면 복사됩니다)",
                        open=False)
                    self._rows[other_node] = None
                parent = other_node
                text = u" %s" % label
            item = self.tree.insert(parent, "end", text=text,
                                    image=thumb if thumb else "")
            self._rows[item] = (kind, label, path)
            if select and kind == "here" and label == select:
                self.tree.selection_set(item)
                self.tree.see(item)
        if here_node is None and not self.tree.selection():
            children = [i for i in self.tree.get_children("") if self._rows.get(i)]
            if children:
                self.tree.selection_set(children[0])

    def _selected(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self._rows.get(selection[0])

    def _on_select(self, _event=None):
        entry = self._selected()
        self.preview.delete("all")
        self._preview_ref = None
        if not entry:
            self.info.config(text=u"")
            return
        _kind, label, path = entry
        thumb = imagecache.thumbnail(path, 190, 140)
        size = imagecache.size_of(path)
        if thumb is not None:
            self._preview_ref = thumb
            self.preview.create_image(100, 75, image=thumb, anchor="center")
        try:
            byte_size = os.path.getsize(path)
        except OSError:
            byte_size = 0
        detail = label
        if size:
            detail += u"\n%d x %d · %d bytes" % (size[0], size[1], byte_size)
        self.info.config(text=detail)

    # ------------------------------------------------------------------ 동작

    def _copy_in(self, source):
        return copy_into_folder(self, self.macro_folder, source)

    def _import_file(self):
        path = filedialog.askopenfilename(
            title=u"이미지 파일 선택",
            initialdir=self.macro_folder or self.macros_root,
            filetypes=[("PNG / GIF", "*.png *.gif"), (u"모든 파일", "*.*")],
            parent=self)
        if not path:
            return
        if not _is_image(path):
            if not messagebox.askyesno(
                    u"이미지 형식",
                    u"OculiX 템플릿은 PNG를 씁니다.\n"
                    u"이 파일은 PNG/GIF가 아닌데 그래도 가져올까요?"):
                return
        name = self._copy_in(path)
        if name:
            self.reload(select=name)

    def _capture(self):
        self.destroy()
        if self.on_capture:
            self.on_capture()

    def _confirm(self):
        entry = self._selected()
        if not entry:
            return
        kind, label, path = entry
        if kind == "here":
            self.result = label
        else:
            name = self._copy_in(path)
            if not name:
                return
            self.result = name
        self.destroy()


def ask_image(parent, macro_folder, macros_root, current=None, on_capture=None):
    """고른 이미지의 파일 이름(매크로 폴더 기준). 취소하면 None."""
    dialog = ImagePickerDialog(parent, macro_folder, macros_root, current, on_capture)
    parent.wait_window(dialog)
    return dialog.result
