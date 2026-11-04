# -*- coding: utf-8 -*-
# SettleLive.sikuli - 진짜 움직이는 대상을 놓고 "멈춤 확인"(settleFor)을 검증한다.
#
# SettleProbe 는 찾기 함수를 가짜로 바꿔 끼워 로직만 본다. 이쪽은 실제 화면
# 픽셀을 읽는 경로(_find / _find_at / _find_now)까지 지난다. 좌표를 다루는
# 실수는 가짜 데이터로는 드러나지 않기 때문에 둘 다 필요하다.
#
# **화면에 작은 창을 하나 띄웠다가 닫는다.** 입력은 주입하지 않는다.
# 템플릿도 그 창에서 직접 잘라 쓰므로 준비물이 없다.
#
# 실행:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Tests\SettleLive.sikuli -c

from sikuli import *
import sys
import os
import shutil
import tempfile
import time

sys.path.append("D:\Programming\Oculix-Automation\Scripts\Common")
import macro_engine

from javax.swing import JFrame, JPanel
from java.awt import Color, Dimension, Font
from java.lang import Thread as JThread, Runnable

PASS = []
FAIL = []

WIN_X, WIN_Y, WIN_W, WIN_H = 120, 120, 380, 640
MARK_X, MARK_Y = 60, 40          # 창 안에서 표식을 그리는 자리
MARK_W, MARK_H = 200, 70
TRAVEL = 360                     # 아래로 밀어 내릴 거리(픽셀)


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


class Board(JPanel):
    """표식 하나를 세로로 밀어 내리는 판. 목록 스크롤을 흉내낸다."""

    def __init__(self):
        self.oy = 0
        self.setBackground(Color(13, 14, 20))

    def paintComponent(self, g):
        g.setColor(Color(13, 14, 20))
        g.fillRect(0, 0, self.getWidth(), self.getHeight())
        # 단색은 화면의 다른 같은 색과 매칭된다. 글자와 테두리로 특징을 준다.
        g.setColor(Color(106, 134, 255))
        g.fillRect(MARK_X, MARK_Y + self.oy, MARK_W, MARK_H)
        g.setColor(Color(255, 255, 255))
        g.setFont(Font("Arial", Font.BOLD, 26))
        g.drawString("TARGET", MARK_X + 34, MARK_Y + self.oy + 46)
        g.drawRect(MARK_X + 6, MARK_Y + self.oy + 6, MARK_W - 12, MARK_H - 12)


work = tempfile.mkdtemp(prefix="settlelive_")
board = Board()
board.setPreferredSize(Dimension(WIN_W, WIN_H))
frame = JFrame("SettleLive")
frame.setUndecorated(True)
frame.getContentPane().add(board)
frame.pack()
frame.setLocation(WIN_X, WIN_Y)
frame.setAlwaysOnTop(True)
frame.setVisible(True)
time.sleep(1.0)

try:
    say(u"=== 움직이는 대상을 집을 때 어디를 집는가 ===")

    # 지금 화면에 보이는 표식을 그대로 잘라 템플릿으로 쓴다
    shot = capture(Region(WIN_X + MARK_X, WIN_Y + MARK_Y, MARK_W, MARK_H))
    template = os.path.join(work, "target.png")
    shutil.copyfile(shot, template)

    engine = macro_engine.Engine({"name": u"live", "settings": {}, "steps": []},
                                 work, lambda m: say(u"        " + m))
    step = {"image": template, "similarity": 0.95, "timeout": 15,
            "region": [WIN_X, WIN_Y, WIN_W, WIN_H], "settleFor": 0.5}

    check(u"멈춰 있을 때 찾는다", engine._find_now(step) is not None)

    # 배경에서 표식을 아래로 밀어 내린다 (약 4초)
    class Scroll(Runnable):
        def run(self):
            for i in range(TRAVEL // 10 + 1):
                board.oy = i * 10
                board.repaint()
                JThread.sleep(100)
    JThread(Scroll()).start()
    time.sleep(0.3)

    first = engine._find(step)
    check(u"움직이는 중에도 찾기는 된다", first is not None)

    settled = engine._settled(step, first, u"")
    check(u"멈출 때까지 기다린다", settled is not None)

    time.sleep(0.6)
    final = engine._find_now(step)
    check(u"멈춘 뒤에도 찾힌다", final is not None)

    if first and settled and final:
        stale = abs(first.getY() - final.getY())
        fresh = abs(settled.getY() - final.getY())
        check(u"멈춤 확인을 하면 실제 자리를 집는다", fresh <= 12,
              u"실제와 %d px 차이" % fresh)
        # 이 값이 작으면 시험 자체가 무의미하다 (움직이지 않은 것)
        check(u"멈춤 확인이 없었다면 크게 빗나갔다", stale > 100,
              u"처음 본 자리는 실제와 %d px 차이" % stale)
        say(u"")
        say(u"  같은 모양의 항목이 %d px 간격으로 늘어선 목록이라면, "
            u"%d px 어긋남은 옆 항목을 누른다는 뜻이다." % (fresh + 100, stale))
finally:
    frame.dispose()
    shutil.rmtree(work, True)

say(u"")
say(u"=" * 62)
say(u"passed %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
if FAIL:
    say(u"실패:")
    for name in FAIL:
        say(u"  - %s" % name)
    sys.exit(1)
say(u"SETTLELIVE_OK")
sys.exit(0)
