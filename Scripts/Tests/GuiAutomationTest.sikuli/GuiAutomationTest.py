# -*- coding: utf-8 -*-
# GuiAutomationTest.sikuli
#
# Verifies the OculiX feature set required by the project against a dedicated
# WinForms target window (Scripts/Tests/TestTarget.ps1), which must already be
# running. Every assertion is checked twice where possible:
#   * visually, through OculiX (image match / pixel colour)
#   * against ground truth, through the target app's state file
#
# Every wait is bounded. The script never loops without a deadline.

from sikuli import *
import sys
import os
import time
import shutil

COMMON = "D:\\Programming\\Oculix-Automation\\Scripts\\Common"
BUNDLE = "D:\\Programming\\Oculix-Automation\\Scripts\\Tests\\GuiAutomationTest.sikuli"
STATE  = "D:\\Programming\\Oculix-Automation\\Logs\\target_state.txt"

sys.path.append(COMMON)
import pixel_util

RESULTS = []


def record(name, passed, detail=""):
    RESULTS.append((name, passed, detail))
    if passed:
        status = "PASS"
    else:
        status = "FAIL"
    print("[%s] %-28s %s" % (status, name, detail))
    return passed


# ---------------------------------------------------------------- state file

def read_state(retries=5):
    """Read the target app's state file. Retries because the app rewrites it
    on every event and the write is not atomic."""
    for attempt in range(retries):
        try:
            f = open(STATE, "r")
            try:
                text = f.read()
            finally:
                f.close()
            d = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    d[k] = v
            if "rect.form" in d:
                return d
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("could not read state file: %s" % STATE)


def rect_of(state, name):
    parts = [int(v) for v in state["rect." + name].split(",")]
    return Region(parts[0], parts[1], parts[2], parts[3])


def center_of(region):
    return Location(region.getX() + region.getW() / 2,
                    region.getY() + region.getH() / 2)


# ---------------------------------------------------------------- test steps

def test_delay():
    t0 = time.time()
    wait(1.0)
    elapsed = time.time() - t0
    ok = 0.9 <= elapsed <= 2.0
    return record("A delay wait(1.0)", ok, "elapsed=%.2fs" % elapsed)


def capture_template(region, filename):
    """Capture a screen region into this bundle and return the absolute path."""
    tmp = capture(region)
    dest = os.path.join(BUNDLE, filename)
    shutil.copyfile(tmp, dest)
    return dest


def test_capture_and_match(label_region):
    path = capture_template(label_region, "target.png")
    ok_file = os.path.exists(path) and os.path.getsize(path) > 0
    record("E1 template capture", ok_file, "%s (%d bytes)" % (
        os.path.basename(path), os.path.getsize(path)))

    pattern = Pattern(path).similar(0.90)
    t0 = time.time()
    match = exists(pattern, 5)
    elapsed = time.time() - t0
    if match is None:
        return record("E2 exists() full screen", False, "no match in %.2fs" % elapsed), None

    score = match.getScore()
    dx = abs(match.getX() - label_region.getX())
    dy = abs(match.getY() - label_region.getY())
    ok = score >= 0.90 and dx <= 5 and dy <= 5
    record("E2 exists() full screen", ok,
           "score=%.4f at (%d,%d) offset=(%d,%d) in %.2fs" % (
               score, match.getX(), match.getY(), dx, dy, elapsed))

    match.highlight(1)
    record("E3 match.highlight(1)", True, "overlay drawn")
    return ok, path


def test_similarity(path):
    strict = exists(Pattern(path).similar(0.99), 3)
    loose = exists(Pattern(path).similar(0.70), 3)
    ok = strict is not None and loose is not None
    detail = "similar(0.99)=%s similar(0.70)=%s" % (
        strict is not None, loose is not None)
    if strict is not None:
        detail += " strict_score=%.4f" % strict.getScore()
    return record("F1 Pattern.similar()", ok, detail)


def test_region_search(path, form_region, label_region):
    pattern = Pattern(path).similar(0.90)

    inside = form_region.exists(pattern, 5)
    ok_pos = inside is not None
    record("F2 Region positive", ok_pos,
           "found inside form region: %s" % (inside is not None))

    # A region deliberately away from the label must NOT match, and must give up
    # at the timeout rather than hang. The search region has to be larger than
    # the template in both axes or OculiX raises SikuliXception instead.
    pad = 60
    ew = label_region.getW() + pad
    eh = label_region.getH() + pad
    ex = form_region.getX()
    ey = form_region.getY() + form_region.getH() + 20
    screen = Screen(0).getBounds()
    if ey + eh > screen.height:
        ey = max(0, form_region.getY() - eh - 20)
    empty = Region(ex, ey, ew, eh)
    t0 = time.time()
    try:
        outside = empty.exists(pattern, 3)
        elapsed = time.time() - t0
        ok_neg = outside is None and elapsed < 8.0
        record("F3 Region negative+timeout", ok_neg,
               "search %dx%d at (%d,%d) -> %s after %.2fs (expected None ~3s)" % (
                   ew, eh, ex, ey, outside, elapsed))
    except Exception, e:
        ok_neg = False
        record("F3 Region negative+timeout", False, "%s: %s" % (type(e).__name__, e))
    return ok_pos and ok_neg


def test_mouse_click(button_region):
    before = int(read_state()["clicks"])
    click(center_of(button_region))
    deadline = time.time() + 5.0
    after = before
    while time.time() < deadline:
        after = int(read_state()["clicks"])
        if after > before:
            break
        time.sleep(0.2)
    ok = after == before + 1
    return record("B mouse click()", ok, "clicks %d -> %d (app-confirmed)" % (before, after))


def test_mouse_down_up(status_region):
    st = read_state()
    d0 = int(st["mouse_downs"])
    u0 = int(st["mouse_ups"])
    hover(center_of(status_region))
    mouseDown(Button.LEFT)
    wait(0.5)
    mouseUp(Button.LEFT)
    deadline = time.time() + 5.0
    d1, u1 = d0, u0
    while time.time() < deadline:
        st = read_state()
        d1 = int(st["mouse_downs"])
        u1 = int(st["mouse_ups"])
        if d1 > d0 and u1 > u0:
            break
        time.sleep(0.2)
    ok = d1 > d0 and u1 > u0
    return record("C mouseDown/mouseUp", ok,
                  "downs %d->%d ups %d->%d (app-confirmed)" % (d0, d1, u0, u1))


def test_keyboard(textbox_region):
    click(center_of(textbox_region))
    wait(0.3)

    keyDown("a")
    wait(0.3)
    keyUp("a")
    deadline = time.time() + 5.0
    downs, ups = "", ""
    while time.time() < deadline:
        st = read_state()
        downs = st.get("key_downs", "")
        ups = st.get("key_ups", "")
        if "A" in downs.split("|") and "A" in ups.split("|"):
            break
        time.sleep(0.2)
    ok_du = "A" in downs.split("|") and "A" in ups.split("|")
    record("D1 keyDown/keyUp", ok_du, "key_downs=[%s] key_ups=[%s]" % (downs, ups))

    type("OCULIX42")
    deadline = time.time() + 5.0
    text = ""
    while time.time() < deadline:
        text = read_state().get("textbox", "")
        if "OCULIX42" in text:
            break
        time.sleep(0.2)
    ok_type = "OCULIX42" in text
    record("D2 type() text entry", ok_type, "textbox=%r (app-confirmed)" % text)
    return ok_du and ok_type


def test_pixel_before_click(status_region):
    c = center_of(status_region)
    rgb = pixel_util.get_pixel_rgb(c.getX(), c.getY())
    ok_read = pixel_util.is_color_similar(rgb, (200, 30, 30), 12)
    record("P1 pixel read (red)", ok_read, "rgb=%s expected~(200,30,30)" % (rgb,))

    t0 = time.time()
    got = pixel_util.wait_pixel_color(c.getX(), c.getY(), (200, 30, 30),
                                      tolerance=12, timeout=3.0, interval=0.1)
    ok_wait = got is not None and (time.time() - t0) < 1.0
    record("P2 wait_pixel_color hit", ok_wait, "returned %s fast" % (got,))

    t0 = time.time()
    miss = pixel_util.wait_pixel_color(c.getX(), c.getY(), (1, 2, 3),
                                       tolerance=0, timeout=2.0, interval=0.1)
    elapsed = time.time() - t0
    ok_timeout = miss is None and 1.8 <= elapsed <= 4.0
    record("P3 wait_pixel_color timeout", ok_timeout,
           "returned %s after %.2fs (expected None ~2.0s)" % (miss, elapsed))

    tol_ok = (pixel_util.is_color_similar((200, 30, 30), (208, 22, 38), 10) and
              not pixel_util.is_color_similar((200, 30, 30), (215, 30, 30), 10))
    record("P4 per-channel tolerance", tol_ok, "boundary behaviour correct")
    return ok_read and ok_wait and ok_timeout and tol_ok


def test_vanish_and_color_change(vanish_region, status_region, button_region):
    vanish_path = capture_template(vanish_region, "vanish.png")
    pattern = Pattern(vanish_path).similar(0.90)

    present = exists(pattern, 3)
    record("G1 vanish target present", present is not None,
           "blue panel matched before click")

    # Clicking the button turns the status panel green and hides the blue panel.
    click(center_of(button_region))

    # waitVanish is scoped to the panel's own region, not the whole screen.
    # A screen-wide search reported "still there" because a similar-looking
    # area elsewhere matched the template - the failure mode that region
    # limiting exists to prevent.
    t0 = time.time()
    gone = vanish_region.waitVanish(pattern, 10)
    elapsed = time.time() - t0
    ok_vanish = bool(gone)
    record("G2 waitVanish() in region", ok_vanish,
           "returned %s after %.2fs" % (gone, elapsed))

    c = center_of(status_region)
    t0 = time.time()
    green = pixel_util.wait_pixel_color(c.getX(), c.getY(), (30, 160, 60),
                                        tolerance=12, timeout=5.0, interval=0.1)
    ok_green = green is not None
    record("P5 pixel change red->green", ok_green,
           "rgb=%s after %.2fs" % (green, time.time() - t0))

    st = read_state()
    ok_state = st.get("vanish_visible", "") == "False" and st.get("status_rgb", "") == "30,160,60"
    record("G3 app state confirms", ok_state,
           "vanish_visible=%s status_rgb=%s" % (
               st.get("vanish_visible"), st.get("status_rgb")))
    return ok_vanish and ok_green and ok_state


def test_negative_image_timeout():
    t0 = time.time()
    missing = exists(Pattern(os.path.join(BUNDLE, "target.png")).similar(0.999999), 3)
    elapsed = time.time() - t0
    ok = elapsed < 8.0
    return record("H exists() bounded", ok,
                  "result=%s after %.2fs (must not hang)" % (missing, elapsed))


# ---------------------------------------------------------------- main

def main():
    print("=== OculiX GUI automation verification ===")
    try:
        state = read_state()
    except Exception, e:
        print("FATAL: %s" % e)
        print("Is TestTarget.ps1 running?")
        return 1

    form    = rect_of(state, "form")
    label   = rect_of(state, "label")
    status  = rect_of(state, "status")
    vanish  = rect_of(state, "vanish")
    button  = rect_of(state, "button")
    textbox = rect_of(state, "textbox")
    print("target window: %s" % form)

    # Order matters: the button click is a one-way state change (red->green,
    # blue panel hidden), so everything that depends on the initial state must
    # run before it.
    # Each step is isolated: one failing assertion must not abort the suite,
    # otherwise a single defect hides every result after it.
    def run(label_name, fn):
        try:
            return fn()
        except Exception, e:
            record(label_name + " (crashed)", False, "%s: %s" % (type(e).__name__, e))
            return None

    run("A", test_delay)
    matched, path = run("E", lambda: test_capture_and_match(label)) or (False, None)
    if path:
        run("F1", lambda: test_similarity(path))
        run("F2/F3", lambda: test_region_search(path, form, label))
    run("P1-P4", lambda: test_pixel_before_click(status))                       # needs red panel
    run("G/P5", lambda: test_vanish_and_color_change(vanish, status, button))   # performs the 1st click
    run("B", lambda: test_mouse_click(button))                                  # 2nd click, counter only
    run("C", lambda: test_mouse_down_up(status))
    run("D", lambda: test_keyboard(textbox))
    run("H", test_negative_image_timeout)

    print("")
    print("=== SUMMARY ===")
    passed = len([r for r in RESULTS if r[1]])
    total = len(RESULTS)
    for name, ok, detail in RESULTS:
        if ok:
            mark = "PASS"
        else:
            mark = "FAIL"
        print("  %-4s %-28s %s" % (mark, name, detail))
    print("passed %d / %d" % (passed, total))
    if passed == total:
        print("ALL_TESTS_PASSED")
        return 0
    print("SOME_TESTS_FAILED")
    return 1


main()
