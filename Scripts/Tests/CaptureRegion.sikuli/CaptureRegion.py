# -*- coding: utf-8 -*-
# CaptureRegion.sikuli - 지정한 논리 좌표 영역을 OculiX가 직접 캡처해 PNG로 저장한다.
#
# 편집기(Python)가 GDI로 직접 캡처하지 않고 이쪽에 맡기는 이유:
# GDI 캡처는 물리 좌표/물리 해상도로 동작해서, 그대로 저장하면 OculiX가
# 실행 시점에 보는 논리 해상도 화면과 배율이 달라 매칭이 실패한다.
# OculiX가 캡처하면 실행 시점과 정확히 같은 픽셀을 얻는다.
#
# 사용: ... -r CaptureRegion.sikuli -c -- <x> <y> <w> <h> <저장경로>

from sikuli import *
import sys
import shutil

if len(sys.argv) < 6:
    print("usage: -- <x> <y> <w> <h> <dest.png>")
    sys.exit(2)

x, y, w, h = [int(v) for v in sys.argv[1:5]]
dest = sys.argv[5]

if w < 1 or h < 1:
    print("ERROR=영역이 너무 작습니다 (%dx%d)" % (w, h))
    sys.exit(2)

region = Region(x, y, w, h)
tmp = capture(region)
if not tmp:
    print("ERROR=캡처 실패")
    sys.exit(1)

shutil.copyfile(tmp, dest)
print("SAVED=%s" % dest)
print("REGION=%d,%d,%d,%d" % (x, y, w, h))
