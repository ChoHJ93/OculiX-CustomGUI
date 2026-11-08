# -*- coding: utf-8 -*-
u"""해상도 대응의 실행 쪽 - 창을 재고 템플릿 축소본을 만든다 (Jython 전용).

변환 계산은 graph_model.Transform 에 있다. 편집기(Python 3)도 같은 값을 내야
하기 때문이다. 여기에는 JVM 안에서만 되는 일만 둔다.

`settings.scaling` 이 없는 매크로에서는 이 파일의 어떤 코드도 돌지 않는다.
JNA 와 OpenCV 를 함수 안에서 import 하는 것도 그 때문이다.
"""

import os
import time

from java.awt import GraphicsEnvironment
from java.io import File

from sikuli import Screen

import graph_model

# 창을 잰 값을 이 시간(초) 동안만 다시 쓴다. 노드 하나가 영역과 이미지를 따로
# 물어도 같은 값을 보게 하려는 것이다. 창은 언제든 움직이므로 더 오래 두지 않는다.
MEASURE_TTL = 0.1


class WindowMissing(Exception):
    u"""기준 창을 지금은 찾을 수 없다. 창 기준 좌표를 계산할 수 없다."""
    pass


class ScaleState(object):
    u"""이번 실행의 해상도 변환. 프로세스(실행) 하나에 하나 (PAUSE 와 같다).

    호출된 매크로와 감시 매크로까지 같은 값을 봐야 한다. 생성자로 넘기면
    엔진을 만드는 곳을 전부 고쳐야 하고, 하나만 빠져도 그 매크로만 말없이
    기준 좌표로 돈다.
    """

    def __init__(self):
        self.spec = None
        self.logger = None
        # 테스트 전용. 창이나 화면을 재는 대신 이 값을 쓴다 (RunMacro 인자).
        self.simulate_client = None
        self.simulate_screen = None
        self._reset()

    def _reset(self):
        self._screen_size = None
        self._screen_view = None
        self._client = None
        self._window_view = None
        self._measured_at = None
        self._said_missing = False
        self._reported = set()
        self._last_state = None

    def configure(self, spec):
        self.spec = spec
        self._reset()

    def attach(self, logger):
        u"""로그를 남길 곳을 정하고 시작 줄을 남긴다."""
        self.logger = logger
        if not self.enabled():
            return
        width, height = self.screen_size()
        self._say(u"해상도 대응: 화면 %dx%d (기준 %dx%d), 시스템 DPI %d"
                  % (width, height, self.spec["screen"][0],
                     self.spec["screen"][1], self.system_dpi()))

    def enabled(self):
        return self.spec is not None

    def _say(self, message):
        if self.logger is not None:
            self.logger(message)

    # ------------------------------------------------------------------ 측정

    @staticmethod
    def jvm_scale():
        u"""Windows 배율. JVM 은 DPI 인식 프로세스라 Win32 가 물리값을 준다."""
        device = (GraphicsEnvironment.getLocalGraphicsEnvironment()
                  .getDefaultScreenDevice())
        return device.getDefaultConfiguration().getDefaultTransform().getScaleX()

    def system_dpi(self):
        return int(round(96.0 * self.jvm_scale()))

    def screen_size(self):
        u"""주 모니터의 OculiX 좌표 크기."""
        if self._screen_size is None:
            if self.simulate_screen:
                self._screen_size = tuple(self.simulate_screen)
            else:
                screen = Screen(0)
                self._screen_size = (screen.getW(), screen.getH())
        return self._screen_size

    def screen_rect(self):
        width, height = self.screen_size()
        return [0, 0, width, height]

    def screen_view(self):
        if self._screen_view is None:
            self._screen_view = graph_model.screen_view(self.spec,
                                                        self.screen_size())
        return self._screen_view

    def _measure(self):
        u"""기준 창의 안쪽을 OculiX 좌표로 잰다. 없거나 최소화면 None.

        창 이름은 App 으로 찾지 않는다. `App(title).window()` 는 이 게임을
        찾지 못하고 IndexOutOfBounds 로 죽는다 (실측).

        JNA 의 User32 에는 ClientToScreen 이 없어서 안쪽의 원점은 창 사각형에서
        구한다. 좌우 테두리는 폭이 같고, 안쪽 아래와 창 아래도 그만큼 떨어져
        있다. 제목 표시줄은 위에만 있다.
        """
        if self.simulate_client:
            return [float(v) for v in self.simulate_client]
        from com.sun.jna.platform.win32 import User32, WinDef
        window = self.spec.get("window") or {}
        user32 = User32.INSTANCE
        handle = user32.FindWindow(window.get("class"), window.get("title"))
        if handle is None:
            return None
        inner = WinDef.RECT()
        outer = WinDef.RECT()
        if not user32.GetClientRect(handle, inner):
            return None
        if not user32.GetWindowRect(handle, outer):
            return None
        width = inner.right - inner.left
        height = inner.bottom - inner.top
        if width <= 0 or height <= 0:
            return None
        border = (outer.right - outer.left - width) // 2
        scale = self.jvm_scale()
        return [(outer.left + border) / scale,
                (outer.bottom - border - height) / scale,
                width / scale, height / scale]

    def window_view(self):
        u"""지금 창에 대한 변환. 창이 없으면 None."""
        now = time.time()
        if self._measured_at is not None \
                and now - self._measured_at < MEASURE_TTL:
            return self._window_view
        self._measured_at = now
        client = self._measure()
        if client is None:
            if self._client is not None or not self._said_missing:
                self._say(u"해상도 대응: 기준 창을 찾을 수 없습니다 (%s)"
                          % self._window_name())
            self._said_missing = True
            self._client = None
            self._window_view = None
            self._last_state = None
            return None
        if client != self._client:
            self._client = client
            self._window_view = graph_model.Transform(self.spec["client"],
                                                      client)
            self._report(self._window_view)
        return self._window_view

    def _window_name(self):
        window = self.spec.get("window") or {}
        return window.get("title") or window.get("class") or u"?"

    def _report(self, view):
        # 스냅으로 옮겨 가는 창은 잴 때마다 좌표가 달라진다. 상태가 바뀔 때만 남긴다.
        state = (view.identity, view.size_key() if view.resized else None)
        if state == self._last_state:
            return
        self._last_state = state
        if view.identity:
            if view.drift <= graph_model.ROUNDING_SLACK:
                self._say(u"해상도 대응: 창이 기준과 같은 크기입니다. "
                          u"변환하지 않습니다")
            else:
                self._say(u"해상도 대응: 창이 기준과 최대 %.0fpx 달라 기준과 같은 "
                          u"크기로 봅니다 (현재 %s). 좌표와 이미지는 그대로 쓰고 "
                          u"검색 영역만 넓힙니다" % (view.drift, view.size_key()))
            return
        self._say(u"해상도 대응: %s" % view.describe())
        if view.aspect_drift() > graph_model.ASPECT_WARN:
            self._say(u"해상도 대응: 주의 - 창의 가로세로비가 기준과 %.1f%% "
                      u"다릅니다. 게임 UI 배치가 비례를 벗어나 좌표가 어긋날 수 "
                      u"있습니다" % (view.aspect_drift() * 100))

    def dpi_fix_needed(self, view):
        u"""템플릿의 DPI 기록을 무시하게 해야 하는가.

        OculiX 는 첫 비교에서 못 찾으면 템플릿을 (시스템 DPI / 템플릿 DPI) 배로
        키워 다시 찾는데, 마스크는 키우지 않아서 투명 템플릿이 CvException 으로
        죽는다. DPI 120 템플릿을 96 DPI 환경에서 쓰면 그대로 걸린다 (재현함).
        축소본은 DPI 기록이 없어 96 으로 읽히므로 같은 일이 일어난다.

        기준 환경에서는 건드리지 않는다. 지금 도는 매크로의 동작을 바꾸지 않는다.
        """
        if not self.enabled():
            return False
        if not self.screen_view().identity:
            return True
        return view is not None and view.resized

    # ---------------------------------------------------------------- 이미지

    def image_path(self, base_dir, name, view):
        u"""이번에 쓸 템플릿 파일. 이미지가 아예 없으면 None."""
        found = graph_model.locate_image(base_dir, name, self.screen_size())
        if found is None:
            return None
        path = found["path"]
        if view is None or not view.scales_content:
            self._report_image(name, found)
            return path
        if found["capture"]:
            # 찍을 때의 창 기준으로 다시 잰다. 그 창과 같으면 그대로 쓴다.
            if found["client"] is None:
                self._report_image(name, found)
                return path
            view = graph_model.Transform(found["client"], view.current)
        if not view.resized:
            self._report_image(name, found)
            return path
        return self._scaled_copy(path, base_dir, name, view)

    def _report_image(self, name, found):
        u"""다시 찍은 이미지를 쓴다는 것을 이미지마다 한 번 남긴다."""
        if not found["capture"] or name in self._reported:
            return
        self._reported.add(name)
        self._say(u"    이미지 %s: %s 의 것을 씁니다" % (
            name, os.path.basename(os.path.dirname(found["path"]))))

    def _scaled_copy(self, source, base_dir, name, view):
        u"""축소본을 돌려준다. 없거나 원본과 다르면 새로 만든다.

        수정 시각을 원본과 같게 맞춰 두고 같은지 비교한다. 더 새로운지만 보면
        원본을 옛 파일로 되돌렸을 때 낡은 축소본이 남는다.

        파일은 Java 로 읽고 쓴다. OpenCV 의 imread/imwrite 는 Windows 에서
        한글 경로를 열지 못한다.
        """
        target = graph_model.scaled_image_path(base_dir, name, view)
        target_file = File(target)
        source_file = File(source)
        stamp = source_file.lastModified()
        if target_file.isFile() and target_file.lastModified() == stamp:
            return target

        from javax.imageio import ImageIO
        from org.opencv.core import Mat, Size
        from org.opencv.imgproc import Imgproc
        from org.sikuli.support import Commons

        image = ImageIO.read(source_file)
        if image is None:
            return source
        width, height = view.image_size(image.getWidth(), image.getHeight())
        small = Mat()
        Imgproc.resize(Commons.makeMat(image, False), small, Size(width, height),
                       0, 0, Imgproc.INTER_CUBIC)
        folder = os.path.dirname(target)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        ImageIO.write(Commons.getBufferedImage(small), "png", target_file)
        target_file.setLastModified(stamp)
        self._say(u"    이미지 %s: 축소본을 만들었습니다 %dx%d -> %dx%d"
                  % (name, image.getWidth(), image.getHeight(), width, height))
        return target


SCALE = ScaleState()
