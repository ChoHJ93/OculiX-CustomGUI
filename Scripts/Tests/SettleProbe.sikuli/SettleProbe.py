# -*- coding: utf-8 -*-
# SettleProbe.sikuli - "찾은 자리가 멈췄는지 확인" 로직(_settled)을 검증한다.
#
# 화면을 읽지도 건드리지도 않는다. 찾기 함수를 가짜로 바꿔 끼워서, 목록이
# 스크롤 중일 때 엔진이 어떤 자리를 돌려주는지만 본다. 실제로 움직이는 UI를
# 띄우지 않고도 "옆 항목을 누르는" 사고의 재발을 잡을 수 있다.
#
# 실행:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Tests\SettleProbe.sikuli -c

from sikuli import *
import sys
import time

sys.path.append("D:\Programming\Oculix-Automation\Scripts\Common")
import macro_engine

PASS = []
FAIL = []


def say(message):
    if isinstance(message, unicode):
        try:
            message = message.encode("utf-8")
        except Exception:
            message = message.encode("ascii", "replace")
    print(message)


def check(name, condition, detail=u""):
    (PASS if condition else FAIL).append(name)
    say(u"  [%s] %-46s %s" % ("PASS" if condition else "FAIL", name, detail))
    return condition


class FakeMatch(object):
    """Match 중에서 _settled 가 쓰는 것만 흉내낸다."""

    def __init__(self, x, y, w=147, h=73):
        self._x, self._y, self._w, self._h = x, y, w, h

    def getX(self):
        return self._x

    def getY(self):
        return self._y

    def getW(self):
        return self._w

    def getH(self):
        return self._h

    def __repr__(self):
        return "(%d,%d)" % (self._x, self._y)


def make_engine():
    macro = {"name": u"settle", "settings": {}, "steps": []}
    return macro_engine.Engine(macro, ".", lambda m: None)


def scripted(engine, spots):
    """찾기 결과를 대본대로 돌려준다. 대본이 끝나면 마지막 값을 계속 준다."""
    box = {"i": 0}

    def nxt(*_args):
        i = min(box["i"], len(spots) - 1)
        box["i"] += 1
        return spots[i]
    engine._find_at = nxt
    engine._find_now = nxt
    return box


say(u"=== _settled: 목록이 움직이는 동안 집지 않는가 ===")

# 1) settleFor 를 주지 않으면 예전 그대로 - 확인도, 지연도 없다
e = make_engine()
scripted(e, [FakeMatch(200, 999)])
start = time.time()
got = e._settled({"image": "x.png"}, FakeMatch(200, 100))
check(u"settleFor 없으면 그대로 돌려준다",
      got.getY() == 100 and (time.time() - start) < 0.1,
      u"%r  %.2fs" % (got, time.time() - start))

# 2) 멈춰 있으면 그 자리를 그대로 준다
e = make_engine()
scripted(e, [FakeMatch(200, 100)])
start = time.time()
got = e._settled({"image": "x.png", "settleFor": 0.4, "timeout": 5}, 
                 FakeMatch(200, 100))
elapsed = time.time() - start
check(u"멈춰 있으면 그 자리를 준다", got.getY() == 100, u"%r" % (got,))
check(u"멈춘 것을 확인하는 데 settleFor 만큼만 쓴다",
      0.35 <= elapsed <= 1.6, u"%.2fs" % elapsed)

# 3) 스크롤 중이면 멈출 때까지 기다렸다가 **마지막** 자리를 준다.
#    이것이 실제 사고다 - 예전에는 처음 본 (200,100) 을 눌러서, 그 사이
#    그 자리로 밀려온 다른 항목을 클릭했다.
e = make_engine()
scripted(e, [FakeMatch(200, 160), FakeMatch(200, 240), FakeMatch(200, 300),
             FakeMatch(200, 300), FakeMatch(200, 300), FakeMatch(200, 300),
             FakeMatch(200, 300)])
got = e._settled({"image": "x.png", "settleFor": 0.4, "timeout": 8},
                 FakeMatch(200, 100))
check(u"스크롤이 끝난 자리를 준다 (처음 본 자리가 아니라)",
      got.getY() == 300, u"%r" % (got,))

# 4) 끝없이 움직이면 제한시간에 마지막으로 본 자리로 진행한다.
#    멈추지 않는다고 실패로 만들면 애니메이션이 도는 UI 를 아예 못 쓴다.
e = make_engine()
box = {"y": 0}

def wandering(*_args):
    box["y"] += 40
    return FakeMatch(200, box["y"])
e._find_at = wandering
e._find_now = wandering
start = time.time()
got = e._settled({"image": "x.png", "settleFor": 0.4, "timeout": 1.0},
                 FakeMatch(200, 100))
elapsed = time.time() - start
check(u"안 멈추면 제한시간에 마지막 자리로 진행", got is not None,
      u"%r  %.2fs" % (got, elapsed))
check(u"제한시간을 크게 넘기지 않는다", elapsed < 2.5, u"%.2fs" % elapsed)

# 5) 좁은 창에서 놓쳐도 영역 전체를 다시 본다
e = make_engine()
e._find_at = lambda *a: None                 # 좁은 창에서는 늘 실패
e._find_now = lambda *a: FakeMatch(200, 400)  # 전체 훑기로는 찾는다
got = e._settled({"image": "x.png", "settleFor": 0.3, "timeout": 5},
                 FakeMatch(200, 100))
check(u"좁은 창에서 놓치면 영역 전체를 다시 본다",
      got is not None and got.getY() == 400, u"%r" % (got,))

# 6) _same_spot 은 몇 픽셀 흔들림을 움직임으로 보지 않는다
e = make_engine()
check(u"몇 픽셀 흔들림은 움직임이 아니다",
      e._same_spot(FakeMatch(200, 100), FakeMatch(203, 104)))
check(u"한 항목만큼 밀리면 움직임이다",
      not e._same_spot(FakeMatch(200, 100), FakeMatch(200, 160)))

say(u"")
say(u"=== 아슬아슬한 점수는 움직임을 의심하고 알린다 ===")


class Scored(FakeMatch):
    def __init__(self, x, y, score):
        FakeMatch.__init__(self, x, y)
        self.score = score

    def getScore(self):
        return self.score


def capture_log():
    lines = []
    eng = macro_engine.Engine({"name": u"m", "settings": {}, "steps": []},
                              ".", lambda m: lines.append(m))
    return eng, lines


# 실제 사고의 숫자 그대로: 임계값 0.95, 찍힌 점수 0.9502, 그리고 움직였다
e, lines = capture_log()
e._find_at = lambda *a: Scored(200, 300, 0.95)      # 다른 자리에서 잡힌다
step = {"image": "x.png", "similarity": 0.95}
e._settled(step, Scored(200, 100, 0.9502))
check(u"아슬아슬 + 움직임 -> 경고한다",
      any(u"움직이는 중" in l for l in lines), u"%r" % (lines,))
check(u"settleFor 를 쓰라고 알려 준다",
      any(u"settleFor" in l for l in lines), u"%r" % (lines,))

# 그 자리에 그대로 있으면 조용하다
e, lines = capture_log()
e._find_at = lambda *a: Scored(200, 100, 0.9502)
e._settled({"image": "x.png", "similarity": 0.95}, Scored(200, 100, 0.9502))
check(u"아슬아슬해도 그 자리면 조용하다", lines == [], u"%r" % (lines,))

# 넉넉히 넘긴 매칭은 확인조차 하지 않는다 (시간을 쓰지 않는다)
e, lines = capture_log()
box = {"n": 0}


def counted(*_a):
    box["n"] += 1
    return None
e._find_at = counted
start = time.time()
e._settled({"image": "x.png", "similarity": 0.95}, Scored(200, 100, 0.9857))
elapsed = time.time() - start
check(u"넉넉한 점수는 다시 보지 않는다", box["n"] == 0 and lines == [],
      u"%d회, %r" % (box["n"], lines))
check(u"그래서 시간도 쓰지 않는다", elapsed < 0.1, u"%.3fs" % elapsed)

say(u"")
say(u"=" * 62)
say(u"passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    say(u"실패:")
    for name in FAIL:
        say(u"  - %s" % name)
    sys.exit(1)
say(u"SETTLEPROBE_OK")
sys.exit(0)
