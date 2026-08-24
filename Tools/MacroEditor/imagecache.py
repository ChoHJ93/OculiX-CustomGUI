# -*- coding: utf-8 -*-
"""PNG 썸네일 캐시.

tkinter 8.6의 PhotoImage가 PNG를 기본 지원하므로 Pillow 같은 외부 라이브러리가
필요 없다. 다만 크기 조절이 정수 배율뿐이다.

    subsample(n)  1/n 로 축소
    zoom(n)       n 배로 확대

이 둘을 조합하면 `zoom(a).subsample(b)` = a/b 배가 되어 임의 배율을 근사할 수
있다. 캔버스 확대/축소에 썸네일이 따라가는 것은 이 방식으로 처리한다.

PhotoImage는 참조를 놓으면 가비지 컬렉션되어 화면에서 사라지므로 캐시로 붙든다.
"""

import os
import tkinter as tk

# 원본 이미지 (파일당 하나)
_originals = {}
# 크기 조절 결과
_scaled = {}
_MAX_SCALED = 400

# 근사에 쓸 배율 후보. 확대는 6배, 축소는 1/12 까지.
_ZOOM_RANGE = range(1, 7)
_SUB_RANGE = range(1, 13)


def _stamp(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _original(path):
    """원본 PhotoImage. 파일이 바뀌면 다시 읽는다."""
    key = (os.path.normcase(os.path.abspath(path)), _stamp(path))
    cached = _originals.get(key)
    if cached is not None:
        return cached
    if not os.path.isfile(path):
        return None
    try:
        image = tk.PhotoImage(file=path)
    except Exception:
        return None
    if image.width() <= 0 or image.height() <= 0:
        return None
    # 같은 파일의 옛 항목은 버린다
    for old in [k for k in _originals if k[0] == key[0]]:
        _originals.pop(old, None)
    _originals[key] = image
    return image


def size_of(path):
    """원본 크기 (w, h). 실패하면 None."""
    image = _original(path)
    if image is None:
        return None
    return image.width(), image.height()


def _best_ratio(width, height, max_w, max_h):
    """max_w x max_h 안에 들어가면서 가장 큰 a/b 배율을 고른다."""
    best = None
    best_area = 0
    for a in _ZOOM_RANGE:
        for b in _SUB_RANGE:
            new_w = width * a // b
            new_h = height * a // b
            if new_w < 1 or new_h < 1:
                continue
            if new_w > max_w or new_h > max_h:
                continue
            area = new_w * new_h
            if area > best_area:
                best = (a, b)
                best_area = area
    if best is not None:
        return best

    # 후보 범위 안에 맞는 조합이 없다 (요청이 아주 작은 경우).
    # 그냥 원본을 돌려주면 크기 제한을 넘으므로 필요한 만큼 더 줄인다.
    need_w = -(-width // max(1, max_w))     # 올림 나눗셈
    need_h = -(-height // max(1, max_h))
    return 1, max(1, need_w, need_h)


def scaled(path, max_w, max_h):
    """max_w x max_h 안에 들어가도록 크기를 맞춘 PhotoImage. 실패하면 None.

    정수 배율 조합으로 근사하므로 요청 크기와 정확히 같지는 않다.
    """
    max_w = max(1, int(max_w))
    max_h = max(1, int(max_h))
    base = _original(path)
    if base is None:
        return None

    key = (os.path.normcase(os.path.abspath(path)), _stamp(path), max_w, max_h)
    cached = _scaled.get(key)
    if cached is not None:
        return cached

    width, height = base.width(), base.height()
    a, b = _best_ratio(width, height, max_w, max_h)

    image = base
    try:
        if a > 1:
            image = image.zoom(a, a)
        if b > 1:
            image = image.subsample(b, b)
    except Exception:
        return None

    if len(_scaled) > _MAX_SCALED:
        _scaled.clear()
    _scaled[key] = image
    return image


def thumbnail(path, max_w=96, max_h=64):
    """예전 이름. scaled() 와 같다."""
    if not path or not os.path.isfile(path):
        return None
    return scaled(path, max_w, max_h)


def fitted_box(path, box_w, box_h):
    """원본 비율을 유지하면서 box 안에 들어가는 크기 (w, h). 실패하면 None.

    캔버스 확대율과 무관한 '월드 좌표' 크기를 잡을 때 쓴다.
    노드 높이 계산이 확대율에 따라 흔들리지 않게 하려면 이 값을 써야 한다.
    """
    size = size_of(path)
    if size is None:
        return None
    width, height = size
    ratio = min(float(box_w) / width, float(box_h) / height)
    return max(1, int(width * ratio)), max(1, int(height * ratio))


def forget(path):
    """파일이 바뀌었을 때 캐시에서 지운다."""
    target = os.path.normcase(os.path.abspath(path))
    for key in [k for k in _originals if k[0] == target]:
        _originals.pop(key, None)
    for key in [k for k in _scaled if k[0] == target]:
        _scaled.pop(key, None)


def clear():
    _originals.clear()
    _scaled.clear()
