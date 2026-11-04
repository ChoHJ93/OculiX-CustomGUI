# -*- coding: utf-8 -*-
# PauseProbe.sikuli - 일시정지 문(PauseGate)의 시간 계산을 검증한다.
#
# 화면을 읽지도 건드리지도 않는다. 실제 실행을 멈췄다 푸는 시험은 graphtest.py
# 33절이 한다. 여기서는 거기서 재현하기 어려운 경우만 본다 - 감시 조건을 확인하는
# 도중에 멈춘 경우의 시간 계산, 눌린 버튼 경고, 신호를 쓰지 않는 실행.
#
# 실행:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Tests\PauseProbe.sikuli -c

from sikuli import *
import os
import sys
import tempfile
import threading
import time

sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import macro_engine

PASS = []
FAIL = []
PAUSE = macro_engine.PAUSE


def say(message):
    if isinstance(message, unicode):
        message = message.encode("utf-8")
    print(message)


def check(name, condition, detail=u""):
    (PASS if condition else FAIL).append(name)
    say(u"  [%s] %-44s %s" % ("PASS" if condition else "FAIL", name, detail))
    return condition


def make_engine():
    lines = []
    macro = {"name": u"pause", "settings": {}, "steps": []}
    return macro_engine.Engine(macro, ".", lambda m: lines.append(m)), lines


def touch(path):
    open(path, "w").close()


def release_after(path, seconds):
    def work():
        time.sleep(seconds)
        os.remove(path)
    t = threading.Thread(target=work)
    t.setDaemon(True)
    t.start()


class FakeWatch(object):
    """tick 만 흉내낸다. action 이 감시 한 바퀴에 해당한다."""

    def __init__(self, action):
        self.action = action

    def active(self):
        return True

    def tick(self, _engine):
        return self.action()


folder = tempfile.mkdtemp(prefix="pauseprobe_")
flag = os.path.join(folder, "pause.flag")

say(u"=== 신호를 쓰지 않는 실행 ===")
PAUSE.configure(None)
e, lines = make_engine()
touch(flag)
check(u"경로가 없으면 파일이 있어도 멈추지 않는다",
      PAUSE.hold(e, u"x") == 0.0 and lines == [], u"%r" % (lines,))
check(u"끼어들 것이 없으면 대기를 자르지 않는다", not e._sliced())
calls = []
e._watched(5, lambda s: calls.append(s) or True)
check(u"그때는 제한시간을 한 번에 넘긴다", calls == [5], u"%r" % (calls,))
os.remove(flag)

say(u"=== 멈춘 시간 계산 ===")
PAUSE.configure(flag)
e, lines = make_engine()
check(u"신호를 쓰는 실행은 대기를 자른다", e._sliced())
check(u"요청이 없으면 멈추지 않는다", PAUSE.hold(e, u"x") == 0.0 and lines == [])

touch(flag)
release_after(flag, 0.6)
spent = e._wait_tick()
check(u"멈춘 시간을 돌려준다", 0.5 <= spent <= 1.2, u"%.2f초" % spent)
check(u"누적 시간에 더해진다 (예산 계산에 쓰인다)",
      abs(PAUSE.total - spent) < 0.01, u"%.2f" % PAUSE.total)

# 감시 조건을 확인하는 도중에 멈춘 경우. 그 바퀴는 '걸린 것 없음' 이라 tick 이
# 0 을 준다. 그것만 믿으면 멈춘 시간이 대기의 제한시간에서 깎인다.
PAUSE.configure(flag)
e, lines = make_engine()


def paused_inside():
    touch(flag)
    release_after(flag, 0.5)
    PAUSE.hold(e, u"감시 조건")
    return 0.0


e.watch = FakeWatch(paused_inside)
spent = e._wait_tick()
check(u"감시 조건 확인 중에 멈춘 시간도 센다", spent >= 0.4, u"%.2f초" % spent)

# 감시가 걸려서 처리한 경우. 그 시간에 안에서 멈춘 시간이 이미 들어 있다.
PAUSE.configure(flag)
e, lines = make_engine()


def fired_with_pause():
    touch(flag)
    release_after(flag, 0.3)
    PAUSE.hold(e, u"감시 처리")
    return 2.0


e.watch = FakeWatch(fired_with_pause)
spent = e._wait_tick()
check(u"감시 처리 시간과 겹쳐 세지 않는다", 1.9 <= spent <= 2.1, u"%.2f초" % spent)

# 앞에서 멈추고 감시도 걸린 경우는 둘 다 센다
PAUSE.configure(flag)
e, lines = make_engine()
e.watch = FakeWatch(lambda: 2.0)
touch(flag)
release_after(flag, 0.4)
spent = e._wait_tick()
check(u"앞서 멈춘 시간과 감시 처리 시간을 더한다", 2.3 <= spent <= 2.8,
      u"%.2f초" % spent)

say(u"=== 대기 중 멈춤 ===")
PAUSE.configure(flag)
e, lines = make_engine()
touch(flag)
release_after(flag, 1.2)
start = time.time()
got = e._watched(0.5, lambda s: None)
elapsed = time.time() - start
check(u"제한시간보다 오래 멈춰도 남은 시간을 기다린다",
      got is None and elapsed >= 1.6, u"%.2f초" % elapsed)

say(u"=== 눌린 버튼 경고 ===")
PAUSE.configure(flag)
e, lines = make_engine()
touch(flag)
release_after(flag, 0.3)
PAUSE.hold(e, u"x")
check(u"눌린 버튼이 없으면 경고하지 않는다",
      not [l for l in lines if u"주의" in l], u"%d줄" % len(lines))

e, lines = make_engine()
PAUSE.held.add("LEFT")
touch(flag)
release_after(flag, 0.3)
PAUSE.hold(e, u"x")
check(u"눌린 버튼이 있으면 알린다",
      [l for l in lines if u"눌린 채" in l and u"LEFT" in l] != [],
      u"%d줄" % len(lines))

PAUSE.configure(None)
try:
    os.rmdir(folder)
except OSError:
    pass

say(u"")
say(u"=" * 62)
say(u"passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    say(u"실패:")
    for name in FAIL:
        say(u"  - %s" % name)
    sys.exit(1)
say(u"PAUSEPROBE_OK")
sys.exit(0)
