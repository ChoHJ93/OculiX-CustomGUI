# -*- coding: utf-8 -*-
# BasicTest.sikuli - OculiX runtime smoke test
# Purpose: confirm the Jython runtime, sikuli API import and screen access work.
# Note: popup() is deliberately NOT used - it is modal and would block a CLI run.

from sikuli import *
import sys

print("=== OculiX smoke test ===")
print("jython version    : %s" % sys.version.replace("\n", " "))
print("platform          : %s" % sys.platform)

n = Screen.getNumberScreens()
print("number of screens : %d" % n)
for i in range(n):
    s = Screen(i)
    print("  Screen(%d) bounds: %s" % (i, s.getBounds()))

print("default similarity: %s" % Settings.MinSimilarity)
print("bundle path       : %s" % getBundlePath())

print("SMOKE_OK")
