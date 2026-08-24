# -*- coding: utf-8 -*-
# ReadPixel.sikuli - 지정 좌표의 픽셀 색을 OculiX 좌표계에서 읽어 출력한다.
# 편집기(Python 3)의 좌표계가 OculiX와 일치하는지 대조하는 데 쓴다.
#
# 사용: ... -r ReadPixel.sikuli -c -- <x> <y>

from sikuli import *
import sys

sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import pixel_util

if len(sys.argv) < 3:
    print("usage: -- <x> <y>")
    sys.exit(2)

x = int(sys.argv[1])
y = int(sys.argv[2])

b = Screen(0).getBounds()
print("SCREEN0=%d,%d,%d,%d" % (b.x, b.y, b.width, b.height))
r, g, bl = pixel_util.get_pixel_rgb(x, y)
print("PIXEL=%d,%d,%d" % (r, g, bl))
