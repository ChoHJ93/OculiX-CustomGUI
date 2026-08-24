# -*- coding: utf-8 -*-
# MyFirstMacro.sikuli - 직접 매크로를 만들어 볼 때 복사해서 시작하는 템플릿.
#
# 이 파일 그대로 실행하면 "화면 읽기"만 하고 아무것도 클릭하지 않는다.
# 안전하게 동작을 확인한 뒤 아래 main() 안을 원하는 작업으로 바꿔 쓰면 된다.
#
# 실행:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar -r D:\Programming\Oculix-Automation\Scripts\Tests\MyFirstMacro.sikuli -c

from sikuli import *
import sys
import os
import time

# 공용 모듈 경로 등록 (pixel_util 등)
sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import pixel_util


# ---------------------------------------------------------------- 설정

# 검색 범위. 전체 화면 대신 좁은 영역을 쓰는 것이 빠르고 오탐도 적다.
# 처음에는 주 모니터 전체로 시작하고, 대상 위치가 정해지면 좁혀라.
SEARCH = Screen(0)

# 이미지 매칭 기본 정확도. 0.90에서 시작해 실제 점수를 보고 조정한다.
SIMILARITY = 0.90

# 기본 대기 시간(초). 무한 대기는 만들지 않는다.
TIMEOUT = 10


# ---------------------------------------------------------------- 헬퍼

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg))


def find_image(image, timeout=TIMEOUT, similarity=SIMILARITY, region=None):
    """이미지를 찾아 Match를 반환. 못 찾으면 None.

    실패해도 예외를 던지지 않으므로 호출부에서 if로 흐름을 제어할 수 있다.
    """
    area = region
    if area is None:
        area = SEARCH
    pattern = Pattern(image).similar(similarity)
    match = area.exists(pattern, timeout)
    if match is None:
        log("NOT FOUND: %s (%.2f, %ds 대기)" % (image, similarity, timeout))
        return None
    log("found %s score=%.4f at (%d,%d)" % (
        image, match.getScore(), match.getX(), match.getY()))
    return match


def click_image(image, timeout=TIMEOUT, similarity=SIMILARITY, region=None):
    """이미지를 찾아 클릭. 성공하면 True."""
    match = find_image(image, timeout, similarity, region)
    if match is None:
        return False
    click(match)
    return True


def wait_image_gone(image, timeout=TIMEOUT, similarity=SIMILARITY):
    """이미지가 사라질 때까지 대기. 사라지면 True."""
    gone = waitVanish(Pattern(image).similar(similarity), timeout)
    if not gone:
        log("STILL THERE: %s (%ds 후에도 남아 있음)" % (image, timeout))
    return bool(gone)


def snap(region, filename):
    """영역을 캡처해 이 번들 안에 저장하고 경로를 반환.

    템플릿 이미지를 코드로 만들 때 쓴다. IDE 캡처보다 재현성이 좋다.
    """
    import shutil
    tmp = capture(region)
    dest = os.path.join(getBundlePath(), filename)
    shutil.copyfile(tmp, dest)
    log("captured %s (%d bytes)" % (filename, os.path.getsize(dest)))
    return dest


# ---------------------------------------------------------------- 작업 단계
# 실제 매크로는 이런 식으로 단계를 함수로 쪼갠다.
# 각 함수는 성공 여부를 True/False로 돌려주고, 실패하면 상위에서 중단한다.

def step_check_environment():
    """화면을 읽을 수 있는지만 확인한다. 아무것도 클릭하지 않는다."""
    log("screens: %d" % Screen.getNumberScreens())
    log("Screen(0): %s" % Screen(0).getBounds())

    # 화면 한가운데 픽셀 색을 읽어본다 - 읽기 경로가 살아 있는지 확인
    b = Screen(0).getBounds()
    cx = b.x + b.width / 2
    cy = b.y + b.height / 2
    rgb = pixel_util.get_pixel_rgb(cx, cy)
    log("center pixel (%d,%d) = %s" % (cx, cy, rgb))
    return True


def step_do_work():
    """여기를 실제 작업으로 바꿔 쓴다.

    아래는 패턴 예시다. 이미지 파일이 없으므로 지금은 건너뛴다.
    """
    # if not click_image("start.png"):
    #     return False
    # if not wait_image_gone("loading.png", timeout=30):
    #     return False
    # if not click_image("confirm.png", similarity=0.88):
    #     return False
    log("작업 단계 - 여기에 내용을 채워 넣으세요")
    return True


# ---------------------------------------------------------------- 진입점

def main():
    log("=== 매크로 시작 ===")

    if not step_check_environment():
        log("환경 확인 실패")
        return 1

    if not step_do_work():
        log("작업 실패")
        return 1

    log("=== 정상 종료 ===")
    return 0


main()
