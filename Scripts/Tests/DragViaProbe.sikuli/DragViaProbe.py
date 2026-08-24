# -*- coding: utf-8 -*-
# DragViaProbe.sikuli - 경유지 드래그가 실제로 경유지를 지나는지 확인한다.
#
# TestTarget.ps1 창이 떠 있어야 한다. 드래그는 그 창 안에서만 일어난다.
# 시작점을 빨간 상태 패널로 잡는 이유: 그 패널만 mouseDown/mouseUp 을 세는데,
# WinForms 가 누른 순간 마우스를 캡처하므로 어디서 놓든 둘 다 기록된다.
# 즉 "눌렸다" 와 "놓였다" 를 앱이 받은 값으로 대조할 수 있다.
#
# 사용:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Tests\DragViaProbe.sikuli -c

from sikuli import *
import sys
import os
import time

sys.path.append("D:/Programming/Oculix-Automation/Scripts/Common")
import macro_engine
from java.awt import MouseInfo

STATE = "D:/Programming/Oculix-Automation/Logs/target_state.txt"

PASS = []
FAIL = []


def say(message):
    if isinstance(message, unicode):
        try:
            message = message.encode("utf-8")
        except Exception:
            message = message.encode("ascii", "replace")
    print(message)


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    say(u"  [%s] %-46s %s" % ("PASS" if condition else "FAIL", name, detail))


def state():
    out = {}
    if not os.path.exists(STATE):
        return out
    handle = open(STATE, "rb")
    try:
        raw = handle.read().decode("utf-8-sig")
    finally:
        handle.close()
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def rect(name):
    return [int(v) for v in state()["rect." + name].split(",")]


def pointer():
    try:
        p = MouseInfo.getPointerInfo().getLocation()
        return (int(p.x), int(p.y))
    except Exception:
        return None


class Recorder(object):
    """엔진이 쓰는 Screen 을 감싸서 어떤 순서로 무엇을 했는지 적어 둔다.

    프로브가 같은 순서를 흉내 내면 프로브를 검사하는 꼴이 된다.
    엔진이 실제로 부른 것을 기록해야 의미가 있다.
    """

    def __init__(self, screen):
        self._screen = screen
        self.events = []
        self.fail_on_hover = 0
        self._hovers = 0

    def drag(self, target):
        result = self._screen.drag(target)
        self.events.append(("drag", pointer()))
        return result

    def hover(self, target):
        self._hovers += 1
        if self.fail_on_hover and self._hovers == self.fail_on_hover:
            self.events.append(("hover-raise", pointer()))
            raise RuntimeError("일부러 낸 오류")
        result = self._screen.hover(target)
        self.events.append(("hover", pointer()))
        return result

    def dropAt(self, target):
        result = self._screen.dropAt(target)
        self.events.append(("drop", pointer()))
        return result

    def mouseUp(self, button):
        self.events.append(("mouseUp", pointer()))
        return self._screen.mouseUp(button)

    def __getattr__(self, name):
        return getattr(self._screen, name)


if "rect.form" not in state():
    say(u"TestTarget.ps1 을 먼저 실행하세요 (%s 없음)" % STATE)
    sys.exit(2)

fx, fy, fw, fh = rect("form")
sx, sy, sw, sh = rect("status")
start = [sx + sw // 2, sy + sh // 2]
via = [[fx + 620, fy + 140], [fx + 620, fy + 430]]
end = [fx + 700, fy + 500]
say(u"창 %r  시작 %r  경유 %r  끝 %r" % ([fx, fy, fw, fh], start, via, end))

engine = macro_engine.Engine({"settings": {}}, os.path.dirname(STATE))
recorder = Recorder(engine.screen)
engine.screen = recorder

before = state()
step = {"type": "drag",
        "from": {"point": start},
        "to": {"point": end},
        "waypoints": via}
ok = engine._dispatch(step, "drag")
time.sleep(0.4)                      # 창이 상태 파일을 쓸 틈을 준다
after = state()

check(u"드래그가 성공으로 끝난다", ok is True, "%r" % (ok,))

kinds = [name for name, _spot in recorder.events]
check(u"누르기 - 경유 - 놓기 순서",
      kinds == ["drag", "hover", "hover", "drop"], "%r" % (kinds,))

spots = dict()
hovers = [spot for name, spot in recorder.events if name == "hover"]
check(u"경유지를 순서대로 지난다", hovers == [tuple(v) for v in via],
      u"기대 %r  실제 %r" % ([tuple(v) for v in via], hovers))

drop_spot = [spot for name, spot in recorder.events if name == "drop"]
check(u"끝점에서 놓는다", drop_spot and drop_spot[0] == tuple(end),
      u"%r" % (drop_spot,))

down_delta = int(after.get("mouse_downs", 0)) - int(before.get("mouse_downs", 0))
up_delta = int(after.get("mouse_ups", 0)) - int(before.get("mouse_ups", 0))
check(u"앱이 누름을 받았다", down_delta == 1, u"mouse_downs +%d" % down_delta)
check(u"앱이 놓음을 받았다", up_delta == 1, u"mouse_ups +%d" % up_delta)

# 경유 도중에 터져도 버튼을 놓고 나와야 한다.
# 안 놓으면 그 뒤 모든 조작이 눌린 채로 진행돼 화면이 엉망이 된다.
say(u"--- 경유 도중 오류가 났을 때 ---")
before2 = state()
recorder.events = []
recorder.fail_on_hover = 2
recorder._hovers = 0
raised = False
try:
    engine._dispatch(step, "drag")
except Exception:
    raised = True
time.sleep(0.4)
after2 = state()

check(u"오류는 그대로 올라간다", raised)
kinds2 = [name for name, _spot in recorder.events]
check(u"터져도 mouseUp 을 부른다", "mouseUp" in kinds2, u"%r" % (kinds2,))
up_delta2 = int(after2.get("mouse_ups", 0)) - int(before2.get("mouse_ups", 0))
check(u"터져도 앱이 놓음을 받았다", up_delta2 == 1, u"mouse_ups +%d" % up_delta2)

say(u"")
say(u"passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
if not FAIL:
    say(u"PROBE_OK")
