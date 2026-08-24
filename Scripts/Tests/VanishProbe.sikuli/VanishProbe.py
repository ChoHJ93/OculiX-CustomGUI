# -*- coding: utf-8 -*-
# VanishProbe.sikuli - waitVanish 실패 원인 진단.
#
# 대상 패널은 이미 숨겨진 상태여야 한다. 그런데도 템플릿이 화면 어딘가에
# 매칭된다면, 그 템플릿이 단색이라 다른 곳과 구분되지 않는다는 뜻이다.

from sikuli import *
import os

BUNDLE = "D:\\Programming\\Oculix-Automation\\Scripts\\Tests\\GuiAutomationTest.sikuli"
path = os.path.join(BUNDLE, "vanish.png")

print("template: %s (%d bytes)" % (path, os.path.getsize(path)))

img = Image.create(path)
print("template size: %dx%d" % (img.getSize().width, img.getSize().height))

for similarity in (0.99, 0.95, 0.90, 0.80):
    pattern = Pattern(path).similar(similarity)
    match = exists(pattern, 1)
    if match:
        print("  similar(%.2f) -> MATCH score=%.4f at (%d,%d) %dx%d" % (
            similarity, match.getScore(), match.getX(), match.getY(),
            match.getW(), match.getH()))
    else:
        print("  similar(%.2f) -> no match" % similarity)

print("--- 화면 전체에서 몇 군데나 매칭되나 (0.90) ---")
try:
    hits = list(findAll(Pattern(path).similar(0.90)))
    print("  %d곳" % len(hits))
    for m in hits[:8]:
        print("    score=%.4f at (%d,%d)" % (m.getScore(), m.getX(), m.getY()))
except Exception, e:
    print("  findAll: %s: %s" % (e.__class__.__name__, e))

print("--- 템플릿이 단색인지 확인 ---")
import sys
sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import pixel_util
from java.io import File
from javax.imageio import ImageIO
bi = ImageIO.read(File(path))
colours = set()
for y in range(0, bi.getHeight(), 7):
    for x in range(0, bi.getWidth(), 7):
        rgb = bi.getRGB(x, y)
        colours.add(((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF))
print("  서로 다른 색: %d개  %s" % (len(colours), list(colours)[:5]))
if len(colours) <= 2:
    print("  => 단색 템플릿. 화면의 같은 색 영역이면 어디든 매칭된다.")
print("PROBE_DONE")
