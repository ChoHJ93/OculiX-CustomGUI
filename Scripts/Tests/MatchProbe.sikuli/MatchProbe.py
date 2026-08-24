# -*- coding: utf-8 -*-
# MatchProbe.sikuli - 템플릿이 지금 화면 어디에 얼마나 닮은 곳으로 걸리는지 본다.
#
# "화면에 없는데 찾았다고 나온다" 를 가릴 때 쓴다. 어떤 점수로 어디에 걸렸는지
# 알려주고, 그 자리를 잘라 PNG 로 남겨 눈으로 대조할 수 있게 한다.
# 입력을 주입하지 않는다. 화면을 읽기만 하므로 언제 돌려도 안전하다.
#
# 사용:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Tests\MatchProbe.sikuli -c ^
#        -- <이미지경로> [잘라낸그림저장경로] [x,y,w,h]
#
# 마지막 인자로 영역을 주면 그 안에서만 찾는다. 검색 범위를 좁히면 오탐이
# 사라지는지 확인할 때 쓴다.

from sikuli import *
import sys
import os
import shutil


def say(message):
    if isinstance(message, unicode):
        try:
            message = message.encode("utf-8")
        except Exception:
            message = message.encode("ascii", "replace")
    print(message)


if len(sys.argv) < 2:
    say(u"usage: -- <이미지경로> [잘라낸그림저장경로]")
    sys.exit(2)

image = sys.argv[1]
crop_dest = sys.argv[2] if len(sys.argv) > 2 else None

if not os.path.isfile(image):
    say(u"이미지를 찾을 수 없습니다: %s" % image)
    sys.exit(2)

screen = Screen(0)
area = screen
if len(sys.argv) > 3 and sys.argv[3]:
    x, y, w, h = [int(v) for v in sys.argv[3].split(",")]
    area = Region(x, y, w, h)
say(u"검색 범위: %s" % area)
say(u"템플릿: %s" % image)

# exists 는 임계값 이상 중 **가장 닮은** 자리를 준다. 낮게 잡고 한 번 부르면
# 최고 점수를 그대로 알 수 있다. timeout 0 이라 한 번만 훑는다.
best = area.exists(Pattern(image).similar(0.50), 0)
if best is None:
    say(u"BEST=none  (0.50 이상 닮은 곳이 아예 없음)")
else:
    say(u"BEST=%.4f at (%d,%d) %dx%d"
        % (best.getScore(), best.getX(), best.getY(),
           best.getW(), best.getH()))

say(u"--- 임계값별 판정 ---")
for threshold in (0.99, 0.97, 0.95, 0.93, 0.90, 0.85, 0.80, 0.70):
    hit = area.exists(Pattern(image).similar(threshold), 0)
    say(u"  similar(%.2f) -> %s" % (
        threshold,
        (u"찾음 score=%.4f at (%d,%d)"
         % (hit.getScore(), hit.getX(), hit.getY())) if hit else u"없음"))

if best is not None and crop_dest:
    # 실제로 무엇에 걸렸는지 눈으로 보라고 그 자리를 잘라 둔다.
    tmp = capture(Region(best.getX(), best.getY(), best.getW(), best.getH()))
    if tmp:
        shutil.copyfile(tmp, crop_dest)
        say(u"CROP=%s" % crop_dest)
