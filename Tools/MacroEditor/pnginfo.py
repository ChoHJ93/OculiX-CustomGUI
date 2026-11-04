# -*- coding: utf-8 -*-
"""PNG 템플릿에서 매칭에 영향을 주는 정보만 읽는다 (표준 라이브러리만 사용).

왜 필요한가 - OculiX 4.0.0 의 버그 하나를 미리 잡으려는 것이다.

    템플릿에 투명 픽셀이 있으면 OculiX 는 그 부분을 마스크로 빼고 비교한다.
    첫 비교에서 못 찾으면, 템플릿의 DPI 가 시스템 DPI 와 다를 때 "배율이
    달라서 그런가" 하고 템플릿을 DPI 비율만큼 키워 다시 찾는데, 이때
    **마스크는 키우지 않는다.** 그래서 OpenCV 가

        (-215:Assertion failed) _templ.size() == _mask.size()
        in function 'cv::matchTemplateMask'

    로 죽는다. 대상이 화면에 아직 없을 때만(첫 비교 실패) 터지므로 제한시간을
    기다리지 않고 바로 실패한다. DPI 정보가 없는 PNG 도 "다르다"로 취급된다.
    (Finder$Finder2.doFindImage -> getDpiRatio -> doFindMatch 에서 확인.
     2026-10-29 실측: 투명+DPI 없음 / 투명+DPI 96 은 터지고, 투명+DPI 120 과
     투명 없음은 정상.)

그래서 "투명 픽셀이 실제로 있는가" 와 "DPI 가 몇인가" 두 가지만 본다.
알파 채널이 있어도 전부 불투명이면 마스크를 쓰지 않으므로 문제가 없다 -
그런 파일이 이 프로젝트에 여럿 있어서, 헛경고를 내지 않으려면 픽셀까지 봐야 한다.
"""

import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 색 형식별 픽셀당 채널 수
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class PngInfo(object):
    def __init__(self):
        self.width = 0
        self.height = 0
        self.dpi = None             # 기록이 없으면 None
        self.has_alpha = False      # 알파 채널 또는 tRNS 가 있는가
        self.transparent = False    # 실제로 255 미만인 픽셀이 있는가


def _chunks(data):
    pos = len(_SIGNATURE)
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        yield kind, body
        pos += 12 + length
        if kind == b"IEND":
            break


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw, width, height, bpp, stride):
    """IDAT 를 풀어 줄 단위 바이트로 돌려준다."""
    rows = []
    prev = bytearray(stride)
    pos = 0
    for _y in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        rows.append(line)
        prev = line
    return rows


def read(path):
    """PngInfo 를 돌려준다. PNG 가 아니거나 읽지 못하면 None."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except (IOError, OSError):
        return None
    if not data.startswith(_SIGNATURE):
        return None

    info = PngInfo()
    depth = color = interlace = None
    idat = []
    trns = None
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            (info.width, info.height, depth, color,
             _comp, _filt, interlace) = struct.unpack(">IIBBBBB", body)
        elif kind == b"pHYs" and len(body) >= 9:
            ppu_x, _ppu_y, unit = struct.unpack(">IIB", body[:9])
            if unit == 1:                       # 미터당 픽셀
                info.dpi = ppu_x * 0.0254
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if color is None:
        return None

    if color == 3:
        # 팔레트: tRNS 에 255 미만 항목이 하나라도 있으면 투명이 있다고 본다
        info.has_alpha = trns is not None
        info.transparent = bool(trns) and any(
            (b if isinstance(b, int) else ord(b)) < 255 for b in trns)
        return info
    if color in (0, 2):
        # 단색 투명키 - 마스크로 쓰일 수 있으므로 보수적으로 투명이라고 본다
        info.has_alpha = trns is not None
        info.transparent = trns is not None
        return info

    info.has_alpha = True                       # 4 (회색+알파) / 6 (RGBA)
    if interlace or depth not in (8, 16):
        info.transparent = True                 # 풀어 보지 못한다 - 보수적으로
        return info
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error:
        info.transparent = True
        return info
    channels = _CHANNELS[color]
    sample = depth // 8
    bpp = channels * sample
    stride = info.width * bpp
    for line in _unfilter(raw, info.width, info.height, bpp, stride):
        # 알파는 픽셀의 마지막 채널. 16비트면 상위 바이트만 봐도 255 여부를 안다.
        for off in range(bpp - sample, stride, bpp):
            if line[off] != 0xFF or (sample == 2 and line[off + 1] != 0xFF):
                info.transparent = True
                return info
    return info


def mask_dpi_risk(path, system_dpi):
    """투명 픽셀 + DPI 불일치로 OculiX 마스크 매칭이 죽을 수 있는가.

    위험하면 이유 문장을, 아니면 None 을 돌려준다.
    """
    info = read(path)
    if info is None or not info.transparent:
        return None
    if info.dpi is not None and abs(info.dpi - system_dpi) < 1.0:
        return None
    have = u"기록 없음" if info.dpi is None else u"%d" % round(info.dpi)
    return (u"투명 픽셀이 있는데 DPI가 시스템과 다릅니다 (이미지: %s, "
            u"시스템: %d). 대상이 아직 화면에 없을 때 OculiX 가 "
            u"'matchTemplateMask' 오류로 기다리지 않고 바로 실패합니다. "
            u"편집기의 [캡처]로 다시 찍거나, 이미지 DPI 를 시스템 값에 "
            u"맞추세요" % (have, round(system_dpi)))
