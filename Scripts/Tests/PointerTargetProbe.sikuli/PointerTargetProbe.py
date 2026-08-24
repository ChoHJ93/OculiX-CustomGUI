# -*- coding: utf-8 -*-
# PointerTargetProbe.sikuli - _target() 의 '대상 없음 -> 현재 커서' 처리 확인.
#
# 화면에 입력을 주입하지 않는다. 커서 위치를 읽기만 하므로 언제 돌려도 안전하다.
#
# 사용:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Tests\PointerTargetProbe.sikuli -c

from sikuli import *
import sys

sys.path.append("D:\Programming\Oculix-Automation\Scripts\Common")
import macro_engine
from java.awt import MouseInfo

PASS = []
FAIL = []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print("  [%s] %-52s %s" % ("PASS" if condition else "FAIL", name, detail))


engine = macro_engine.Engine({"settings": {}},
                             "D:\Programming\Oculix-Automation\Scripts\Tests")

here = MouseInfo.getPointerInfo().getLocation()
cursor = (int(here.x), int(here.y))
print("=== 현재 커서 %r ===" % (cursor,))

# 1) 대상이 없고 allow_pointer 면 커서 위치가 나와야 한다
spot = engine._target({"type": "click"}, allow_pointer=True)
got = None if spot is None else (int(spot.getX()), int(spot.getY()))
check("대상 없음 -> 현재 커서 위치", got == cursor, "%r vs %r" % (got, cursor))

# 2) allow_pointer 없이는 예전처럼 MacroError
try:
    engine._target({"type": "drag"})
    check("allow_pointer 없으면 MacroError", False, "예외가 나지 않았다")
except macro_engine.MacroError:
    check("allow_pointer 없으면 MacroError", True)

# 3) 좌표를 주면 그대로 쓴다 (기존 동작 유지)
spot = engine._target({"type": "click", "point": [123, 456]}, allow_pointer=True)
got = (int(spot.getX()), int(spot.getY()))
check("좌표를 주면 그대로 사용", got == (123, 456), "%r" % (got,))

# 4) 커서를 읽지 못하면 클릭하지 않고 None 을 돌려줘야 한다
real_pointer = engine._pointer
engine._pointer = lambda: None
try:
    check("커서를 못 읽으면 None", engine._target({"type": "click"},
                                            allow_pointer=True) is None)
finally:
    engine._pointer = real_pointer

# 5) 대상 없는 wheel 이 실제로 OculiX 호출까지 통과하는지.
#    amount=0 이라 화면은 움직이지 않는다 (호출이 받아들여지는지만 본다).
try:
    ok = engine._dispatch({"type": "wheel", "amount": 0, "direction": "down"},
                          "wheel")
    check("대상 없는 wheel 이 호출까지 통과", ok is True, "%r" % (ok,))
except Exception, e:
    check("대상 없는 wheel 이 호출까지 통과", False,
          "%s: %s" % (e.__class__.__name__, e))

# 6) targetOffset 이 실제로 먹는가. 드래그의 시작/끝도 같은 _target 을 지나므로
#    여기서 확인되면 드래그 양 끝에도 그대로 적용된다.
#    화면 한 조각을 떠서 그것을 찾게 하면 반드시 걸린다.
import tempfile
import shutil as _shutil

_work = tempfile.mkdtemp(prefix="offsetprobe_")
_shot = capture(Region(300, 300, 160, 90))
if not _shot:
    check("targetOffset 검증용 화면 조각", False, "capture 실패")
else:
    _shutil.copyfile(_shot, os.path.join(_work, "onscreen.png"))
    probe_engine = macro_engine.Engine({"settings": {}}, _work)

    plain = probe_engine._target({"type": "click", "image": "onscreen.png",
                                  "region": [280, 280, 200, 130], "timeout": 3})
    if plain is None:
        check("targetOffset: 기준 이미지를 찾음", False, "뜬 자리를 못 찾았다")
    else:
        check("targetOffset: 기준 이미지를 찾음", True)
        base = plain.getTarget()
        shifted = probe_engine._target(
            {"type": "click", "image": "onscreen.png",
             "region": [280, 280, 200, 130], "timeout": 3,
             "targetOffset": [12, -7]})
        if shifted is None:
            check("targetOffset 적용", False, "오프셋을 준 쪽을 못 찾았다")
        else:
            spot = shifted.getTarget()
            dx = int(spot.getX()) - int(base.getX())
            dy = int(spot.getY()) - int(base.getY())
            check("targetOffset 적용", (dx, dy) == (12, -7),
                  "중앙 대비 (%d,%d)" % (dx, dy))
_shutil.rmtree(_work, ignore_errors=True)

# 7) 확인만 하고 아무것도 누르지 않았는지 - 커서가 그대로여야 한다
after = MouseInfo.getPointerInfo().getLocation()
check("프로브가 커서를 움직이지 않았다",
      (int(after.x), int(after.y)) == cursor,
      "%r" % ((int(after.x), int(after.y)),))

print("")
print("passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
if not FAIL:
    print("PROBE_OK")
