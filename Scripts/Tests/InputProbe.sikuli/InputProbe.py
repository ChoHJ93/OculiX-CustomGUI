# -*- coding: utf-8 -*-
# InputProbe.sikuli - separate "Robot cannot move the pointer" from
# "something external keeps moving the pointer".

from sikuli import *
from java.awt import MouseInfo, Robot
import time

robot = Robot()


def pos():
    p = MouseInfo.getPointerInfo().getLocation()
    return (p.x, p.y)


print("=== 1. is the pointer stable when nobody commands it? ===")
samples = []
for i in range(10):
    samples.append(pos())
    time.sleep(0.2)
moved = len(set(samples)) > 1
print("  samples: %s" % (samples,))
if moved:
    print("  VERDICT: pointer moves on its own -> EXTERNAL INTERFERENCE")
else:
    print("  VERDICT: pointer is stable when idle")

print("=== 2. raw java.awt.Robot.mouseMove, read back immediately ===")
for (x, y) in [(300, 300), (800, 400), (1200, 700)]:
    robot.mouseMove(x, y)
    immediate = pos()
    time.sleep(0.5)
    later = pos()
    print("  mouseMove(%4d,%4d) -> immediate %s  after 0.5s %s" % (x, y, immediate, later))

print("=== 3. does it stick if we re-assert repeatedly? ===")
robot.mouseMove(600, 400)
hits = 0
for i in range(10):
    robot.mouseMove(600, 400)
    time.sleep(0.1)
    if pos() == (600, 400):
        hits += 1
print("  landed exactly on (600,400) in %d/10 attempts" % hits)

print("=== 4. final resting position ===")
print("  %s" % (pos(),))
print("PROBE_DONE")
