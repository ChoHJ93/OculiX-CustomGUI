# -*- coding: utf-8 -*-
# CoordProbe.sikuli - diagnose the multi-monitor / DPI coordinate mismatch.
# Moves the pointer to known points and reads back where it actually landed.

from sikuli import *
from java.awt import MouseInfo, GraphicsEnvironment
import time

print("=== GraphicsDevice view ===")
ge = GraphicsEnvironment.getLocalGraphicsEnvironment()
for gd in ge.getScreenDevices():
    cfg = gd.getDefaultConfiguration()
    b = cfg.getBounds()
    tx = cfg.getDefaultTransform()
    print("  %s bounds=%s scaleX=%.3f scaleY=%.3f" % (
        gd.getIDstring(), b, tx.getScaleX(), tx.getScaleY()))

print("=== OculiX Screen view ===")
for i in range(Screen.getNumberScreens()):
    print("  Screen(%d) = %s" % (i, Screen(i).getBounds()))

print("=== pointer round-trip on Screen(0) ===")
worst = 0
for (x, y) in [(100, 100), (358, 521), (1000, 600), (1500, 900)]:
    hover(Location(x, y))
    time.sleep(0.4)
    p = MouseInfo.getPointerInfo().getLocation()
    dx = abs(p.x - x)
    dy = abs(p.y - y)
    worst = max(worst, dx, dy)
    print("  requested (%4d,%4d) -> actual (%4d,%4d)  delta=(%d,%d)" % (x, y, p.x, p.y, dx, dy))

print("worst_delta=%d" % worst)
if worst <= 2:
    print("COORD_OK")
else:
    print("COORD_MISMATCH")
