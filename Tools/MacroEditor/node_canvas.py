# -*- coding: utf-8 -*-
"""노드 그래프 캔버스 - UE 블루프린트식 편집 화면.

조작
    노드 몸통 드래그      위치 이동. 여러 개를 골라 뒀으면 전부 함께 움직인다
    빈 곳에서 드래그      사각형 범위 선택. 범위 안에 **완전히** 들어온 노드만 잡힌다
    Ctrl + 클릭          선택에 추가          (빈 곳에서 드래그하면 범위만큼 추가)
    Alt + 클릭           선택에서 제외        (빈 곳에서 드래그하면 범위만큼 제외)
    Ctrl + C / Ctrl + V  고른 노드 복사 / 붙여넣기 (다른 매크로에도 붙는다)
    Ctrl + D             고른 노드 복제 (여러 개면 노드 사이 연결까지 함께)
    출력 핀에서 드래그    다른 노드에 놓으면 연결 / 빈 곳에 놓으면 해제
    연결선 클릭 후 Delete 연결 삭제
    Delete               선택한 노드 전부 삭제
    빈 곳 우클릭          노드 추가 메뉴
    노드 우클릭           이 노드부터 실행 / 시작 노드 지정 / 사용 해제 / 복제 / 삭제
    Shift + F5           고른 노드 하나부터 실행 (저장된 시작 노드는 그대로 둔다)
    가운데 버튼 드래그    화면 이동
    휠                    확대 / 축소

선택은 두 가지로 나뉜다. `selected_nodes` 는 골라 둔 노드 전체이고,
`selected_node` 는 그중 속성 패널에 보여 줄 하나(활성 노드)다.
`selected_node` 에 값을 넣으면 선택이 그 하나로 초기화된다.

노드에는 핀 타입(Exec)과, 이미지 매개변수가 있으면 그 이미지의 썸네일이 함께 그려진다.

복사/붙여넣기는 클립보드에 JSON 글자로 오간다. 옮길 때 노드 id 를 새로 발급하고
이미지 파일까지 따라 옮기는 규칙은 `nodeclip.py` 에 있다.
"""

import copy
import os
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

import screenutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "Scripts", "Common")))

import graph_model
import imagecache
import nodeclip
import schema
import theme


NODE_W = 208
HEADER_H = 28
PIN_ROW_H = 22
DETAIL_H = 18
THUMB_MAX_W = 120
THUMB_MAX_H = 64
THUMB_PAD = 6
THUMB_GAP = 6          # 그림 여러 장을 나란히 놓을 때의 간격
THUMB_LABEL_H = 13     # '시작' / '끝' 같은 자리 이름을 적는 줄
COLLAPSE_H = 16        # 접기 아이콘 줄
PAD = 8
CORNER = 7

GROUP_COLORS = {
    u"기본":   ("#3d3d47", "#4a4a57"),
    u"화면":   ("#1c4b78", "#2563a0"),
    u"마우스": ("#1d5c3c", "#26804f"),
    u"키보드": ("#7a4614", "#a15f1c"),
    u"흐름":   ("#54307d", "#6f3fa5"),
}
DEFAULT_COLOR = ("#3d3d47", "#4a4a57")

BG = theme.BG_DARKEST
GRID = "#22222a"
GRID_MAJOR = "#2a2a34"
NODE_BODY = "#26262e"
NODE_BODY_OFF = "#202026"
WIRE = "#b9b9c6"
WIRE_SEL = theme.WARN
TEXT = theme.FG
SUBTEXT = theme.FG_DIM
FAINT = theme.FG_FAINT
SEL_OUTLINE = theme.WARN
ENTRY_OUTLINE = theme.OK
NODE_BORDER = "#14141a"

# 범위 선택을 시작한 것으로 볼 최소 드래그 거리(화면 픽셀).
# 이보다 짧으면 손떨림으로 보고 그냥 클릭으로 처리한다.
DRAG_SLOP = 3

# event.state 비트. <Control-Button-1> 같은 전용 바인딩이 우선이고,
# 이 값은 그 바인딩이 오지 않는 경우를 대비한 보조 판정이다.
STATE_CTRL = 0x0004
STATE_ALT = 0x20000

SELECT_REPLACE = "replace"
SELECT_ADD = "add"
SELECT_REMOVE = "remove"


def node_color(ntype):
    spec = schema.STEP_TYPES.get(ntype) or {}
    return GROUP_COLORS.get(spec.get("group"), DEFAULT_COLOR)


class NodeCanvas(ttk.Frame):

    def __init__(self, master, app):
        ttk.Frame.__init__(self, master)
        self.app = app
        self.graph = None
        self.base_dir = None

        self.zoom = 1.0
        self.origin = [40.0, 40.0]
        self.selected_nodes = set()      # 골라 둔 노드 전체
        self._selected_node = None       # 그중 활성 노드
        self._notified_node = None       # 속성 패널에 마지막으로 알린 노드
        self.selected_link = None

        self._drag_node = None
        self._drag_offset = (0, 0)
        self._drag_start = None          # 그룹 이동용 {id: (x, y)} 시작 좌표
        self._drag_from_world = None     # 누른 지점의 월드 좌표
        self._press_node = None
        self._press_collapse = False     # 뗄 때 선택을 하나로 줄일지
        self._moved = False
        self._marquee = None             # (시작x, 시작y, 현재x, 현재y) 화면 좌표
        self._marquee_mode = SELECT_REPLACE
        self._marquee_base = set()
        self._connect_from = None
        self._panning = False
        self._pan_from = None
        self._thumb_refs = []
        self._font_cache = {}

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        theme.style_canvas(self.canvas, BG)
        self.canvas.pack(fill="both", expand=True)

        c = self.canvas
        c.bind("<Button-1>", self._on_press)
        c.bind("<Control-Button-1>",
               lambda e: self._on_press(e, SELECT_ADD))
        c.bind("<Alt-Button-1>",
               lambda e: self._on_press(e, SELECT_REMOVE))
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Button-3>", self._on_right_click)
        c.bind("<Button-2>", self._on_pan_start)
        c.bind("<B2-Motion>", self._on_pan_move)
        c.bind("<ButtonRelease-2>", self._on_pan_end)
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<Delete>", lambda e: self.delete_selection())
        c.bind("<Double-Button-1>", self._on_double_click)
        # 캔버스 위젯에만 건다. 속성 패널의 입력칸에서는 평소대로 글자가 복사된다.
        # 대문자 쪽은 Shift 나 CapsLock 이 걸린 채로 눌렀을 때를 위한 것이다.
        c.bind("<Control-c>", self._on_copy)
        c.bind("<Control-C>", self._on_copy)
        c.bind("<Control-v>", self._on_paste)
        c.bind("<Control-V>", self._on_paste)
        c.bind("<Control-d>", self._on_duplicate)
        c.bind("<Control-D>", self._on_duplicate)
        c.configure(takefocus=True)

    # ------------------------------------------------------------------ 선택

    @property
    def selected_node(self):
        """속성 패널에 보여 줄 활성 노드. 선택이 비어 있으면 None."""
        return self._selected_node

    @selected_node.setter
    def selected_node(self, node_id):
        """하나만 고른 상태로 초기화한다.

        바깥 코드(편집기 상태 복원, 테스트)가 예전처럼 그냥 대입해도
        다중 선택과 어긋나지 않도록 여기서 함께 맞춰 준다.
        """
        self._selected_node = node_id
        self.selected_nodes = set([node_id]) if node_id else set()
        self._remember_active()

    def _remember_active(self):
        """활성 노드를 매크로에 적어 둔다. 선택을 비워도 지우지 않는다.

        `mark_dirty` 를 부르지 않는다 - 클릭만으로 수정됨이 되면 안 된다.
        파일에는 매크로를 떠날 때 들어간다 (`Macro.store_last_selected`).
        """
        if self._selected_node and self.graph is not None:
            self.graph.last_selected = self._selected_node

    def set_selection(self, node_ids, active=None, notify=True):
        """선택 전체를 갈아 끼운다. 활성 노드는 가능하면 유지한다."""
        ids = set(i for i in node_ids if self.graph and self.graph.node(i))
        if active not in ids:
            active = self._selected_node if self._selected_node in ids else None
        if active is None and ids:
            # 그래프에 실린 순서대로 첫 노드를 활성으로 삼는다 - 집합은 순서가 없다
            for node in self.graph.nodes:
                if node.get("id") in ids:
                    active = node["id"]
                    break
        self.selected_nodes = ids
        self._selected_node = active
        self._remember_active()
        if notify:
            self._notify_active()

    def _notify_active(self, force=False):
        """활성 노드가 바뀌었을 때만 속성 패널에 알린다.

        범위 선택 중에는 `set_selection(notify=False)` 로 조용히 바꾸므로,
        "지난번에 무엇을 알렸는지" 를 따로 들고 있어야 놓치지 않는다.
        """
        if force or self._selected_node != self._notified_node:
            self._notified_node = self._selected_node
            self.app.on_node_selected(self._selected_node)

    # ------------------------------------------------------------ 노드 치수

    def _resolve_image(self, name):
        """이미지 이름을 절대 경로로. 파일이 없으면 None."""
        if not name:
            return None
        if os.path.isabs(name):
            return name if os.path.isfile(name) else None
        if not self.base_dir:
            return None
        found = graph_model.locate_image(self.base_dir, name,
                                         screenutil.logical_screen_size())
        return found["path"] if found else None

    def node_image_path(self, node):
        """이 노드의 첫 번째 이미지 절대 경로. 없으면 None."""
        paths = self.node_image_paths(node)
        return paths[0][1] if paths else None

    def node_image_paths(self, node):
        """이 노드가 참조하는 이미지 전부. [(라벨, 절대경로), ...]

        드래그는 시작/끝 두 장, 분기는 조건 안의 이미지를 쓴다.
        어떤 자리에 어떤 그림이 들어갔는지 노드에서 바로 보이게 하려는 것이다.
        """
        found = []
        for label, name in schema.image_params(node):
            path = self._resolve_image(name)
            if path:
                found.append((label, path))
        return found

    @staticmethod
    def images_collapsed(node):
        """이미지 미리보기를 접어 뒀는가."""
        return bool((node.get("ui") or {}).get("imagesCollapsed"))

    def thumb_slots(self, node):
        """썸네일 배치. [(라벨, 경로, (w, h)), ...] 와 줄 크기를 함께 준다.

        크기는 **월드 좌표** 다. 확대율에 따라 달라지면 노드 높이가 확대할
        때마다 늘었다 줄었다 한다.
        여러 장이면 폭을 나눠 한 줄에 늘어놓고, 어느 자리 그림인지 라벨을 단다.
        """
        images = self.node_image_paths(node)
        if not images or self.images_collapsed(node):
            return [], 0, 0
        count = len(images)
        slot_w = THUMB_MAX_W if count == 1 else \
            max(28, (NODE_W - PAD * 2 - THUMB_GAP * (count - 1)) // count)
        slots = []
        for label, path in images:
            box = imagecache.fitted_box(path, slot_w, THUMB_MAX_H)
            if box is None:
                box = (slot_w, 24)
            slots.append((label, path, box))
        row_h = max(box[1] for _l, _p, box in slots)
        if count > 1:
            row_h += THUMB_LABEL_H          # 어느 자리 그림인지 적을 줄
        return slots, slot_w, row_h

    def node_thumb(self, node):
        """이 노드의 첫 이미지를 현재 확대율에 맞춘 썸네일. 없으면 None."""
        slots, _w, _h = self.thumb_slots(node)
        if not slots:
            return None
        _label, path, box = slots[0]
        return self.thumb_image(path, box)

    def thumb_image(self, path, box):
        """현재 확대율에 맞춘 썸네일 PhotoImage."""
        # 확대율마다 새 이미지를 만들면 캐시가 폭발한다. 8px 단위로 끊는다.
        want_w = max(8, int(box[0] * self.zoom) // 8 * 8)
        want_h = max(8, int(box[1] * self.zoom) // 8 * 8)
        return imagecache.scaled(path, want_w, want_h)

    def node_height(self, node):
        ntype = node.get("type")
        pins = graph_model.exec_pins(ntype)
        height = HEADER_H + max(1, len(pins)) * PIN_ROW_H
        if self._detail(node):
            height += DETAIL_H
        if self.node_image_paths(node):
            # 접기 아이콘 줄은 접었을 때도 남는다. 다시 펼 수 있어야 한다.
            height += COLLAPSE_H
            _slots, _w, row_h = self.thumb_slots(node)
            if row_h:
                height += row_h + THUMB_PAD * 2
        return height + PAD

    # ------------------------------------------------------------ 좌표 변환

    def to_screen(self, x, y):
        return x * self.zoom + self.origin[0], y * self.zoom + self.origin[1]

    def to_world(self, sx, sy):
        return (sx - self.origin[0]) / self.zoom, (sy - self.origin[1]) / self.zoom

    def _pos(self, node):
        ui = node.get("ui") or {}
        return float(ui.get("x", 0)), float(ui.get("y", 0))

    def _input_anchor(self, node):
        x, y = self._pos(node)
        return self.to_screen(x, y + HEADER_H / 2.0)

    def _output_anchor(self, node, pin):
        x, y = self._pos(node)
        pins = graph_model.exec_pins(node.get("type"))
        names = [p for p, _l in pins]
        index = names.index(pin) if pin in names else 0
        return self.to_screen(x + NODE_W, y + HEADER_H + PIN_ROW_H * (index + 0.5))

    # ---------------------------------------------------------------- 그리기

    def set_graph(self, graph, base_dir=None):
        self.graph = graph
        self.base_dir = base_dir
        self.selected_node = None
        self.selected_link = None
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        self._thumb_refs = []
        if self.graph is None:
            c.create_text(24, 24, anchor="nw", fill=SUBTEXT, font=theme.FONT,
                          text=u"그래프 매크로가 아닙니다.")
            return
        self._draw_grid()
        for link in self.graph.links:
            self._draw_wire(link)
        for node in self.graph.nodes:
            self._draw_node(node)
        if not self.graph.nodes:
            c.create_text(30, 30, anchor="nw", fill=SUBTEXT, font=theme.FONT,
                          text=u"빈 곳을 우클릭해서 노드를 추가하거나,\n"
                               u"왼쪽 라이브러리에서 매크로를 끌어다 놓으세요.")

    def _draw_grid(self):
        c = self.canvas
        w = c.winfo_width() or 800
        h = c.winfo_height() or 600
        step = 32 * self.zoom
        if step < 10:
            return
        ox = self.origin[0] % step
        oy = self.origin[1] % step
        major_every = 4
        i = int(-self.origin[0] // step)
        x = ox
        while x < w:
            c.create_line(x, 0, x, h,
                          fill=GRID_MAJOR if i % major_every == 0 else GRID)
            x += step
            i += 1
        j = int(-self.origin[1] // step)
        y = oy
        while y < h:
            c.create_line(0, y, w, y,
                          fill=GRID_MAJOR if j % major_every == 0 else GRID)
            y += step
            j += 1

    def _rounded(self, x1, y1, x2, y2, r, **kw):
        r = max(1, r)
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kw)

    def _pin_triangle(self, x, y, size, filled, colour, tags):
        """실행 핀은 블루프린트처럼 삼각형으로 그린다."""
        pts = [x - size, y - size, x - size, y + size, x + size, y]
        return self.canvas.create_polygon(
            pts, fill=colour if filled else "", outline=colour,
            width=max(1, int(self.zoom)), tags=tags)

    def _draw_node(self, node):
        c = self.canvas
        ntype = node.get("type")
        node_id = node.get("id")
        x, y = self.to_screen(*self._pos(node))
        w = NODE_W * self.zoom
        h = self.node_height(node) * self.zoom
        header = HEADER_H * self.zoom
        dark, light = node_color(ntype)
        disabled = node.get("enabled") is False
        tag = "node:%s" % node_id

        if node_id == self._selected_node:
            outline, width = SEL_OUTLINE, 3      # 활성 노드는 더 굵게
        elif node_id in self.selected_nodes:
            outline, width = SEL_OUTLINE, 2
        elif node_id == self.graph.entry:
            outline, width = ENTRY_OUTLINE, 2
        else:
            outline, width = NODE_BORDER, 1

        # 몸통 + 머리
        self._rounded(x, y, x + w, y + h, CORNER * self.zoom,
                      fill=NODE_BODY_OFF if disabled else NODE_BODY,
                      outline=outline, width=width, tags=(tag, "node"))
        self._rounded(x, y, x + w, y + header + CORNER * self.zoom,
                      CORNER * self.zoom,
                      fill="#3a3a44" if disabled else light,
                      outline="", tags=(tag, "node"))
        c.create_rectangle(x, y + header - 1, x + w, y + header + 1,
                           fill=dark, outline="", tags=(tag, "node"))

        fsize = max(6, int(9 * self.zoom))
        small = max(6, int(7 * self.zoom))

        # 오른쪽부터 채운다: [시작] [노드 id]. 남는 자리에 이름을 넣는다.
        # 로그와 검사 메시지가 이 id 로 노드를 가리키므로 화면에서 바로
        # 대조할 수 있어야 한다.
        right = x + w - 8 * self.zoom
        id_font = ("Consolas", small)
        c.create_text(right, y + header / 2, anchor="e",
                      text=node_id, fill=SUBTEXT, font=id_font,
                      tags=(tag, "node"))
        right -= self._text_width(node_id, id_font) + 6 * self.zoom

        if node_id == self.graph.entry:
            entry_font = ("맑은 고딕", small, "bold")
            c.create_text(right, y + header / 2, anchor="e",
                          text=u"시작", fill=ENTRY_OUTLINE, font=entry_font,
                          tags=(tag, "node"))
            right -= self._text_width(u"시작", entry_font) + 6 * self.zoom

        title = node.get("label") or schema.step_label(ntype)
        if disabled:
            title = u"⃠ " + title
        title_x = x + 10 * self.zoom
        title_font = ("맑은 고딕", fsize, "bold")
        c.create_text(title_x, y + header / 2, anchor="w",
                      text=self._fit(title, title_font, right - title_x),
                      fill=TEXT, font=title_font, tags=(tag, "node"))

        # 입력 핀 (타입 표시)
        ix, iy = self._input_anchor(node)
        in_type = graph_model.input_pin_type(ntype)
        in_colour = graph_model.pin_type_color(in_type)
        connected_in = len(self.graph.incoming(node_id)) > 0
        self._pin_triangle(ix, iy, 5 * self.zoom, connected_in, in_colour,
                           (tag, "node", "inpin:%s" % node_id))
        c.create_text(ix + 10 * self.zoom, iy, anchor="w",
                      text=graph_model.pin_type_label(in_type), fill=FAINT,
                      font=("Consolas", small), tags=(tag, "node"))

        # 출력 핀 (역할 이름 + 타입)
        for index, (pin, label) in enumerate(graph_model.exec_pins(ntype)):
            px, py = self._output_anchor(node, pin)
            ptype = graph_model.pin_type(ntype, pin)
            colour = graph_model.pin_type_color(ptype)
            connected = self.graph.target(node_id, pin) is not None
            pin_tag = (tag, "node", "outpin:%s:%s" % (node_id, pin))
            self._pin_triangle(px, py, 5 * self.zoom, connected, colour, pin_tag)
            c.create_text(px - 10 * self.zoom, py, anchor="e",
                          text=label, fill=SUBTEXT,
                          font=("맑은 고딕", small), tags=pin_tag)
            c.create_text(px - 10 * self.zoom - 30 * self.zoom, py, anchor="e",
                          text=graph_model.pin_type_label(ptype), fill=FAINT,
                          font=("Consolas", small), tags=pin_tag)

        cursor_y = y + header + max(1, len(graph_model.exec_pins(ntype))) * PIN_ROW_H * self.zoom

        # 이미지 매개변수 미리보기 (확대율을 따라간다)
        if self.node_image_paths(node):
            cursor_y = self._draw_thumbs(node, x, w, cursor_y, tag, small)

        detail = self._detail(node)
        if detail:
            c.create_text(x + 10 * self.zoom, cursor_y + 8 * self.zoom, anchor="w",
                          text=self._clip(detail, 26), fill=SUBTEXT,
                          font=("맑은 고딕", small), tags=(tag, "node"))

    def _draw_thumbs(self, node, x, w, cursor_y, tag, small):
        """접기 아이콘과 이미지 미리보기를 그린다. 다음 y 를 돌려준다.

        아이콘은 접었을 때도 남겨 둔다. 접고 나면 펼 방법이 없어지기 때문이다.
        """
        c = self.canvas
        node_id = node.get("id")
        collapsed = self.images_collapsed(node)
        slots, _slot_w, row_h = self.thumb_slots(node)

        # 접기 아이콘. 글자만 두면 누르기 어려워서 투명한 판을 깔아 준다.
        icon_y = cursor_y + COLLAPSE_H * self.zoom / 2
        icon_x = x + 10 * self.zoom
        hit = ("collapse:%s" % node_id, tag, "node")
        c.create_rectangle(x + 2 * self.zoom, cursor_y,
                           x + w - 2 * self.zoom, cursor_y + COLLAPSE_H * self.zoom,
                           fill="", outline="", tags=hit)
        c.create_text(icon_x, icon_y, anchor="w",
                      text=(u"▶" if collapsed else u"▼"), fill=SUBTEXT,
                      font=("맑은 고딕", small), tags=hit)
        count = len(self.node_image_paths(node))
        c.create_text(icon_x + 14 * self.zoom, icon_y, anchor="w",
                      text=(u"이미지 %d장" % count) if collapsed else u"이미지",
                      fill=FAINT, font=("맑은 고딕", small), tags=hit)
        cursor_y += COLLAPSE_H * self.zoom
        if collapsed or not slots:
            return cursor_y

        label_h = THUMB_LABEL_H * self.zoom if len(slots) > 1 else 0
        total_w = sum(box[0] for _l, _p, box in slots) * self.zoom \
            + THUMB_GAP * self.zoom * (len(slots) - 1)
        left = x + (w - total_w) / 2
        top = cursor_y + THUMB_PAD * self.zoom
        pic_h = (row_h * self.zoom) - label_h

        for label, path, box in slots:
            slot_w = box[0] * self.zoom
            slot_h = box[1] * self.zoom
            cx = left + slot_w / 2
            # 높이가 제각각이면 아래를 맞춰 둔다. 라벨 줄과 붙어 보기 좋다.
            ty = top + (pic_h - slot_h)
            c.create_rectangle(cx - slot_w / 2 - 2, ty - 2,
                               cx + slot_w / 2 + 2, ty + slot_h + 2,
                               fill="#15151a", outline="#4a4a57",
                               tags=(tag, "node"))
            thumb = self.thumb_image(path, box)
            if thumb is not None:
                self._thumb_refs.append(thumb)
                # 정수 배율 근사라 요청 크기와 살짝 다를 수 있다. 가운데 맞춘다.
                c.create_image(cx, ty + slot_h / 2, anchor="center",
                               image=thumb, tags=(tag, "node"))
            if label_h:
                c.create_text(cx, top + pic_h + label_h / 2, anchor="center",
                              text=label, fill=SUBTEXT,
                              font=("맑은 고딕", small), tags=(tag, "node"))
            left += slot_w + THUMB_GAP * self.zoom

        return top + row_h * self.zoom + THUMB_PAD * self.zoom

    def _draw_wire(self, link, temp_to=None):
        src = self.graph.node(link.get("from"))
        if src is None:
            return
        x1, y1 = self._output_anchor(src, link.get("pin"))
        if temp_to:
            x2, y2 = temp_to
        else:
            dst = self.graph.node(link.get("to"))
            if dst is None:
                return
            x2, y2 = self._input_anchor(dst)
        selected = (self.selected_link is not None and
                    self.selected_link[0] == link.get("from") and
                    self.selected_link[1] == link.get("pin"))
        colour = WIRE_SEL if selected else WIRE
        stretch = max(40.0, abs(x2 - x1) * 0.5) * self.zoom
        points = [x1, y1, x1 + stretch, y1, x2 - stretch, y2, x2, y2]
        tag = "wire:%s:%s" % (link.get("from"), link.get("pin"))
        self.canvas.create_line(*points, smooth=True, splinesteps=24,
                                width=max(2, int(2.5 * self.zoom)),
                                fill=colour, arrow="last",
                                arrowshape=(10, 12, 4), tags=(tag, "wire"))

    @staticmethod
    def _clip(text, limit):
        text = text or u""
        return text if len(text) <= limit else text[:limit - 1] + u"…"

    def _font(self, spec):
        """측정용 Font 객체. 노드마다 새로 만들면 다시 그리기가 느려진다."""
        cached = self._font_cache.get(spec)
        if cached is None:
            cached = tkfont.Font(root=self.canvas, font=spec)
            self._font_cache[spec] = cached
        return cached

    def _text_width(self, text, spec):
        if not text:
            return 0
        try:
            return self._font(spec).measure(text)
        except tk.TclError:
            return len(text) * 7          # 폰트를 못 잡아도 그리기는 계속한다

    def _fit(self, text, spec, max_width):
        """`max_width` 픽셀 안에 들어가게 뒤를 잘라낸다.

        글자 수로 자르면 안 된다. 한글·영문·숫자의 폭이 제각각이라 같은
        22자라도 어떤 이름은 남고 어떤 이름은 오른쪽 id 위로 넘어간다.
        """
        text = text or u""
        if max_width <= 0:
            return u""
        if self._text_width(text, spec) <= max_width:
            return text
        clipped = text
        while clipped and self._text_width(clipped + u"…", spec) > max_width:
            clipped = clipped[:-1]
        return (clipped + u"…") if clipped else u""

    @staticmethod
    def _detail(node):
        summary = schema.summarize(node)
        if u"—" in summary:
            return summary.split(u"—", 1)[1].strip()
        return u""

    # ---------------------------------------------------------------- 히트

    def _tags_at(self, event):
        item = self.canvas.find_withtag("current")
        if not item:
            return []
        return self.canvas.gettags(item[0])

    @staticmethod
    def _find_tag(tags, prefix):
        for t in tags:
            if t.startswith(prefix):
                return t
        return None

    def node_rect(self, node):
        """노드가 차지하는 화면 사각형 (x0, y0, x1, y1)."""
        x, y = self.to_screen(*self._pos(node))
        return x, y, x + NODE_W * self.zoom, y + self.node_height(node) * self.zoom

    def nodes_in_rect(self, rect):
        """사각형 안에 **완전히** 들어온 노드 id 목록.

        일부만 걸친 노드는 뺀다. 블루프린트처럼 범위를 넉넉히 그어야
        잡히므로, 빽빽한 그래프에서 옆 노드가 딸려오지 않는다.
        """
        x0, y0, x1, y1 = rect
        found = []
        for node in (self.graph.nodes if self.graph else []):
            nx0, ny0, nx1, ny1 = self.node_rect(node)
            if nx0 >= x0 and ny0 >= y0 and nx1 <= x1 and ny1 <= y1:
                found.append(node["id"])
        return found

    def _marquee_rect(self):
        """드래그 방향과 무관하게 정규화한 사각형."""
        sx, sy, cx, cy = self._marquee
        return min(sx, cx), min(sy, cy), max(sx, cx), max(sy, cy)

    def _draw_marquee(self):
        x0, y0, x1, y1 = self._marquee_rect()
        self.canvas.create_rectangle(
            x0, y0, x1, y1, outline=SEL_OUTLINE, width=1, dash=(4, 3),
            fill=SEL_OUTLINE, stipple="gray12")

    def _node_at(self, event):
        items = self.canvas.find_overlapping(event.x - 1, event.y - 1,
                                             event.x + 1, event.y + 1)
        for item in reversed(items):
            for t in self.canvas.gettags(item):
                if t.startswith("node:"):
                    return t.split(":", 1)[1]
        return None

    # ---------------------------------------------------------------- 이벤트

    @staticmethod
    def _mode_from_state(event, mode):
        """전용 바인딩이 오지 않은 경우를 대비해 수정 키를 한 번 더 본다."""
        if mode != SELECT_REPLACE:
            return mode
        try:
            state = int(event.state)
        except (AttributeError, TypeError, ValueError):
            return mode
        if state & STATE_ALT:
            return SELECT_REMOVE
        if state & STATE_CTRL:
            return SELECT_ADD
        return mode

    def _on_press(self, event, mode=SELECT_REPLACE):
        self.canvas.focus_set()
        if self.graph is None:
            return
        mode = self._mode_from_state(event, mode)
        self._press_node = None
        self._press_collapse = False
        self._moved = False
        self._marquee = None
        tags = self._tags_at(event)

        # 접기 아이콘이 노드 몸통보다 먼저다. 몸통으로 넘어가면 드래그가 시작된다.
        collapse = self._find_tag(tags, "collapse:")
        if collapse:
            self._toggle_images(collapse.split(":", 1)[1])
            return

        outpin = self._find_tag(tags, "outpin:")
        if outpin:
            _prefix, node_id, pin = outpin.split(":", 2)
            self._connect_from = (node_id, pin)
            return

        wire = self._find_tag(tags, "wire:")
        if wire:
            _prefix, from_id, pin = wire.split(":", 2)
            self.selected_link = (from_id, pin)
            self.selected_node = None
            self.redraw()
            return

        node_tag = self._find_tag(tags, "node:")
        if node_tag:
            self._press_on_node(event, node_tag.split(":", 1)[1], mode)
            return

        # 빈 곳 - 범위 선택을 시작한다. 끌지 않고 떼면 그냥 클릭으로 본다.
        self.selected_link = None
        self._marquee = (event.x, event.y, event.x, event.y)
        self._marquee_mode = mode
        self._marquee_base = set(self.selected_nodes)

    def _press_on_node(self, event, node_id, mode):
        node = self.graph.node(node_id)
        if node is None:
            return
        self.selected_link = None
        self._marquee = None
        self._press_collapse = False
        self._moved = False

        if mode == SELECT_REMOVE:
            if node_id in self.selected_nodes:
                remaining = set(self.selected_nodes)
                remaining.discard(node_id)
                self.set_selection(remaining)
            self.redraw()
            return                       # 빼낸 노드를 그대로 끌고 다니지 않는다

        if mode == SELECT_ADD:
            self.set_selection(set(self.selected_nodes) | {node_id}, active=node_id)
        elif node_id in self.selected_nodes:
            # 이미 골라 둔 노드다. 여기서 선택을 하나로 줄이면 그룹 이동이
            # 불가능해지므로, 끌지 않고 뗐을 때만 줄인다.
            self._press_collapse = len(self.selected_nodes) > 1
            self.set_selection(self.selected_nodes, active=node_id)
        else:
            self.set_selection([node_id], active=node_id)

        self._press_node = node_id
        self._begin_move(event, node_id)
        self.redraw()
        self._notify_active(force=True)   # 노드를 누르면 늘 속성 패널을 갱신한다

    def _begin_move(self, event, node_id):
        """선택한 노드 전부의 시작 좌표를 적어 둔다.

        매 프레임 상대 이동을 누적하면 `move_node` 의 int 반올림 때문에
        노드끼리 조금씩 어긋난다. 그래서 시작 좌표 + 총 변위로 계산한다.
        """
        self._drag_node = node_id
        self._drag_from_world = self.to_world(event.x, event.y)
        self._drag_start = {}
        for moving in self.selected_nodes:
            node = self.graph.node(moving)
            if node is not None:
                self._drag_start[moving] = self._pos(node)
        wx, wy = self._drag_from_world
        nx, ny = self._pos(self.graph.node(node_id))
        self._drag_offset = (wx - nx, wy - ny)

    def _on_drag(self, event):
        if self._connect_from:
            self.redraw()
            link = {"from": self._connect_from[0], "pin": self._connect_from[1]}
            self._draw_wire(link, temp_to=(event.x, event.y))
            return

        if self._marquee:
            sx, sy = self._marquee[0], self._marquee[1]
            self._marquee = (sx, sy, event.x, event.y)
            if not self._moved and (abs(event.x - sx) > DRAG_SLOP
                                    or abs(event.y - sy) > DRAG_SLOP):
                self._moved = True
            if self._moved:
                # 고르는 중에는 속성 패널을 건드리지 않는다(notify=False).
                # 매번 폼을 다시 만들면 드래그가 눈에 띄게 끊긴다.
                self.set_selection(self._selection_for_marquee(), notify=False)
            self.redraw()
            self._draw_marquee()
            return

        if self._drag_node:
            wx, wy = self.to_world(event.x, event.y)
            dx = wx - self._drag_from_world[0]
            dy = wy - self._drag_from_world[1]
            if not self._moved and (abs(dx * self.zoom) > DRAG_SLOP
                                    or abs(dy * self.zoom) > DRAG_SLOP):
                self._moved = True
            if not self._drag_start:     # 선택이 비면 누른 노드만 옮긴다
                self.graph.move_node(self._drag_node,
                                     wx - self._drag_offset[0],
                                     wy - self._drag_offset[1])
            else:
                for moving, (sx, sy) in self._drag_start.items():
                    self.graph.move_node(moving, sx + dx, sy + dy)
            self.app.mark_dirty()
            self.redraw()

    def _selection_for_marquee(self):
        inside = set(self.nodes_in_rect(self._marquee_rect()))
        if self._marquee_mode == SELECT_ADD:
            return self._marquee_base | inside
        if self._marquee_mode == SELECT_REMOVE:
            return self._marquee_base - inside
        return inside

    def _on_release(self, event):
        if self._connect_from:
            target = self._node_at(event)
            from_id, pin = self._connect_from
            self._connect_from = None
            if target and target != from_id:
                try:
                    self.graph.connect(from_id, pin, target)
                    self.app.mark_dirty()
                    self.app.log_line(u"연결: %s.%s -> %s" % (from_id, pin, target))
                except graph_model.GraphError as exc:
                    self.app.log_line(u"연결 실패: %s" % exc, "err")
            elif target is None:
                if self.graph.disconnect(from_id, pin):
                    self.app.mark_dirty()
                    self.app.log_line(u"연결 해제: %s.%s" % (from_id, pin))
            self.redraw()

        elif self._marquee:
            # 끌지 않고 뗐으면 빈 곳 클릭이다 - 예전처럼 선택을 푼다.
            picked = self._selection_for_marquee() if self._moved \
                else (self._marquee_base if self._marquee_mode != SELECT_REPLACE
                      else set())
            self._marquee = None
            self.set_selection(picked)
            self.redraw()

        elif self._press_collapse and not self._moved:
            # 여러 개를 고른 상태에서 그중 하나를 그냥 클릭했다 -> 그 하나만 남긴다
            self.set_selection([self._press_node], active=self._press_node)
            self.redraw()

        self._drag_node = None
        self._drag_start = None
        self._press_node = None
        self._press_collapse = False
        self._moved = False

    def _on_double_click(self, event):
        node_id = self._node_at(event)
        if node_id:
            node = self.graph.node(node_id)
            if node is not None and node.get("type") == "call":
                self.app.open_macro_ref(node.get("macro"))
                return
            self.app.focus_properties()

    def _on_right_click(self, event):
        if self.graph is None:
            return
        node_id = self._node_at(event)
        if node_id and node_id not in self.selected_nodes:
            # 고르지 않은 노드를 우클릭하면 그 노드로 선택을 옮긴다
            self.set_selection([node_id], active=node_id)
            self.redraw()
        menu = tk.Menu(self, tearoff=0)
        theme.style_menu(menu)
        wx, wy = self.to_world(event.x, event.y)   # 붙여넣기를 놓을 자리
        if node_id:
            node = self.graph.node(node_id)
            # 노드를 하나만 골랐을 때만. 여러 개면 어디서 시작할지 모호하다.
            if len(self.selected_nodes) == 1:
                menu.add_command(label=u"이 노드부터 실행 (Shift+F5)",
                                 command=self.app.run_from_selected_node)
                menu.add_separator()
            menu.add_command(label=u"시작 노드로 지정",
                             command=lambda: self._set_entry(node_id))
            state = u"사용 안 함으로" if node.get("enabled") is not False else u"다시 사용"
            menu.add_command(label=state, command=lambda: self._toggle(node_id))
            count = len(self.selected_nodes)
            menu.add_command(
                label=(u"선택한 노드 %d개 복제 (Ctrl+D)" % count) if count > 1
                      else u"복제 (Ctrl+D)",
                command=self.duplicate_selection)
            menu.add_separator()
            menu.add_command(
                label=(u"선택한 노드 %d개 복사 (Ctrl+C)" % count) if count > 1
                      else u"복사 (Ctrl+C)",
                command=self.copy_selection)
            menu.add_command(label=u"붙여넣기 (Ctrl+V)",
                             command=lambda x=wx, y=wy: self.paste_clipboard((x, y)))
            if node.get("type") == "call":
                menu.add_separator()
                menu.add_command(label=u"호출 대상 열기",
                                 command=lambda: self.app.open_macro_ref(node.get("macro")))
            menu.add_separator()
            if count > 1 and node_id in self.selected_nodes:
                picked = list(self.selected_nodes)
                menu.add_command(label=u"선택한 노드 %d개 삭제" % count,
                                 command=lambda: self._delete_nodes(picked))
            else:
                menu.add_command(label=u"삭제",
                                 command=lambda: self._delete_node(node_id))
        else:
            add = tk.Menu(menu, tearoff=0)
            theme.style_menu(add)
            for group, entries in schema.grouped_types().items():
                sub = tk.Menu(add, tearoff=0)
                theme.style_menu(sub)
                for stype, label in entries:
                    sub.add_command(
                        label=label,
                        command=lambda t=stype, x=wx, y=wy: self.add_node(t, x, y))
                add.add_cascade(label=group, menu=sub)
            menu.add_cascade(label=u"노드 추가", menu=add)
            menu.add_command(label=u"붙여넣기 (Ctrl+V)",
                             command=lambda x=wx, y=wy: self.paste_clipboard((x, y)))
            menu.add_separator()
            menu.add_command(label=u"보기 초기화", command=self.reset_view)
            menu.add_command(label=u"자동 정렬", command=self.auto_layout)
        menu.tk_popup(event.x_root, event.y_root)

    def _on_pan_start(self, event):
        self._panning = True
        self._pan_from = (event.x, event.y, self.origin[0], self.origin[1])

    def _on_pan_move(self, event):
        if not self._panning:
            return
        sx, sy, ox, oy = self._pan_from
        self.origin[0] = ox + (event.x - sx)
        self.origin[1] = oy + (event.y - sy)
        self.redraw()

    def _on_pan_end(self, _event):
        self._panning = False

    def _on_wheel(self, event):
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        new_zoom = max(0.35, min(2.5, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
        wx, wy = self.to_world(event.x, event.y)
        self.zoom = new_zoom
        self.origin[0] = event.x - wx * self.zoom
        self.origin[1] = event.y - wy * self.zoom
        self.redraw()

    # ---------------------------------------------------------------- 동작

    def add_node(self, stype, x=None, y=None):
        if self.graph is None:
            return None
        if x is None:
            x, y = self.to_world(80, 80)
        node = dict(schema.new_step(stype))
        for key in ("then", "else", "steps"):
            node.pop(key, None)
        self.graph.add_node(node, int(x), int(y))
        self.selected_node = node["id"]
        self.app.mark_dirty()
        self.redraw()
        self.app.on_node_selected(node["id"])
        return node

    def drop_call_node(self, ref, x_root, y_root):
        """라이브러리에서 끌어다 놓은 매크로를 호출 노드로 만든다."""
        if self.graph is None:
            return None
        sx = x_root - self.canvas.winfo_rootx()
        sy = y_root - self.canvas.winfo_rooty()
        wx, wy = self.to_world(sx, sy)
        node = self.add_node("call", wx - NODE_W / 2, wy - HEADER_H / 2)
        if node is None:
            return None
        node["macro"] = ref
        node["label"] = ref.split("/")[-1]
        self.redraw()
        self.app.on_node_selected(node["id"])
        return node

    def delete_selection(self):
        if self.selected_link:
            from_id, pin = self.selected_link
            self.graph.disconnect(from_id, pin)
            self.selected_link = None
            self.app.mark_dirty()
            self.redraw()
            return
        self._delete_nodes(self.selected_nodes)

    def _delete_node(self, node_id):
        self._delete_nodes([node_id])

    def _delete_nodes(self, node_ids):
        """고른 노드를 한꺼번에 지운다. 다시 그리는 것은 마지막에 한 번만."""
        ids = [i for i in node_ids if self.graph.node(i) is not None]
        if not ids:
            return
        for node_id in ids:
            self.graph.remove_node(node_id)
            self.selected_nodes.discard(node_id)
        if self._selected_node in ids:
            self._selected_node = None
        self.set_selection(self.selected_nodes)
        self.app.mark_dirty()
        self.redraw()

    def _set_entry(self, node_id):
        self.graph.entry = node_id
        self.app.mark_dirty()
        self.redraw()

    def _toggle_images(self, node_id):
        """이미지 미리보기를 접었다 폈다 한다.

        상태는 노드의 ui 에 저장해서 매크로를 다시 열어도 유지된다.
        보기 설정이라 실행 결과에는 영향이 없다.
        """
        node = self.graph.node(node_id) if self.graph else None
        if node is None:
            return
        ui = node.setdefault("ui", {})
        if ui.get("imagesCollapsed"):
            ui.pop("imagesCollapsed", None)   # 기본값이면 키를 남기지 않는다
        else:
            ui["imagesCollapsed"] = True
        self.app.mark_dirty()
        self.redraw()

    def _toggle(self, node_id):
        node = self.graph.node(node_id)
        if node.get("enabled") is False:
            node.pop("enabled", None)
        else:
            node["enabled"] = False
        self.app.mark_dirty()
        self.redraw()

    def _duplicate(self, node_id):
        node = self.graph.node(node_id)
        clone = copy.deepcopy(node)
        clone.pop("id", None)
        ui = clone.setdefault("ui", {})
        ui["x"] = ui.get("x", 0) + 30
        ui["y"] = ui.get("y", 0) + 30
        self.graph.add_node(clone)
        self.selected_node = clone["id"]
        self.app.mark_dirty()
        self.redraw()
        # 선택이 복제본으로 옮겨 갔으니 속성 패널도 그쪽을 보게 한다.
        # 알리지 않으면 원본을 편집 중인 것처럼 보인다.
        self._notify_active(force=True)
        return [clone["id"]]

    # ------------------------------------------------- 복사 / 붙여넣기

    def _on_copy(self, _event=None):
        self.copy_selection()
        return "break"

    def _on_paste(self, _event=None):
        self.paste_clipboard(at=self._pointer_world())
        return "break"

    def _on_duplicate(self, _event=None):
        self.duplicate_selection()
        return "break"

    def duplicate_selection(self):
        """고른 노드를 그 자리 옆에 복제한다. 새로 생긴 노드 id 목록.

        하나만 골랐으면 예전 '복제' 와 같다. 여럿이면 노드 사이의 연결까지
        살려야 하는데 그 규칙은 이미 nodeclip 에 있으므로 복사/붙여넣기
        경로를 그대로 쓴다. 그 대가로 클립보드 내용은 덮어쓰인다.
        """
        if self.graph is None:
            return []
        if not self.selected_nodes:
            self.app.log_line(u"복제할 노드를 먼저 고르세요", "err")
            return []
        if len(self.selected_nodes) == 1:
            return self._duplicate(next(iter(self.selected_nodes)))
        if not self.copy_selection():
            return []
        return self.paste_clipboard()

    def _pointer_world(self):
        """마우스가 캔버스 위에 있으면 그 자리의 월드 좌표. 밖이면 None."""
        c = self.canvas
        try:
            sx = c.winfo_pointerx() - c.winfo_rootx()
            sy = c.winfo_pointery() - c.winfo_rooty()
        except tk.TclError:
            return None
        if 0 <= sx < c.winfo_width() and 0 <= sy < c.winfo_height():
            return self.to_world(sx, sy)
        return None

    def copy_selection(self):
        """고른 노드를 클립보드에 담는다. 담은 개수를 돌려준다.

        노드 사이의 연결도 함께 담는다. 선택 밖으로 나가던 연결은 뺀다 -
        붙여넣는 곳에 그 상대가 없기 때문이다.
        """
        if self.graph is None or not self.selected_nodes:
            self.app.log_line(u"복사할 노드를 먼저 고르세요", "err")
            return 0
        macro = getattr(self.app, "macro", None)
        payload = nodeclip.pack(
            self.graph, self.selected_nodes, source_dir=self.base_dir,
            source_name=(macro.data.get("name") if macro else u"") or u"")
        if payload is None:
            return 0
        try:
            self.canvas.clipboard_clear()
            self.canvas.clipboard_append(nodeclip.dumps(payload))
        except tk.TclError as exc:
            self.app.log_line(u"클립보드에 담지 못했습니다: %s" % exc, "err")
            return 0
        self.app.log_line(u"노드 %d개 복사 (연결 %d개)"
                          % (len(payload["nodes"]), len(payload["links"])), "ok")
        return len(payload["nodes"])

    def paste_clipboard(self, at=None):
        """클립보드의 노드 꾸러미를 심는다. 새로 생긴 노드 id 목록.

        `at` 은 놓을 월드 좌표(꾸러미의 왼쪽 위 모서리 기준). 없으면 원래
        자리에서 조금 밀어 놓는다.
        """
        if self.graph is None:
            return []
        try:
            text = self.canvas.clipboard_get()
        except tk.TclError:
            text = None                  # 클립보드가 비었거나 글자가 아니다
        payload = nodeclip.loads(text)
        if payload is None:
            self.app.log_line(u"클립보드에 붙여넣을 노드가 없습니다", "err")
            return []

        image_map, notes, copied = nodeclip.import_images(payload,
                                                          self.base_dir)
        for tag, line in notes:
            self.app.log_line(line, tag)
        if copied:
            # 폴더에 파일이 늘었다. 프로젝트 패널이 낡은 목록을 들고 있으면
            # 방금 가져온 그림이 없는 것처럼 보인다.
            refresh = getattr(self.app, "refresh_project", None)
            if refresh:
                refresh()

        new_ids = nodeclip.paste(self.graph, payload, at=at, image_map=image_map)
        if not new_ids:
            return []
        self.app.mark_dirty()
        self.set_selection(new_ids, active=new_ids[0])
        self.redraw()
        self._notify_active(force=True)
        source = payload.get("sourceName")
        self.app.log_line(u"노드 %d개 붙여넣기%s"
                          % (len(new_ids),
                             (u" (원본: %s)" % source) if source else u""), "ok")
        self._warn_pasted_calls(new_ids)
        return new_ids

    def _warn_pasted_calls(self, node_ids):
        """붙여넣은 호출 노드가 여기서도 유효한지 기존 검사로 확인한다.

        `./이름` 하위 매크로 참조는 그 가족 안에서만 뜻이 있어서, 다른
        매크로에 붙이면 가리킬 곳이 없어진다. 참조를 몰래 고치는 대신
        어디가 깨졌는지 바로 알린다.
        """
        check = getattr(self.app, "check_call_targets", None)
        if check is None:
            return
        ids = set(node_ids)
        if not any((self.graph.node(i) or {}).get("type") == "call"
                   for i in ids):
            return
        for line in check(only=ids):
            self.app.log_line(u"주의: %s" % line, "err")

    def reset_view(self):
        self.zoom = 1.0
        self.origin = [40.0, 40.0]
        self.redraw()

    def center_on_node(self, node_id):
        """노드 하나를 화면 한가운데로 끌어온다. 배율과 선택은 건드리지 않는다.

        노드를 옮기는 것이 아니라 보는 위치(origin)만 옮긴다.
        아래쪽 `focus_node` 와 헷갈리지 않게 이름을 나눠 뒀다 -
        그쪽은 선택만 바꾸고 화면은 그대로 둔다.
        """
        node = self.graph.node(node_id) if self.graph else None
        if node is None:
            return False
        # 방금 만들어진 패널은 아직 크기가 없다. 그리기 전에 실제 크기를 받아 온다.
        self.canvas.update_idletasks()
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            w, h = 800, 600
        x, y = self._pos(node)
        cx = x + NODE_W / 2.0
        cy = y + self.node_height(node) / 2.0
        self.origin[0] = w / 2.0 - cx * self.zoom
        self.origin[1] = h / 2.0 - cy * self.zoom
        self.redraw()
        return True

    def focus_entry(self):
        """시작 노드를 화면 한가운데로. 시작 노드가 없으면 False."""
        if self.graph is None or not self.graph.entry:
            return False
        return self.center_on_node(self.graph.entry)

    def focus_opened(self):
        """막 연 매크로의 보는 위치를 잡는다. 옮기지 못했으면 False.

        마지막으로 선택한 노드, 그게 없으면(기록이 없거나 지워졌으면) 시작 노드로
        간다. 노드가 하나도 없으면 둘 다 없으므로 화면은 그대로다.
        """
        if self.graph is None:
            return False
        target = self.graph.last_selected
        if self.graph.node(target) is None:
            target = self.graph.entry
        return self.center_on_node(target)

    def auto_layout(self):
        """시작 노드부터 폭 우선으로 훑어 열/행에 배치한다."""
        if self.graph is None or not self.graph.entry:
            return
        depth = {}
        order = []
        queue = [(self.graph.entry, 0)]
        seen = set()
        while queue:
            node_id, d = queue.pop(0)
            if node_id in seen or self.graph.node(node_id) is None:
                continue
            seen.add(node_id)
            depth[node_id] = d
            order.append(node_id)
            for link in self.graph.outgoing(node_id):
                queue.append((link.get("to"), d + 1))

        rows = {}
        for node_id in order:
            d = depth[node_id]
            row = rows.get(d, 0)
            rows[d] = row + 1
            self.graph.move_node(node_id, 60 + d * 280, 60 + row * 190)

        loose = 0
        for node in self.graph.nodes:
            if node.get("id") not in seen:
                self.graph.move_node(node["id"], 60, 60 + (len(rows) + loose) * 190)
                loose += 1

        self.app.mark_dirty()
        self.reset_view()

    def focus_node(self, node_id):
        node = self.graph.node(node_id) if self.graph else None
        if not node:
            return
        self.selected_node = node_id
        self.redraw()
