# -*- coding: utf-8 -*-
# ApiProbe.sikuli - verify which OculiX 4.0.0 APIs exist before writing real tests.
# Touches nothing on screen except reading pixels.

from sikuli import *
import sys

sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import pixel_util

failures = []


def check(label, fn):
    try:
        result = fn()
        print("  [OK  ] %-24s -> %s" % (label, result))
        return True
    except Exception, e:
        print("  [FAIL] %-24s -> %s: %s" % (label, type(e).__name__, e))
        failures.append(label)
        return False


print("=== 1. core callables present ===")
for name in ["click", "wait", "exists", "find", "mouseDown", "mouseUp",
             "keyDown", "keyUp", "type", "waitVanish", "hover", "dragDrop"]:
    present = name in globals() or hasattr(sys.modules["sikuli"], name)
    print("  %-12s : %s" % (name, present))
    if not present:
        failures.append("missing:" + name)

print("=== 2. core classes ===")
check("Region(...)", lambda: Region(0, 0, 100, 100))
check("Location(...)", lambda: Location(10, 10))
check("Pattern().similar()", lambda: Pattern("nonexistent.png").similar(0.90))
check("Screen(0)", lambda: Screen(0))
check("Button.LEFT", lambda: Button.LEFT)
check("Key.ESC", lambda: Key.ESC)

print("=== 3. Region methods used by the test plan ===")
r = Region(0, 0, 200, 200)
for m in ["exists", "find", "waitVanish", "click", "highlight", "getScreen", "setAutoWaitTimeout"]:
    ok = hasattr(r, m)
    print("  Region.%-20s : %s" % (m, ok))
    if not ok:
        failures.append("missing:Region." + m)

print("=== 4. java.awt.Robot availability (pixel colour path) ===")
check("Robot getPixelColor", lambda: pixel_util.get_pixel_rgb(5, 5))
check("is_color_similar same", lambda: pixel_util.is_color_similar((10, 20, 30), (12, 18, 33), 5))
check("is_color_similar diff", lambda: pixel_util.is_color_similar((10, 20, 30), (200, 20, 30), 5))
check("euclidean_distance", lambda: round(pixel_util.euclidean_distance((0, 0, 0), (10, 0, 0)), 3))

print("=== 5. negative-path timeout behaviour (must NOT hang) ===")
import time
t0 = time.time()
res = pixel_util.wait_pixel_color(5, 5, (1, 2, 3), tolerance=0, timeout=1.0, interval=0.1)
elapsed = time.time() - t0
print("  impossible colour -> %s in %.2fs (expected None in ~1.0s)" % (res, elapsed))
if res is not None or elapsed > 3.0:
    failures.append("wait_pixel_color timeout misbehaved")

t0 = time.time()
missing = exists(Pattern("definitely_not_on_screen.png").similar(0.99), 2)
elapsed = time.time() - t0
print("  exists() on missing image -> %s in %.2fs (expected None in ~2s)" % (missing, elapsed))

print("=== RESULT ===")
if failures:
    print("FAILURES: %s" % failures)
    print("PROBE_FAILED")
else:
    print("PROBE_OK")
