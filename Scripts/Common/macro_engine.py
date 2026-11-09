# -*- coding: utf-8 -*-
"""macro_engine - executes a JSON macro definition on top of OculiX.

Why JSON instead of generated code: a GUI editor has to be able to re-open and
modify a macro. Generated Python cannot be reliably parsed back into a step
list, so the macro is stored as data and interpreted by this engine. The GUI
edits the data; this file is the only thing that ever touches the OculiX API.

Safety rules enforced by the engine itself, not left to the macro author:
  * every image/colour wait has a timeout, defaulted if omitted
  * `while` loops REQUIRE a bounded maxIterations and are hard-capped
  * a failing step aborts the run unless it opts into "onFail": "continue"
"""

# OculiX exposes its CLASSES as module attributes, but its global action
# functions (click, type, mouseDown, ...) are injected only into the namespace
# of the running .sikuli script - they are NOT attributes of the sikuli module.
# An imported module like this one therefore cannot call them, and doing so
# fails at runtime with "NameError: global name 'click' is not defined".
#
# Every action here goes through Screen/Region methods instead, which are real
# instance methods and always available. Verified with Scripts/Tests/MethodProbe.
from sikuli import Region, Screen, Pattern, Location
from sikuli import Button, Key, KeyModifier, Settings, OCR

# 클릭 뒤 커서가 실제로 그 자리에 갔는지 확인하는 데 쓴다.
from java.awt import MouseInfo

# Jython 에서 Java 예외는 파이썬 Exception 으로 잡히지 않는다.
# 잡지 않으면 단계 하나가 실패하는 대신 매크로 전체가 죽는다.
from java.lang import Throwable

import json
import os
import time

import pixel_util

from scale_runtime import SCALE, WindowMissing


HARD_ITERATION_CAP = 10000   # last-resort guard against a runaway macro

# 대상이 멈췄는지 확인할 때 두 번 보는 사이의 간격(초).
# 너무 짧으면 스크롤이 느린 UI 에서 "멈췄다"고 잘못 볼 수 있고,
# 너무 길면 멀쩡한 화면에서 클릭이 그만큼 늦어진다.
SETTLE_GAP = 0.2

# 감시가 걸려 있을 때 대기를 이만큼(초)씩 잘라서 기다린다. 자른 사이마다
# 감시를 확인한다. 실제 확인 주기는 handlerInterval 이 정한다.
WATCH_SLICE = 0.5

# 일시정지 중에 재개 요청을 확인하는 간격(초).
PAUSE_POLL = 0.1

# 찾은 자리를 다시 확인할 때 사각형을 이만큼 넓혀서 본다. 몇 픽셀 흔들리는
# 렌더링까지 "움직였다"고 보지 않으려는 여유다.
SETTLE_GROW = 8

# 점수가 임계값을 이만큼도 못 넘기면 "아슬아슬하다"고 보고 움직임을 의심한다.
# 움직이는 중에 찍힌 화면은 흐릿해서 점수가 임계값 언저리로 떨어진다.
MARGINAL_SCORE = 0.02

# 실패했을 때 "어디까지 갔는지"를 남기는 파일. 편집기가 읽어 '이어서 실행'에 쓴다.
# Logs 아래라 git 추적 대상이 아니다(.gitignore).
RESUME_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Logs", "resume.json")

# WIN / CMD / META 는 OculiX에서 값이 모두 4로 같다.
_MODIFIERS = {
    "CTRL": KeyModifier.CTRL,
    "SHIFT": KeyModifier.SHIFT,
    "ALT": KeyModifier.ALT,
    "ALTGR": KeyModifier.ALTGR,
    "META": KeyModifier.META,
    "WIN": KeyModifier.META,
    "CMD": KeyModifier.META,
}

_BUTTONS = {
    "LEFT": Button.LEFT,
    "MIDDLE": Button.MIDDLE,
    "RIGHT": Button.RIGHT,
}


class MacroError(Exception):
    pass


class _Break(Exception):
    """Internal control-flow signal for the `break` step."""
    pass


class TextHit(object):
    u"""OCR 로 찾아낸 글자의 위치와 실제로 읽힌 값.

    Match 를 그대로 쓸 수 없어서 따로 둔다. 한글은 OCR 이 음절마다 조각을
    내놓기 때문에 ("설정" -> "설", "정") 질의가 걸친 조각들을 합쳐 새 사각형을
    만들어야 하고, 그렇게 만든 것은 Match 가 아니라 Region 이다.

    region 은 화면 절대 좌표이고, 클릭하면 그 중앙을 누른다.
    """

    def __init__(self, region, text):
        self.region = region
        self.text = text


class PauseGate(object):
    u"""편집기의 일시정지 요청을 받는 문. 프로세스(실행) 하나에 하나.

    편집기는 별도 프로세스라 신호는 파일 하나로 주고받는다 - 파일이 있으면
    멈추고, 지우면 간다. 경로는 실행 인자로 받는다(--pause-file). 고정 경로로
    두면 남은 파일 하나 때문에 명령줄 실행이나 테스트가 영원히 멈출 수 있다.
    경로를 받지 않은 실행은 아무것도 확인하지 않는다.

    입력 장치를 쓰는 동작 도중에는 멈추지 않는다. 노드 사이와 대기 중에
    엔진이 스스로 확인할 때만 멈추므로, 진행 중인 클릭/입력/드래그는 끝난다.
    """

    def __init__(self):
        self.path = None
        self.total = 0.0            # 지금까지 멈춰 있던 시간(초)
        self.held = set()           # mouseDown 으로 누른 채인 버튼

    def configure(self, path):
        self.path = path or None
        self.total = 0.0
        self.held = set()

    def enabled(self):
        return self.path is not None

    def hold(self, engine, where):
        """요청이 있으면 풀릴 때까지 멈춘다. 멈춰 있던 시간(초)을 준다."""
        if self.path is None or not os.path.exists(self.path):
            return 0.0
        started = time.time()
        engine.log(u"%s 멈췄습니다 - %s" % (graph_model.PAUSED_MARK, where))
        if self.held:
            # 일부러 떼지 않는다. 드래그 도중이면 떼는 순간 엉뚱한 곳에 놓인다.
            engine.log(u"%s 주의: 마우스 버튼이 눌린 채입니다 (%s). 재개하면 "
                       u"그대로 이어 갑니다. 그동안 마우스를 움직이면 "
                       u"드래그가 어긋납니다"
                       % (graph_model.PAUSED_MARK,
                          u", ".join(sorted(self.held))))
        while os.path.exists(self.path):
            time.sleep(PAUSE_POLL)
        spent = time.time() - started
        self.total += spent
        engine.log(u"%s %.1f초 멈춰 있었습니다. 이어서 진행합니다"
                   % (graph_model.RESUMED_MARK, spent))
        return spent


PAUSE = PauseGate()


class Engine(object):

    def __init__(self, macro, base_dir, logger=None, params=None):
        self.macro = macro
        self.base_dir = base_dir
        self.log = logger or self._default_logger
        # 이 실행에서 쓸 매개변수 값. 호출될 때마다 새로 묶이므로 인스턴스마다
        # 따로 갖는다. 같은 매크로를 다른 값으로 여러 번 불러도 섞이지 않는다.
        self.params = dict(params) if params else {}

        settings = macro.get("settings", {})
        self.screen_index = int(settings.get("screen", 0))
        self.default_similarity = float(settings.get("defaultSimilarity", 0.90))
        self.default_timeout = float(settings.get("defaultTimeout", 10))
        self.step_delay = float(settings.get("stepDelay", 0))
        # 이미지를 찾은 자리가 이만큼(초) 멈춰 있어야 집는다. 0 이면 확인하지
        # 않는다(예전과 같은 동작). 스크롤이 끝나기 전에 집는 사고를 막는 값이다.
        self.default_settle = float(settings.get("defaultSettle", 0))

        self.screen = Screen(self.screen_index)
        # 기본 검색 영역. 해상도 대응을 쓰면 창이 뜬 뒤에야 계산할 수 있으므로
        # 쓸 때 Region 으로 만든다.
        self.search_region = settings.get("searchRegion") or None
        if self.search_region and len(self.search_region) != 4:
            raise MacroError("region must be [x, y, w, h], got %r"
                             % (self.search_region,))
        # 이 매크로 좌표의 기준. 노드의 `space` 가 있으면 그것이 우선한다.
        self.space = macro.get("space") or graph_model.SPACE_WINDOW

        self.stats = {"steps": 0, "failed": 0}

        # 글자 인식 언어. 설치된 언어만 쓸 수 있다 (기본 eng).
        self._language = u"eng"
        self._default_language = settings.get("ocrLanguage") or u"eng"
        if self._default_language != u"eng":
            self._set_language(self._default_language)

        # Tesseract 페이지 분할 모드. 기본값 3(자동)은 UI 화면에 맞지 않는다.
        # 같은 창에서 재보면 3은 9칸 중 5칸만 맞혔고 (라벨에 여백을 조금만 둬도
        # 아예 빈 결과가 나왔다), 11(성긴 글자)은 9/9 에 더 빨랐다.
        # 영문 대상에서는 3/4/11 이 모두 8칸 중 7칸으로 같았다.
        self._psm = settings.get("ocrPsm", 11)
        self._set_psm(self._psm)

        # 감시 매크로 관리자 (WatchManager). 감시가 걸린 실행에서만 채워진다.
        self.watch = None

    # ------------------------------------------------------------- utilities

    def _default_logger(self, msg):
        # Jython's stdout defaults to ascii, so Korean labels raise
        # UnicodeEncodeError unless we encode explicitly.
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        if isinstance(line, unicode):
            try:
                line = line.encode("utf-8")
            except Exception:
                line = line.encode("ascii", "replace")
        print(line)

    def _view(self, step):
        """이 단계의 좌표에 쓸 변환. 해상도 대응을 안 쓰면 None.

        창 기준인데 창이 없으면 WindowMissing. 좌표를 계산할 수 없다.
        """
        if not SCALE.enabled():
            return None
        if (step.get("space") or self.space) == graph_model.SPACE_SCREEN:
            return SCALE.screen_view()
        view = SCALE.window_view()
        if view is None:
            raise WindowMissing(u"기준 창을 찾을 수 없어 좌표를 계산하지 "
                                u"못했습니다")
        return view

    def _map_point(self, point, step):
        """기준 좌표를 지금 화면의 좌표로. (x, y)"""
        view = self._view(step)
        if view is None:
            return int(point[0]), int(point[1])
        mapped = view.point(point)
        return mapped[0], mapped[1]

    def _make_region(self, spec, step):
        if spec is None:
            spec = self.search_region
            if spec is None:
                return self.screen
        if len(spec) != 4:
            raise MacroError("region must be [x, y, w, h], got %r" % (spec,))
        view = self._view(step)
        if view is not None:
            spec = view.region(spec, SCALE.screen_rect())
        return Region(int(spec[0]), int(spec[1]), int(spec[2]), int(spec[3]))

    def _image_path(self, name, view=None):
        """Images live next to the macro's .json file, like a .sikuli bundle."""
        if SCALE.enabled():
            path = SCALE.image_path(self.base_dir, name, view)
            if path is None:
                raise MacroError("image not found: %s"
                                 % os.path.join(self.base_dir, name))
            return path
        path = name
        if not os.path.isabs(path):
            path = os.path.join(self.base_dir, name)
        if not os.path.exists(path):
            raise MacroError("image not found: %s" % path)
        return path

    def _pattern(self, step):
        image = step.get("image")
        if not image:
            raise MacroError("step %r requires 'image'" % step.get("type"))
        similarity = float(step.get("similarity", self.default_similarity))
        view = self._view(step)
        pattern = Pattern(self._image_path(image, view)).similar(similarity)
        offset = step.get("targetOffset")
        if offset:
            if view is not None:
                offset = view.offset(offset)
            pattern = pattern.targetOffset(int(offset[0]), int(offset[1]))
        if SCALE.dpi_fix_needed(view):
            pattern.getImage().setCaptureDpi(SCALE.system_dpi())
        return pattern

    def _timeout(self, step):
        return float(step.get("timeout", self.default_timeout))

    def _pointer(self):
        try:
            p = MouseInfo.getPointerInfo().getLocation()
            return int(p.x), int(p.y)
        except Exception:
            return None

    def _verify_pointer(self, expected, action):
        """클릭/이동 뒤 커서가 정말 그 자리에 갔는지 확인한다.

        입력이 OS 수준에서 막히면 OculiX 로그에는 'CLICK on ...' 이 그대로
        찍히지만 커서는 꼼짝하지 않는다. 조용히 실패하면 원인을 찾기 어려우므로
        여기서 명시적으로 알린다.
        """
        if expected is None:
            return
        actual = self._pointer()
        if actual is None:
            return
        dx = abs(actual[0] - expected[0])
        dy = abs(actual[1] - expected[1])
        if dx <= 3 and dy <= 3:
            return
        self.log(u"    !! %s 는 보냈지만 커서가 (%d,%d) 에 있습니다 "
                 u"(기대 (%d,%d))." % (action, actual[0], actual[1],
                                       expected[0], expected[1]))
        self.log(u"       입력이 전달되지 않았을 수 있습니다 - 안티치트, "
                 u"화면보호기, 관리자 권한으로 뜬 창, 원격 데스크톱 등을 확인하세요.")

    @staticmethod
    def _expected_point(target):
        """클릭 대상이 가리키는 화면 좌표. 알 수 없으면 None."""
        try:
            spot = target.getTarget()
        except Exception:
            try:
                spot = target
            except Exception:
                return None
        try:
            return int(spot.getX()), int(spot.getY())
        except Exception:
            return None

    # ------------------------------------------------------------- 감시

    def _sliced(self):
        """대기를 잘라서 기다려야 하는가.

        자른 사이마다 감시와 일시정지를 확인한다. 해상도 대응을 쓰면 창 크기도
        다시 잰다. 모두 해당 없으면(명령줄 실행에 감시도 없는 경우) 예전처럼
        한 번에 기다린다.
        """
        return (PAUSE.enabled() or SCALE.enabled()
                or (self.watch is not None and self.watch.active()))

    def _wait_tick(self):
        """대기 중의 끼어들기를 처리한다. 메인이 멈춰 있던 시간(초)을 준다.

        일시정지 요청이 있으면 멈추고, 감시를 돌 때가 됐으면 돈다. 기다리는
        노드는 이 시간을 제한시간에 더한다 - 메인의 시계는 멈춘 것으로 본다.
        팝업 하나 닫는 사이나 사용자가 멈춘 사이에 대기가 시간 초과로
        실패하면 안 된다.

        감시 쪽에서 멈춘 시간을 따로 재는 이유: 감시 조건을 확인하는 도중에
        일시정지가 걸리면 그 바퀴는 "걸린 것 없음"이라 tick 이 0 을 준다.
        그것만 믿으면 멈춘 시간이 고스란히 제한시간에서 깎인다.
        """
        paused = PAUSE.hold(self, u"대기 중")
        if self.watch is None:
            return paused
        before = PAUSE.total
        spent = self.watch.tick(self)
        return paused + max(spent, PAUSE.total - before)

    def _pause_point(self, step):
        """노드를 시작하기 직전. 여기서 멈추면 그 노드는 아직 실행 전이다."""
        PAUSE.hold(self, u"다음 노드 실행 전: %s (%s)"
                   % (self._name(step), step.get("id") or u"-"))

    def _watch_node_start(self):
        """노드 하나를 시작하기 직전. 메인이 한 걸음 나아갔다고 알리고 확인한다."""
        if self.watch is None:
            return
        self.watch.progress += 1
        self.watch.tick(self)

    def _watched(self, timeout, attempt):
        """`attempt(초)` 를 제한시간까지 되풀이하며 사이사이 감시를 확인한다.

        attempt 는 찾으면 결과를, 못 찾으면 None 을 돌려줘야 한다.
        끼어들 것이 없으면 예전처럼 한 번에 다 기다린다 (_sliced).
        """
        if not self._sliced():
            return attempt(timeout)
        deadline = time.time() + float(timeout)
        while True:
            deadline += self._wait_tick()
            remaining = deadline - time.time()
            result = attempt(max(0.0, min(WATCH_SLICE, remaining)))
            if result is not None:
                return result
            if time.time() >= deadline:
                return None

    def _reapply_ocr(self):
        """글자 인식 설정을 이 엔진 것으로 되돌린다.

        언어와 psm 은 프로세스 전체에 하나뿐이라, 감시 매크로가 자기 설정으로
        바꿔 놓으면 메인의 다음 인식이 엉뚱한 설정으로 돈다.
        """
        self._set_psm(self._psm)
        try:
            Settings.OcrLanguage = self._language
            OCR.globalOptions().language(self._language)
        except (Exception, Throwable):
            pass

    def _find(self, step):
        """Locate the step's image. Returns Match or None - never raises."""
        if SCALE.enabled():
            return self._watched(self._timeout(step),
                                 lambda seconds: self._look(step, seconds))
        region = self._make_region(step.get("region"), step)
        pattern = self._pattern(step)
        return self._watched(self._timeout(step),
                             lambda seconds: region.exists(pattern, seconds))

    def _look(self, step, seconds):
        """창을 새로 재서 한 번 찾는다. 창이 없으면 그만큼 기다리고 None.

        대기 조각마다 다시 계산한다. 창은 스냅되기 전과 뒤의 크기가 다르고,
        기다리는 도중에도 움직일 수 있다.
        """
        try:
            region = self._make_region(step.get("region"), step)
            pattern = self._pattern(step)
        except WindowMissing:
            time.sleep(seconds)
            return None
        return region.exists(pattern, seconds)

    def _find_now(self, step):
        """지금 한 번만 훑는다. 기다리지 않는다."""
        if SCALE.enabled():
            return self._look(step, 0)
        region = self._make_region(step.get("region"), step)
        return region.exists(self._pattern(step), 0)

    def _find_at(self, step, match):
        """방금 찾은 자리 근처만 다시 본다.

        전체 영역을 훑지 않으므로 거의 공짜다. 대상이 그대로 있는지
        확인하는 용도다.
        """
        # 화면 밖으로 나가지 않게 자른다. 목록 맨 위/맨 아래 항목이면
        # 넓힌 사각형이 음수 좌표가 된다.
        x = max(0, match.getX() - SETTLE_GROW)
        y = max(0, match.getY() - SETTLE_GROW)
        area = Region(x, y,
                      match.getW() + (match.getX() - x) + SETTLE_GROW,
                      match.getH() + (match.getY() - y) + SETTLE_GROW)
        probe = dict(step)
        probe.pop("region", None)          # 좁힌 영역이 이미 검색 범위다
        return area.exists(self._pattern(probe), 0)

    @staticmethod
    def _same_spot(a, b, slack=SETTLE_GROW):
        return (abs(a.getX() - b.getX()) <= slack
                and abs(a.getY() - b.getY()) <= slack)

    def _warn_if_marginal(self, step, match, head=u""):
        """점수가 임계값에 아슬아슬하면 움직이는 중인지 확인하고 알린다.

        움직이는 중에 찍힌 화면은 흐릿해서 점수가 뚝 떨어진다. 실측한 사고에서
        멈춰 있을 때는 0.968~0.989 로 찾히던 버튼이, 목록이 스크롤하는 동안에는
        0.9502 로 찍혔다 (임계값 0.95 를 겨우 넘겼다). 세로로 16px 흔들린
        이미지를 만들어 재 보면 0.9508 로, 관측값과 같다.

        그래서 **아슬아슬한 점수**를 움직임의 신호로 본다. 넉넉히 넘긴 매칭은
        확인하지 않으므로, 멀쩡히 도는 매크로에는 시간이 들지 않는다.

        고치지는 않는다 - 알리기만 한다. 실제로 멈추기를 기다리는 것은
        settleFor 를 준 단계의 몫이다.
        """
        threshold = float(step.get("similarity", self.default_similarity))
        try:
            score = match.getScore()
        except Exception:
            return
        if score - threshold > MARGINAL_SCORE:
            return                       # 넉넉히 넘겼다. 볼 것 없다.
        time.sleep(SETTLE_GAP)
        again = self._find_at(step, match)
        if again is not None and self._same_spot(match, again):
            return                       # 그 자리에 그대로 있다
        self.log(u"    %s주의: 점수가 %.4f 로 기준(%.2f)에 아슬아슬하고 "
                 u"대상이 그 자리에 없습니다. 화면이 움직이는 중일 수 있습니다 - "
                 u"지금 누르면 마우스가 도착할 때쯤 다른 것이 그 자리에 옵니다. "
                 u"'멈춤 확인(settleFor)' 을 주세요" % (head, score, threshold))

    def _settled(self, step, match, head=u""):
        """찾은 자리가 멈춰 있는지 확인한다. 움직이는 중이면 멈출 때까지 기다린다.

        왜 필요한가: 찾은 순간과 실제로 누르는 순간 사이에 시간이 있다.
        OculiX 기본값 `Settings.MoveMouseDelay` 만 해도 0.5초다. 그동안
        목록이 스크롤을 마저 하면, 마우스가 도착했을 때 그 자리에 있는 것은
        아까 찾은 항목이 아니라 **바로 옆 항목**이다. 같은 모양의 버튼이
        세로로 늘어선 목록에서 간헐적으로 엉뚱한 버튼을 누르게 된다.

        `settleFor` (초) 를 준 단계에서만 확인한다. 0 이면 그대로 돌려준다 -
        멀쩡히 도는 매크로의 속도를 말없이 늦추지 않으려는 것이다.
        """
        hold = float(step.get("settleFor", self.default_settle))
        if match is None:
            return match
        if hold <= 0:
            self._warn_if_marginal(step, match, head)
            return match

        limit = time.time() + self._timeout(step)
        steady_since = time.time()
        moved = False
        while True:
            spent = self._wait_tick()
            if spent:
                # 감시나 사용자가 화면을 건드렸다. 멈춤 확인을 처음부터 다시 한다.
                limit += spent
                steady_since = time.time()
            time.sleep(SETTLE_GAP)
            again = self._find_at(step, match)
            if again is None:
                # 좁은 창을 벗어났다. 영역 전체를 한 번 더 본다.
                again = self._find_now(step)
            if again is None:
                self.log(u"    %s대상이 잠깐 사라졌습니다. 다시 봅니다" % head)
            elif self._same_spot(match, again):
                match = again
                if time.time() - steady_since >= hold:
                    if moved:
                        self.log(u"    %s대상이 (%d,%d) 에서 멈췄습니다"
                                 % (head, match.getX(), match.getY()))
                    return match
            else:
                self.log(u"    %s대상이 (%d,%d) -> (%d,%d) 로 움직이는 중입니다. "
                         u"멈추기를 기다립니다"
                         % (head, match.getX(), match.getY(),
                            again.getX(), again.getY()))
                match = again
                steady_since = time.time()
                moved = True

            if time.time() > limit:
                self.log(u"    %s%.1f초 동안 자리가 멈추지 않았습니다. "
                         u"마지막으로 본 자리로 진행합니다"
                         % (head, self._timeout(step)))
                return match

    @staticmethod
    def _normalize_text(value):
        """비교용으로 글자를 다듬는다 - 공백 무시, 대소문자 무시.

        OCR 은 같은 글자를 읽어도 공백을 넣었다 뺐다 한다. 실제로 이 프로젝트의
        테스트 창에서 같은 라벨이 좁은 영역에서는 "OCULIX-TARGET", 창 전체에서는
        "OCULIX- TARGET" 으로 읽혔다. 공백을 지우고 비교하면 이 흔들림에 걸리지 않는다.
        """
        try:
            text = unicode(value)
        except (Exception, Throwable):
            return u""
        return u"".join(text.split()).upper()

    def _set_language(self, language):
        """글자 인식 언어를 바꾼다. **한 번에 한 언어만 된다.**

        OculiX 는 Tesseract 의 "kor+eng" 같은 다중 언어 표기를 거부한다.
        설치된 <언어>.traineddata 파일 이름과 그대로 대조하기 때문이다.
        한글 화면과 영문 화면이 섞여 있으면 단계마다 ocrLanguage 로 전환한다.

        Settings 와 globalOptions 를 **함께** 맞춰야 한다. 한쪽만 바꾸면
        남아 있는 값이 덮어써서 이후 인식이 전부 예외로 죽는다 (측정으로 확인).
        """
        language = language or u"eng"
        # 언어 설정은 프로세스 전체에 하나뿐이다. 다른 엔진(호출된 매크로,
        # 감시 매크로)이 그사이 바꿔 놓았을 수 있으므로 기억해 둔 값만 믿지
        # 않고 실제 값과도 대조한다.
        try:
            actual = Settings.OcrLanguage
        except (Exception, Throwable):
            actual = language
        if language == self._language and actual == language:
            return True
        previous = self._language
        try:
            Settings.OcrLanguage = language
            OCR.globalOptions().language(language)
            self._language = language
            return True
        except (Exception, Throwable), e:
            try:
                available = u", ".join([unicode(x) for x in OCR.availableLanguages()])
            except (Exception, Throwable):
                available = u"?"
            self.log(u"경고: 글자 인식 언어 '%s' 를 쓸 수 없습니다 "
                     u"(설치된 것: %s). '%s' 로 계속합니다."
                     % (language, available, previous))
            # 실패한 값이 남으면 이후 인식이 전부 죽으므로 되돌린다.
            try:
                Settings.OcrLanguage = previous
                OCR.globalOptions().language(previous)
            except (Exception, Throwable):
                pass
            return False

    def _set_psm(self, psm):
        """Tesseract 페이지 분할 모드를 정한다.

        화면 글자를 못 찾을 때 가장 먼저 의심할 값이다. 영역에 여백을 조금 두면
        기본값 3 에서는 인식이 통째로 비어버리는 일이 있었다 (Tesseract 가
        "Empty page!!" 를 뱉는다). 매크로 설정 `ocrPsm` 으로 바꿀 수 있다.
        쓸 만한 값: 11 성긴 글자, 4 세로로 늘어선 글줄, 7 한 줄, 3 자동.
        """
        if psm is None:
            return
        try:
            OCR.globalOptions().psm(int(psm))
        except (Exception, Throwable), e:
            self.log(u"경고: 글자 인식 psm=%r 을 쓸 수 없습니다: %s" % (psm, e))

    def _match_span(self, items, needle):
        """읽어낸 조각들을 이어붙여 needle 이 걸친 구간의 사각형을 만든다.

        조각을 하나씩 검사하면 한글을 놓친다. OCR 이 한글을 **음절마다 따로**
        내놓기 때문이다 - "설정 열기" 는 "설", "정", "열", "기" 네 조각이 되고
        "설정" 은 그중 어느 조각에도 통째로 들어 있지 않다. 그래서 전부 이어붙인
        뒤 위치를 찾고, 그 구간에 걸친 조각만 합쳐 사각형을 만든다. 이러면
        "설 정 열 기" 줄 전체가 아니라 "설정" 두 글자만 가리킨다.
        """
        flat = u""
        owner = []      # flat 의 각 글자가 몇 번째 조각에서 나왔는지
        for index, item in enumerate(items):
            try:
                text = item.getText()
            except (Exception, Throwable):
                continue
            for char in self._normalize_text(text):
                flat += char
                owner.append(index)
        at = flat.find(needle)
        if at < 0:
            return None
        span = owner[at:at + len(needle)]
        if not span:
            return None
        picked = items[min(span):max(span) + 1]
        # findWords/findLines 는 화면 절대 좌표를 준다 (OCR.readWords 는 상대).
        left = min(i.getX() for i in picked)
        top = min(i.getY() for i in picked)
        right = max(i.getX() + i.getW() for i in picked)
        bottom = max(i.getY() + i.getH() for i in picked)
        read = u" ".join([unicode(i.getText()).strip() for i in picked])
        return TextHit(Region(left, top, right - left, bottom - top), read)

    def _scan_text(self, region, query, for_click=False):
        """영역의 글자를 읽어 query 를 품은 곳을 찾는다. TextHit 또는 None.

        OculiX 의 existsText 를 쓰지 않는다. 그 함수의 일치 규칙이 단순 부분
        일치가 아니기 때문이다. 측정 결과 화면에 "OCULIX-TARGET" 이 있을 때
        existsText 는 "OCULIX" 는 찾았지만 "OCULIX-TARGET" 은 찾지 못했고,
        한글은 OCR 이 넣는 공백 때문에 "설정" 을 아예 못 찾았다
        ("설 정 열 기" 라고 공백까지 흉내내야만 걸렸다).

        단어 -> 줄 순으로 본다. 좁은 쪽이 클릭 지점으로도 알맞기 때문이다.
        두 방법 모두 같은 화면에서 실행마다 결과가 흔들려서 (한쪽이 놓친 글자를
        다른 쪽이 잡는다) 둘 다 시도한다. 위치가 필요 없는 판정이라면 마지막으로
        영역 전체를 통짜로 읽어본다 - 가장 관대하지만 위치는 알 수 없다.
        """
        needle = self._normalize_text(query)
        if not needle:
            return None
        for finder in ("findWords", "findLines"):
            try:
                items = getattr(region, finder)()
            except (Exception, Throwable):
                continue
            if not items:
                continue
            hit = self._match_span(items, needle)
            if hit is not None:
                return hit
        if for_click:
            return None
        try:
            whole = region.text()
        except (Exception, Throwable):
            return None
        if needle in self._normalize_text(whole):
            # 있다는 것만 안다. 어디인지는 모른다.
            return TextHit(region, unicode(whole).strip())
        return None

    def _find_text(self, step, for_click=False):
        """화면 글자를 읽어(OCR) 찾는다. TextHit 또는 None.

        대소문자와 공백을 무시한 부분 일치다. 제한시간까지 되풀이해 읽는다.
        검색 영역이 넓으면 인식률이 크게 떨어지므로 region 을 좁히는 것이
        중요하다 - 이미지 검색과 같은 원칙이다. 실제로 주 모니터 전체를 읽으면
        한 번에 2초 넘게 걸리고, 엉뚱한 창의 같은 글자를 짚기도 했다.
        """
        query = step.get("text")
        if not query:
            raise MacroError("step %r requires 'text'" % step.get("type"))
        self._set_language(step.get("ocrLanguage") or self._default_language)
        region = None
        if not SCALE.enabled():
            region = self._make_region(step.get("region"), step)
        deadline = time.time() + self._timeout(step)
        while True:
            spent = self._wait_tick()
            if spent:
                deadline += spent
                # 감시 매크로가 인식 설정을 바꿔 놓았을 수 있다
                self._set_language(step.get("ocrLanguage")
                                   or self._default_language)
            hit = self._read_text(region, step, query, for_click)
            if hit is not None:
                return hit
            if time.time() >= deadline:
                return None
            time.sleep(0.3)

    def _read_text(self, region, step, query, for_click):
        """글자를 한 번 읽는다. 해상도 대응을 쓰면 영역을 매번 다시 계산한다."""
        if region is None:
            try:
                region = self._make_region(step.get("region"), step)
            except WindowMissing:
                return None
        return self._scan_text(region, query, for_click)

    def _region_note(self, step):
        """로그에 쓸 검색 범위. 변환했으면 저장 값과 실제 값을 함께 쓴다."""
        spec = step.get("region")
        if not spec:
            return u"화면 전체"
        try:
            view = self._view(step)
        except WindowMissing:
            return u"%s (창 없음)" % (spec,)
        if view is None:
            return spec
        actual = view.region(spec, SCALE.screen_rect())
        if actual == [int(v) for v in spec]:
            return spec
        return u"%s -> %s" % (spec, actual)

    def _search_note(self, step):
        """어떤 조건으로 찾는지 한 줄로. 실패했을 때 무엇을 조일지 알려 준다."""
        return u"정확도 %.2f 이상, 제한 %.0f초, 범위 %s" % (
            float(step.get("similarity", self.default_similarity)),
            self._timeout(step),
            self._region_note(step))

    def _spot_text(self, target):
        """대상이 가리키는 좌표를 (x,y) 로. 알 수 없으면 (?,?)."""
        point = self._expected_point(target)
        return u"(%d,%d)" % point if point else u"(?,?)"

    def _target(self, step, allow_pointer=False, label=None):
        """클릭 대상을 정한다. 이미지면 찾은 Match, 아니면 절대 좌표.

        Match 를 그대로 넘기면 OculiX 가 `getTarget()` 을 누른다. 이 값은
        기본적으로 **찾은 영역의 정중앙**이고, targetOffset 을 준 경우에만
        그만큼 옮겨진다. 어디를 누르는지 로그에 남겨 눈으로 확인할 수 있게 한다.

        `label` 은 로그 앞에 붙는 자리 이름이다. 드래그처럼 대상이 둘인 노드는
        이게 없으면 어느 줄이 시작이고 어느 줄이 끝인지 구분할 수 없다.

        `allow_pointer` 를 주면 이미지·텍스트·좌표가 모두 비었을 때
        **현재 커서 위치**를 대상으로 삼는다. mouseDown/mouseUp 과 같은 결의
        단순 입력이다. 드래그처럼 그런 기본값이 성립하지 않는 곳에서는
        쓰지 않는다.
        """
        head = u"%s: " % label if label else u""

        if step.get("image"):
            # 찾기 전에 먼저 남긴다. 제한시간이 길면 여기서 한참 멈춰 있는데,
            # 무엇을 기다리는 중인지 모르면 멈춘 건지 도는 건지 알 수 없다.
            self.log(u"    %s이미지 %s 찾는 중 (%s)"
                     % (head, step["image"], self._search_note(step)))
            match = self._find(step)
            if match is None:
                self.log(u"    %s이미지 %s 없음" % (head, step["image"]))
                return None
            # 누르기 전에 자리가 멈췄는지 본다 (settleFor 를 준 단계만).
            match = self._settled(step, match, head)
            if match is None:
                self.log(u"    %s이미지 %s 가 자리를 잡지 못했습니다"
                         % (head, step["image"]))
                return None
            spot = match.getTarget()
            centre = (match.getX() + match.getW() // 2,
                      match.getY() + match.getH() // 2)
            offset = step.get("targetOffset")
            if offset:
                shift = u"  중앙 (%d,%d)  오프셋 (%d,%d) 적용" % (
                    centre[0], centre[1], int(offset[0]), int(offset[1]))
            else:
                shift = u""
            self.log(u"    %s이미지 %s 발견 score=%.4f  영역 (%d,%d) %dx%d%s"
                     u"  ->  잡는 지점 (%d,%d)"
                     % (head, step["image"], match.getScore(),
                        match.getX(), match.getY(),
                        match.getW(), match.getH(), shift,
                        spot.getX(), spot.getY()))
            return match

        if step.get("text"):
            self.log(u'    %s글자 "%s" 찾는 중 (%s)'
                     % (head, step["text"], self._search_note(step)))
            hit = self._find_text(step, for_click=True)
            if hit is None:
                self.log(u'    %s글자 "%s" 없음' % (head, step["text"]))
                return None
            spot = hit.region.getTarget()
            self.log(u'    %s글자 "%s" 발견 (읽은 값 "%s")  영역 (%d,%d) %dx%d'
                     u'  ->  잡는 지점 (%d,%d)'
                     % (head, step["text"], hit.text,
                        hit.region.getX(), hit.region.getY(),
                        hit.region.getW(), hit.region.getH(),
                        spot.getX(), spot.getY()))
            return hit.region

        point = step.get("point")
        if point:
            x, y = self._map_point(point, step)
            if (x, y) == (int(point[0]), int(point[1])):
                self.log(u"    %s좌표 지정 (%d,%d)" % (head, x, y))
            else:
                self.log(u"    %s좌표 지정 (%d,%d) -> (%d,%d)"
                         % (head, int(point[0]), int(point[1]), x, y))
            return Location(x, y)
        if not allow_pointer:
            raise MacroError("step %r needs 'image', 'text' or 'point'"
                             % step.get("type"))

        # 아무것도 지정하지 않았다 -> 커서가 지금 있는 자리에서 그대로 실행한다.
        pos = self._pointer()
        if pos is None:
            self.log(u"    %s현재 커서 위치를 읽지 못했습니다. "
                     u"화면보호기가 켜져 있는지 확인하세요" % head)
            return None
        self.log(u"    %s대상 지정 없음 -> 현재 커서 위치 (%d,%d) 에서 실행"
                 % (head, pos[0], pos[1]))
        return Location(pos[0], pos[1])


    # ------------------------------------------------------------ 프로그램 실행

    @staticmethod
    def _split_args(value):
        """인자 문자열을 나눈다. 큰따옴표로 묶은 조각은 하나로 본다."""
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [unicode(v) for v in value]
        parts = []
        current = []
        quoted = False
        for ch in unicode(value):
            if ch == u'"':
                quoted = not quoted
            elif ch.isspace() and not quoted:
                if current:
                    parts.append(u"".join(current))
                    current = []
            else:
                current.append(ch)
        if current:
            parts.append(u"".join(current))
        return parts

    def _run_program(self, step):
        """프로그램이나 문서를 실행한다.

        useShell(기본 켜짐)이면 `cmd /c start` 로 연결 프로그램에 맡긴다.
        .msc .lnk 문서 URL 은 이 방식이라야 열린다. 대신 시작만 하고 끝난다.
        끄면 실행 파일을 직접 실행하고 종료와 종료 코드를 확인할 수 있다.
        """
        from java.lang import ProcessBuilder
        from java.io import File
        from java.util import ArrayList
        from java.util.concurrent import TimeUnit

        command = step.get("command")
        if not command:
            self.log(u"    실행할 명령이 없습니다")
            return False

        args = self._split_args(step.get("args"))
        use_shell = step.get("useShell", True)
        wait_for_exit = bool(step.get("waitForExit", False))
        timeout = float(step.get("timeout", 30))
        working_dir = step.get("workingDir")

        if use_shell:
            # start 의 첫 인자는 창 제목 자리라 빈 문자열을 넣어야 한다
            tokens = [u"cmd", u"/c", u"start", u"", unicode(command)] + args
        else:
            tokens = [unicode(command)] + args

        parts = ArrayList()
        for token in tokens:
            parts.add(token)

        builder = ProcessBuilder(parts)
        builder.redirectErrorStream(True)
        if working_dir:
            folder = File(unicode(working_dir))
            if not folder.isDirectory():
                self.log(u"    작업 폴더가 없습니다: %s" % working_dir)
                return False
            builder.directory(folder)

        shown = u" ".join(tokens[4:] if use_shell else tokens)
        self.log(u"    실행: %s%s" % (shown,
                                      u"  (연결 프로그램)" if use_shell else u""))

        try:
            process = builder.start()
        except (Exception, Throwable), e:
            self.log(u"    실행 실패: %s" % e)
            return False

        if use_shell or not wait_for_exit:
            # 시작만 하고 넘어간다. cmd /c start 는 곧바로 끝난다.
            return True

        try:
            finished = process.waitFor(long(timeout * 1000), TimeUnit.MILLISECONDS)
        except (Exception, Throwable), e:
            self.log(u"    대기 중 오류: %s" % e)
            return False
        if not finished:
            process.destroy()
            self.log(u"    %.0f초 안에 끝나지 않아 중단했습니다" % timeout)
            return False

        code = process.exitValue()
        output = self._read_stream(process)
        if output:
            for line in output[:10]:
                self.log(u"      | %s" % line)
        if code != 0:
            self.log(u"    종료 코드 %d (0이 아니라 실패로 봅니다)" % code)
            return False
        self.log(u"    정상 종료 (코드 0)")
        return True

    # ------------------------------------------------------------- 창

    def _window(self, step):
        u"""노드가 가리키는 창을 찾는다. 제한시간까지 기다린다. 못 찾으면 None.

        여러 창이 맞으면 화면 맨 앞의 것을 쓰고 그 사실을 남긴다.
        """
        import window_util
        spec = window_util.spec_of(step)
        if spec is None:
            self.log(u"    창 조건이 없습니다 (제목, 클래스, 프로세스 중 하나)")
            return None
        timeout = self._timeout(step)

        def attempt(seconds):
            deadline = time.time() + seconds
            while True:
                found = window_util.find_windows(spec)
                if found:
                    return found
                left = deadline - time.time()
                if left <= 0:
                    return None
                time.sleep(min(window_util.FIND_POLL, left))

        found = self._watched(timeout, attempt)
        if not found:
            self.log(u"    창을 찾지 못했습니다: %s (%.0fs)"
                     % (window_util.describe_spec(spec), timeout))
            return None
        handle = found[0]
        if len(found) > 1:
            self.log(u"    조건에 맞는 창이 %d개라 맨 앞의 창을 씁니다"
                     % len(found))
        self.log(u"    창: %s" % window_util.describe(handle))
        return handle

    def _focus_window(self, step):
        import window_util
        handle = self._window(step)
        if handle is None:
            return False
        if window_util.is_foreground(handle) \
                and window_util.window_state(handle) != window_util.MINIMIZED:
            self.log(u"    이미 포커스를 가진 창입니다")
            return True
        if not window_util.focus(handle, self.log):
            self.log(u"    포커스를 가져오지 못했습니다. Windows 가 다른 창의 "
                     u"포커스를 지키고 있습니다")
            return False
        self.log(u"    포커스를 옮겼습니다")
        return True

    def _move_window(self, step):
        u"""창 테두리의 왼쪽 위를 지정한 화면 좌표로 옮긴다.

        옮기면 안 되는 상태(전체 화면, 최대화, 최소화)나 어느 모니터에도 없는
        좌표는 로그만 남기고 넘어간다. 실패로 보지 않는다.
        """
        import window_util
        point = step.get("point")
        if not (isinstance(point, (list, tuple)) and len(point) == 2):
            self.log(u"    옮길 좌표가 없습니다")
            return False
        x, y = int(point[0]), int(point[1])
        handle = self._window(step)
        if handle is None:
            return False

        state = window_util.window_state(handle)
        if state != window_util.NORMAL:
            self.log(u"    %s 상태라 옮기지 않습니다"
                     % window_util.STATE_LABELS[state])
            return True
        monitor = window_util.monitor_at(x, y)
        if monitor is None:
            self.log(u"    (%d, %d) 는 어느 모니터에도 없어 옮기지 않습니다"
                     % (x, y))
            return True

        before = window_util.frame_rect(handle)
        if before is not None and before[0] == x and before[1] == y:
            self.log(u"    이미 (%d, %d) 에 있습니다" % (x, y))
            return True
        width = before[2] - before[0] if before else 0
        height = before[3] - before[1] if before else 0
        if before and (x + width > monitor[2] or y + height > monitor[3]):
            self.log(u"    주의: %dx%d 창이 그 모니터 (%d,%d)-(%d,%d) 밖으로 "
                     u"삐져나갑니다" % ((width, height) + tuple(monitor)))

        after = window_util.move_frame(handle, x, y)
        if after is None:
            self.log(u"    옮긴 뒤 창 위치를 읽지 못했습니다")
            return False
        self.log(u"    옮김: (%d, %d) -> (%d, %d)"
                 % (before[0] if before else -1, before[1] if before else -1,
                    after[0], after[1]))
        slack = window_util.MOVE_SLACK
        if abs(after[0] - x) > slack or abs(after[1] - y) > slack:
            self.log(u"    창이 요청한 자리 (%d, %d) 에 가지 않았습니다. "
                     u"앱이 위치를 되돌렸을 수 있습니다" % (x, y))
            return False
        return True

    @staticmethod
    def _read_stream(process):
        from java.io import BufferedReader, InputStreamReader
        lines = []
        try:
            reader = BufferedReader(InputStreamReader(process.getInputStream()))
            while True:
                line = reader.readLine()
                if line is None:
                    break
                lines.append(line.strip())
            reader.close()
        except Exception:
            pass
        return [l for l in lines if l]

    # ------------------------------------------------------------ conditions

    def _drag_via(self, src, dst, waypoints):
        """경유지를 거쳐 끈다.

        `dragDrop` 은 시작에서 끝으로 곧장 가므로 중간 지점을 지날 수 없다.
        누르기(drag) - 지나가기(hover) - 놓기(dropAt) 로 나눠서 처리한다.

        도중에 예외가 나면 버튼을 누른 채로 빠져나가게 되는데, 그러면 이후
        모든 조작이 망가진다. 무슨 일이 있어도 버튼은 놓고 나온다.
        """
        self.screen.drag(src)
        pressed = True
        try:
            for point in waypoints:
                x, y = int(point[0]), int(point[1])
                self.screen.hover(Location(x, y))
                self.log(u"    경유 (%d,%d)" % (x, y))
            self.screen.dropAt(dst)
            pressed = False
        finally:
            if pressed:
                try:
                    self.screen.mouseUp(_BUTTONS["LEFT"])
                except (Exception, Throwable):
                    pass
        return True

    def _log_image_probe(self, probe, match):
        """조건이 무엇에 걸렸는지 남긴다.

        점수와 자리를 안 남기면 "화면에 없는데 참이 나온다" 를 눈으로 확인할
        길이 없다. 평평한 배경을 담은 템플릿은 전혀 다른 곳과도 0.9 넘게
        맞을 수 있어서, 그 자리를 찍어 줘야 오탐인지 바로 알 수 있다.
        """
        if match is None:
            self.log(u"    %s 없음 (%s)"
                     % (probe.get("image"), self._search_note(probe)))
            return
        self.log(u"    %s 발견 score=%.4f  영역 (%d,%d) %dx%d  (%s)"
                 % (probe.get("image"), match.getScore(),
                    match.getX(), match.getY(), match.getW(), match.getH(),
                    self._search_note(probe)))

    @staticmethod
    def _param_text(value):
        """로그에 보일 매개변수 값.

        %r 을 그대로 쓰면 Jython 2 가 유니코드 문자열을 u'...' 로 찍는다.
        사용자에게는 잡음이라 문자열만 따옴표로 감싸 보여 준다.
        """
        if isinstance(value, bool):
            return u"true" if value else u"false"
        if isinstance(value, (str, unicode)):
            return u'"%s"' % value
        return u"%s" % (value,)

    def _param_type(self, name):
        for param in graph_model.declared_params(self.macro):
            if param.get("name") == name:
                return param.get("type")
        # 반복(forEach)이 만드는 변수는 선언 목록에 없다. 노드에서 찾는다.
        return graph_model.loop_params(self.macro).get(name)

    def _compare_param(self, cond):
        """선언된 매개변수를 리터럴과 비교한다.

        비교할 값을 **선언된 타입으로 맞춘 뒤** 비교한다. 문자열 "3" 과
        숫자 3 을 그냥 비교하면 조건이 말없이 어긋난다.
        """
        name = cond.get("param")
        ptype = self._param_type(name)
        if ptype is None:
            raise MacroError("condition refers to undeclared parameter %r"
                             % (name,))
        actual = self.params.get(name)
        wanted = graph_model.coerce_param(
            cond.get("value"), ptype, u"조건의 비교값")
        op = cond.get("op")
        result = graph_model.compare_params(actual, op, wanted)
        self.log(u"    매개변수 %s = %s  %s  %s  ->  %s"
                 % (name, self._param_text(actual), op,
                    self._param_text(wanted), result))
        return result

    def evaluate(self, cond):
        ctype = cond.get("type")

        if ctype == "paramCompare":
            return self._compare_param(cond)

        if ctype in ("imageExists", "imageMissing"):
            probe = dict(cond)
            probe.setdefault("timeout", 3)
            match = self._find(probe)
            self._log_image_probe(probe, match)
            found = match is not None
            return found if ctype == "imageExists" else not found

        if ctype == "textExists":
            probe = dict(cond)
            probe.setdefault("timeout", 3)
            return self._find_text(probe) is not None

        if ctype == "textMissing":
            probe = dict(cond)
            probe.setdefault("timeout", 3)
            return self._find_text(probe) is None

        if ctype == "colorMatches":
            x, y = self._map_point(cond["point"], cond)
            rgb = pixel_util.get_pixel_rgb(x, y)
            return pixel_util.is_color_similar(
                rgb, tuple(cond["rgb"]), cond.get("tolerance", 10))

        if ctype == "not":
            return not self.evaluate(cond["condition"])

        if ctype == "all":
            for c in cond["conditions"]:
                if not self.evaluate(c):
                    return False
            return True

        if ctype == "any":
            for c in cond["conditions"]:
                if self.evaluate(c):
                    return True
            return False

        raise MacroError("unknown condition type: %r" % ctype)

    # ----------------------------------------------------------------- steps

    def run(self):
        """Execute the macro. Returns True when every step succeeded."""
        self.log("=== %s ===" % self.macro.get("name", "(no name)"))
        try:
            ok = self._run_steps(self.macro.get("steps", []))
        except _Break:
            self.log("!! 'break' outside a loop - treated as end of macro")
            ok = True
        self.log("=== steps=%d failed=%d -> %s ===" % (
            self.stats["steps"], self.stats["failed"],
            "OK" if ok else "ABORTED"))
        return ok

    def _run_steps(self, steps):
        for step in steps:
            if step.get("enabled") is False:
                self.log("--  skipped (disabled): %s" % step.get("type"))
                continue
            self._pause_point(step)
            self._watch_node_start()
            if not self._run_one(step):
                return False
            if self.step_delay:
                time.sleep(self.step_delay)
        return True

    @staticmethod
    def _name(node):
        return node.get("label") or node.get("type") or "?"

    def _log_entry(self, step, extra=u""):
        """노드에 들어갈 때 찍는 '--> ' 줄. 끝에 노드 id 를 붙인다.

        로그와 검사 메시지가 노드 id 로 노드를 가리키고, 캔버스도 머리에
        같은 값을 보여 준다. 실행 줄에도 있어야 셋을 바로 대조할 수 있다.
        트리 형식 단계에는 id 가 없으므로 그때는 이름만 남는다.
        """
        node_id = step.get("id")
        tail = u" (%s)" % node_id if node_id else u""
        self.log(u"--> %s%s%s" % (self._name(step), extra, tail))

    def _attempt(self, step):
        """단계를 실행하고 성공 여부만 돌려준다. onFail 은 여기서 보지 않는다.

        그래프 실행기는 '실패' 핀이 연결됐는지 먼저 봐야 하므로,
        실행과 실패 처리를 분리해 둔다.
        """
        stype = step.get("type")
        self.stats["steps"] += 1
        self._log_entry(step)

        try:
            ok = self._dispatch(step, stype)
        except _Break:
            raise
        except MacroError:
            raise
        except BudgetExceeded:
            # 대기 중에 돈 감시 매크로가 예산을 다 썼거나 막혔다. 단계 실패가
            # 아니라 실행 전체를 멈출 일이다.
            raise
        except (Exception, Throwable), e:
            self.log(u"    오류 %s: %s" % (e.__class__.__name__, e))
            ok = False

        if not ok:
            self.stats["failed"] += 1
        return ok

    def _run_one(self, step):
        """트리 실행기용. 실패하면 onFail 설정에 따라 계속할지 정한다."""
        if self._attempt(step):
            return True
        if step.get("onFail") == "continue":
            self.log("    FAILED - continuing (onFail=continue)")
            return True
        self.log("    FAILED - aborting macro")
        return False

    def _dispatch(self, step, stype):
        if stype == "log":
            self.log("    %s" % step.get("message", ""))
            return True

        if stype == "wait":
            seconds = float(step.get("seconds", 1))
            if not self._sliced():
                time.sleep(seconds)
                return True
            # 감시 처리와 일시정지 동안은 기다린 시간으로 치지 않는다
            end = time.time() + seconds
            while True:
                end += self._wait_tick()
                left = end - time.time()
                if left <= 0:
                    return True
                time.sleep(min(WATCH_SLICE, left))

        if stype == "run":
            return self._run_program(step)

        if stype == "focusWindow":
            return self._focus_window(step)

        if stype == "moveWindow":
            return self._move_window(step)

        if stype == "waitImage":
            match = self._find(step)
            if match is None:
                self.log("    not found: %s (%.0fs)" % (
                    step.get("image"), self._timeout(step)))
                return False
            self.log("    found score=%.4f at (%d,%d)" % (
                match.getScore(), match.getX(), match.getY()))
            return True

        if stype == "waitText":
            hit = self._find_text(step)
            if hit is None:
                self.log(u'    글자를 찾지 못했습니다: "%s" (%.0fs, 언어 %s)'
                         % (step.get("text"), self._timeout(step),
                            self._language))
                return False
            self.log(u'    글자 "%s" 발견 (읽은 값 "%s")  (%d,%d) %dx%d'
                     % (step["text"], hit.text,
                        hit.region.getX(), hit.region.getY(),
                        hit.region.getW(), hit.region.getH()))
            return True

        if stype == "waitVanish":
            gone = self._watched(
                self._timeout(step),
                lambda seconds: True if self._vanished(step, seconds)
                else None)
            if not gone:
                self.log("    still visible after %.0fs" % self._timeout(step))
            return bool(gone)

        if stype in ("click", "doubleClick", "rightClick", "hover"):
            target = self._target(step, allow_pointer=True)
            if target is None:
                self.log(u"    대상을 찾지 못했습니다: %s"
                         % (step.get("image") or step.get("text")
                            or step.get("point") or u"(현재 커서 위치)"))
                return False
            expected = self._expected_point(target)
            getattr(self.screen, stype)(target)
            self._verify_pointer(expected, u"클릭" if stype != "hover" else u"이동")
            return True

        if stype == "mouseDown":
            button = step.get("button", "LEFT").upper()
            self.screen.mouseDown(_BUTTONS[button])
            PAUSE.held.add(button)
            if self.watch is not None:
                # 누른 채로 감시가 끼어들면 드래그가 엉뚱한 곳에서 끝난다
                self.watch.held.add(button)
            return True

        if stype == "mouseUp":
            button = step.get("button", "LEFT").upper()
            self.screen.mouseUp(_BUTTONS[button])
            PAUSE.held.discard(button)
            if self.watch is not None:
                self.watch.held.discard(button)
            return True

        if stype == "drag":
            src = self._target(self._drag_side(step, "from"), label=u"시작")
            dst = self._target(self._drag_side(step, "to"), label=u"끝")
            if src is None or dst is None:
                # 어느 쪽이 안 됐는지 밝힌다. 둘 다 실패로 보이면 엉뚱한 쪽을 고친다.
                self.log(u"    드래그를 못 합니다 - 시작 %s, 끝 %s"
                         % (u"OK" if src is not None else u"못 찾음",
                            u"OK" if dst is not None else u"못 찾음"))
                return False
            waypoints = [self._map_point(p, step)
                         for p in step.get("waypoints") or []]
            route = [self._spot_text(src)]
            route.extend(u"경유 (%d,%d)" % (p[0], p[1]) for p in waypoints)
            route.append(self._spot_text(dst))
            self.log(u"    끌기 경로: %s" % u" -> ".join(route))
            if not waypoints:
                self.screen.dragDrop(src, dst)
                return True
            return self._drag_via(src, dst, waypoints)

        if stype == "wheel":
            target = self._target(step, allow_pointer=True)
            if target is None:
                self.log(u"    스크롤할 기준 위치를 정하지 못했습니다")
                return False
            direction = step.get("direction", "down").lower()
            amount = int(step.get("amount", 3))
            if direction == "up":
                self.screen.wheel(target, Button.WHEEL_UP, amount)
            else:
                self.screen.wheel(target, Button.WHEEL_DOWN, amount)
            return True

        if stype == "type":
            text = step.get("text", "")
            if step.get("usePaste"):
                self.screen.paste(text)   # safer for Korean / long strings
            else:
                self.screen.type(text)
            return True

        if stype == "key":
            key = step.get("key", "")
            resolved = getattr(Key, key.upper(), key)
            mods = step.get("modifiers", [])
            if mods:
                combined = None
                for m in mods:
                    value = _MODIFIERS[m.upper()]
                    combined = value if combined is None else (combined | value)
                self.screen.type(resolved, combined)
            else:
                self.screen.type(resolved)
            return True

        if stype == "waitColor":
            x, y = self._map_point(step["point"], step)
            got = self._watched(
                self._timeout(step),
                lambda seconds: pixel_util.wait_pixel_color(
                    x, y, tuple(step["rgb"]),
                    tolerance=step.get("tolerance", 10),
                    timeout=seconds,
                    interval=float(step.get("interval", 0.1))))
            if got is None:
                self.log("    colour never matched within %.0fs" % self._timeout(step))
                return False
            self.log("    colour matched: %s" % (got,))
            return True

        if stype == "if":
            result = self.evaluate(step["condition"])
            self.log("    condition -> %s" % result)
            branch = step.get("then", []) if result else step.get("else", [])
            return self._run_steps(branch)

        if stype == "repeat":
            return self._repeat(step)

        if stype == "break":
            raise _Break()

        raise MacroError("unknown step type: %r" % stype)

    def _vanished(self, step, seconds):
        """이미지가 사라졌는가. 창이 없으면 확인할 수 없으므로 아직 아니다."""
        try:
            region = self._make_region(step.get("region"), step)
            pattern = self._pattern(step)
        except WindowMissing:
            time.sleep(seconds)
            return False
        return region.waitVanish(pattern, seconds)

    @staticmethod
    def _drag_side(step, key):
        """드래그의 한쪽 끝. 노드에 준 `space` 를 양 끝이 함께 쓴다."""
        side = step.get(key, {})
        if step.get("space") and "space" not in side:
            side = dict(side)
            side["space"] = step["space"]
        return side

    def _repeat(self, step):
        steps = step.get("steps", [])

        # Both keys set means the macro says two different things. Guessing
        # let 'times' win silently, so a loop that had a condition attached
        # never evaluated it. Stop instead of guessing.
        if "times" in step and "while" in step:
            raise MacroError(
                "repeat: 'times' and 'while' cannot both be set - "
                "clear one of them")

        if "times" in step:
            count = int(step["times"])
            if count > HARD_ITERATION_CAP:
                raise MacroError("repeat.times %d exceeds cap %d" % (
                    count, HARD_ITERATION_CAP))
            for i in range(count):
                self.log("    iteration %d/%d" % (i + 1, count))
                try:
                    if not self._run_steps(steps):
                        return False
                except _Break:
                    self.log("    break")
                    return True
            return True

        if "while" in step:
            # A while loop without a bound is exactly the failure mode this
            # project forbids, so maxIterations is mandatory.
            if "maxIterations" not in step:
                raise MacroError("repeat/while requires 'maxIterations'")
            limit = int(step["maxIterations"])
            if limit > HARD_ITERATION_CAP:
                raise MacroError("maxIterations %d exceeds cap %d" % (
                    limit, HARD_ITERATION_CAP))
            i = 0
            while i < limit:
                if not self.evaluate(step["while"]):
                    self.log("    while-condition false, exiting after %d" % i)
                    return True
                i += 1
                self.log("    iteration %d (max %d)" % (i, limit))
                try:
                    if not self._run_steps(steps):
                        return False
                except _Break:
                    self.log("    break")
                    return True
            self.log("    reached maxIterations (%d) - stopping loop" % limit)
            return bool(step.get("allowMaxIterations", True))

        raise MacroError("repeat needs 'times' or 'while'")


# ------------------------------------------------------------------- 그래프

import graph_model


class BudgetExceeded(Exception):
    """실행 예산 초과. 자유 연결 그래프에서 순환이 멈추지 않을 때의 안전장치."""
    pass


class WatchStuck(BudgetExceeded):
    """같은 감시가 메인이 나아가지 못하는 동안 계속 걸린다 - 닫기가 먹지 않는다.

    예산 초과와 같은 길로 실행 전체를 멈춘다. 단계 하나의 실패로 다루면
    실패 핀이나 재시도가 같은 화면에서 같은 일을 되풀이할 뿐이다.
    """
    pass


NORMAL = "normal"
BREAK = "break"
ABORT = "abort"

# _on_failure 가 '중단은 아니지만 이어갈 노드도 없다'를 알릴 때 쓰는 표시
END_OF_CHAIN = "__end__"


class GraphEngine(Engine):
    """노드 그래프를 실행 링크를 따라가며 실행한다.

    트리 실행기와 달리 순환이 만들어질 수 있으므로, 전역 실행 예산
    (maxSteps / maxSeconds)으로 상한을 둔다. 이것이 무한 루프를 막는
    유일한 수단이므로 끌 수 없다.
    """

    def __init__(self, macro, base_dir, logger=None, root=None, call_stack=None,
                 start_node=None, params=None, resume_path=None):
        Engine.__init__(self, macro, base_dir, logger, params=params)
        self.graph = graph_model.Graph(macro)
        # 지금 어디를 지나고 있는지. 반복/호출로 들어갈 때마다 한 칸 쌓인다.
        # 파이썬 호출 스택에만 있으면 밖으로 꺼낼 수가 없어서 따로 들고 다닌다.
        self.frames = []
        # 실패한 자리 (가장 안쪽 것 하나만 남긴다). 그 순간 지나고 있던
        # 반복/호출이 몇 겹이든 전부 담긴다 - 재시도와 '이어서 실행'이
        # 이 경로를 되짚어 실패한 노드로 곧장 들어간다.
        self.failed_at = None
        self.failed_name = None
        # 이번 실행을 이 경로부터 이어서 한다면 그 경로
        self.resume_path = resume_path
        # 이어서 실행할 위치를 남길 때 쓸 '진짜' 매크로 파일 경로.
        # 하위 매크로는 base_dir 이 부모로 바뀌므로 그것으로는 알 수 없다.
        self.macro_path = None
        # 이번 실행에만 쓰는 시작 지점. 매크로에 저장된 entry 는 건드리지 않는다.
        # 호출된 매크로는 늘 자기 entry 에서 시작하므로 물려주지 않는다.
        self.start_node = start_node
        settings = macro.get("settings", {})
        self.max_steps = int(settings.get("maxSteps", graph_model.DEFAULT_MAX_STEPS))
        self.max_seconds = float(settings.get("maxSeconds",
                                              graph_model.DEFAULT_MAX_SECONDS))
        self.executed = 0
        self.deadline = None
        # 호출된 매크로는 자기 예산을 새로 시작하면 안 된다. 상한이 무의미해진다.
        # 루트 엔진 하나가 전체 실행의 예산을 갖는다.
        self.root = root or self
        # 호출 사슬은 흐름마다 하나다. 호출된 매크로는 호출한 쪽의 목록을 그대로
        # 받고, 감시 처리는 메인과 별개인 자기 목록으로 시작한다.
        self.call_stack = call_stack if call_stack is not None else []
        # 하위 매크로를 단독으로 돌릴 때 부모의 감시 목록. make_engine 이 채운다.
        # (부모 매크로, 부모 폴더, 부모 macro.json 경로)
        self.inherited_handlers = None

    def _start_watch(self):
        """최상위 실행의 감시('전역' 감시)를 건다.

        걸 감시가 없어도 관리자는 만든다. 최상위에는 감시가 없고 호출된
        매크로에만 있는 경우에도 그 감시가 걸려야 하기 때문이다.

        하위 매크로를 단독으로 돌릴 때는 부모의 감시를 먼저 건다. 호출로
        돌 때와 같은 문맥이어야 단독 실행으로 확인한 것이 본 실행에서도 맞다.
        """
        layers = []
        if self.inherited_handlers:
            parent, parent_dir, parent_path = self.inherited_handlers
            layers.append((parent, parent_dir, parent_path))
        layers.append((self.macro, self.base_dir, self.macro_path))
        watch = WatchManager(self, graph_model.handler_interval(self.macro))
        try:
            for macro, folder, path in layers:
                if graph_model.handler_refs(macro):
                    watch.push(self, macro, folder, path)
        except MacroError, e:
            self.log(u"오류: %s" % e)
            return False
        self.watch = watch
        if watch.active():
            self.log(u"감시 확인 간격: %.1f초" % watch.interval)
        return True

    def run(self):
        # 한글이 들어간 서식 문자열은 반드시 u"" 여야 한다.
        # Jython 2.7에서 바이트 문자열 + unicode 인자를 섞으면 latin-1로
        # 디코딩되어 글자가 깨진다.
        self.log(u"=== %s (그래프) ===" % self.macro.get("name", "(no name)"))
        errors, warnings = self.graph.validate()
        for warning in warnings:
            self.log(u"경고: %s" % warning)
        if errors:
            for error in errors:
                self.log(u"오류: %s" % error)
            self.log(u"=== 정의 오류로 실행하지 않음 ===")
            return False

        start = self.graph.entry
        if self.start_node:
            node = self.graph.node(self.start_node)
            if node is None:
                self.log(u"오류: 시작 노드 %s 를 이 매크로에서 찾을 수 없습니다"
                         % self.start_node)
                self.log(u"=== 정의 오류로 실행하지 않음 ===")
                return False
            start = self.start_node
            self.log(u"시작 지점 지정: %s  (저장된 시작 노드 대신 여기서부터)"
                     % self._name(node))

        is_root = self.root is self
        if is_root:
            if not self._start_watch():
                self.log(u"=== 정의 오류로 실행하지 않음 ===")
                return False
            self.log(u"예산: 최대 %d단계 / %.0f초" % (self.max_steps, self.max_seconds))
            self.deadline = time.time() + self.max_seconds

        path = self.resume_path
        if path:
            if not self._describe_resume(path):
                return False
            start = path[0]["node"]

        try:
            status = self._run_chain(start, 0, resume=path)
        except BudgetExceeded, e:
            # 예산은 실행 전체에 하나뿐이다. 호출된 매크로 안에서 터졌다면
            # 여기서 삼키지 말고 루트까지 올려보내 실행 전체를 멈춘다.
            if not is_root:
                raise
            stuck = isinstance(e, WatchStuck)
            self.log(u"!! %s" % e)
            self.log(u"=== %s (실행 %d단계) ==="
                     % (u"감시가 막혀 중단" if stuck else u"예산 초과로 중단",
                        self.root.executed))
            self._save_resume(u"감시 막힘" if stuck else u"예산 초과")
            return False

        ok = status != ABORT
        if is_root and not ok:
            self._save_resume(u"단계 실패")
        elif is_root:
            self._clear_resume()
        self.log(u"=== 노드 %d회 실행, 실패 %d -> %s ===" % (
            self.root.executed if is_root else self.stats["steps"],
            self.stats["failed"], "OK" if ok else "ABORTED"))
        return ok

    def _describe_resume(self, path):
        """이어서 실행할 자리를 확인하고 알린다. 못 쓰면 False."""
        first = self.graph.node(path[0].get("node"))
        if first is None:
            self.log(u"오류: 이어서 실행할 노드 %s 를 이 매크로에서 찾을 수 "
                     u"없습니다. 매크로를 고쳤다면 저장된 위치는 쓸 수 없습니다"
                     % path[0].get("node"))
            return False
        self.log(u"이어서 실행: %s" % u" > ".join(self._step_text(f) for f in path))
        return True

    def _step_text(self, frame):
        node = self.graph.node(frame.get("node"))
        name = self._name(node) if node else frame.get("node")
        if frame.get("enter") == "loop":
            return u"%s[%d회째]" % (name, int(frame.get("done", 0)) + 1)
        if frame.get("enter") == "call":
            return u"%s->" % (frame.get("ref") or name)
        return u"%s" % name

    def _clear_resume(self):
        """끝까지 성공했으면 이 매크로의 '이어서 실행' 기록을 지운다.

        이어서 실행이 성공한 뒤에도 기록이 남아 있으면 편집기 버튼이 계속
        켜져 있어서, 다시 누르면 이미 끝낸 지점으로 돌아간다. 다른 매크로의
        기록은 건드리지 않는다.
        """
        try:
            if not os.path.exists(RESUME_FILE):
                return
            handle = open(RESUME_FILE, "rb")
            try:
                saved = json.loads(handle.read().decode("utf-8"))
            finally:
                handle.close()
            mine = os.path.normcase(os.path.abspath(self.macro_path or u""))
            theirs = os.path.normcase(os.path.abspath(saved.get("macro") or u""))
            if mine == theirs:
                os.remove(RESUME_FILE)
        except (Exception, Throwable):
            pass

    def _save_resume(self, reason):
        """실패한 순간의 위치를 파일로 남긴다. 편집기의 '이어서 실행'이 읽는다."""
        if not self.failed_at:
            self.log(u"실패한 위치를 알 수 없어 이어서 실행할 수 없습니다")
            return
        payload = {
            "macro": self.macro_path or os.path.abspath(
                os.path.join(self.base_dir, "macro.json")),
            "macroName": self.macro.get("name") or u"",
            "savedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
            "failedAt": self.failed_at,
            "failedName": self.failed_name,
        }
        try:
            folder = os.path.dirname(RESUME_FILE)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            handle = open(RESUME_FILE, "wb")
            try:
                handle.write(json.dumps(payload, ensure_ascii=False,
                                        indent=2).encode("utf-8"))
            finally:
                handle.close()
        except (Exception, Throwable), e:
            self.log(u"이어서 실행할 위치를 남기지 못했습니다: %s" % e)
            return
        self.log(u"이어서 실행할 수 있습니다 - 실패한 '%s' 부터 "
                 u"(편집기의 [이어서 실행])" % (self.failed_name or u"?"))

    # ------------------------------------------------------------------ 실행

    # ------------------------------------------------- 실행 위치 기록 / 재개

    def _here(self, node_id, enter=None, **extra):
        """지금 위치를 나타내는 프레임 하나.

        매크로 이름은 base_dir 이 아니라 매크로가 스스로 밝힌 이름을 쓴다.
        하위 매크로는 부모 폴더를 base_dir 로 쓰기 때문에, 폴더 이름으로는
        호출 사슬의 모든 칸이 부모 이름으로 찍힌다. 이 이름은 사람이 기록을
        읽을 때만 쓰이지만, 진단용 파일에 틀린 이름이 들어가면 안 된다.
        """
        frame = {"macro": (self.macro.get("name")
                           or os.path.basename(os.path.abspath(self.base_dir))),
                 "node": node_id, "enter": enter}
        frame.update(extra)
        return frame

    def _path_to(self, node_id):
        """루트에서 이 노드까지 내려오는 길 전체. 재개할 때 이 길을 되짚는다."""
        return [dict(f) for f in self.root.frames] + [self._here(node_id)]

    def _note_failure(self, node_id):
        """실패한 자리를 남긴다. 가장 안쪽 것 하나만 - 밖으로 번지며
        덮어쓰면 어디서 처음 터졌는지 알 수 없다."""
        if self.root.failed_at is None:
            self.root.failed_at = self._path_to(node_id)
            node = self.graph.node(node_id)
            self.root.failed_name = self._name(node) if node else node_id

    def _forget_failure(self):
        """실패를 실패 핀이나 '무시하고 계속'으로 넘겼다. 기록을 지운다.

        안쪽 노드가 실패해 위치가 남은 뒤 바깥 호출 노드의 실패 핀이 그걸
        복구하면, 지우지 않는 한 낡은 위치가 남아 나중의 진짜 실패를
        가린다 (가장 안쪽 하나만 남기는 규칙 때문에 덮어쓰지 못한다).
        """
        self.root.failed_at = None
        self.root.failed_name = None

    def _consume_resume(self, resume, node_id):
        """복원 경로의 머리가 이 노드를 가리키면 (프레임, 나머지) 를 준다."""
        if resume and resume[0].get("node") == node_id:
            return resume[0], list(resume[1:])
        return None, None

    def _spend(self, node_id):
        root = self.root
        root.executed += 1
        if root.executed > root.max_steps:
            raise BudgetExceeded(
                u"실행 단계가 상한 %d를 넘었습니다 (노드 %s). "
                u"연결에 순환이 있는지 확인하세요." % (root.max_steps, node_id))
        # 멈춰 있던 시간은 실행 시간으로 치지 않는다. 사용자가 10분 멈췄다고
        # 재개하자마자 예산 초과로 끝나면 일시정지를 쓸 수 없다.
        if root.deadline is not None and \
                time.time() - PAUSE.total > root.deadline:
            raise BudgetExceeded(
                u"실행 시간이 상한 %.0f초를 넘었습니다 (노드 %s)."
                % (root.max_seconds, node_id))

    def _on_failure(self, node_id, node):
        """실패했을 때 다음에 갈 노드 id. None 이면 매크로를 중단한다.

        우선순위
          1. '실패' 핀에 연결된 노드가 있으면 그쪽 (복구 경로)
          2. onFail 이 continue 면 평소 진행 핀으로
          3. 그 외에는 중단
        """
        target = self.graph.target(node_id, graph_model.FAIL_PIN)
        if target:
            self.log(u"    실패 -> 실패 경로로 진행")
            self._forget_failure()
            return target
        if node.get("onFail") == "continue":
            self._forget_failure()
            carry = self.graph.target(node_id,
                                      graph_model.skip_pin(node.get("type")))
            if carry:
                self.log(u"    실패했지만 계속 진행 (onFail=continue)")
                return carry
            self.log(u"    실패했지만 계속 진행 - 이어진 노드가 없어 여기서 끝")
            return END_OF_CHAIN
        self.log(u"    실패 - 매크로 중단")
        self._note_failure(node_id)
        return None

    def _run_chain(self, node_id, depth, resume=None):
        """실행 링크를 따라 체인을 실행한다.

        연결이 끊긴 지점에서 자연히 끝나고, 그때 호출자(루프 또는 최상위)로
        돌아간다. 블루프린트의 실행 핀과 같은 동작이다.

        `resume` 은 이어서 실행할 때만 준다. 머리가 시작 노드를 가리키는
        복원 경로이고, 그 노드가 반복이나 호출이면 그 **안쪽**으로 마저
        내려간다. 한 번 쓰고 버린다 - 그 뒤로는 평범하게 흐른다.
        """
        guard = 0
        while node_id:
            node = self.graph.node(node_id)
            if node is None:
                self.log(u"!! 연결된 노드를 찾을 수 없습니다: %s" % node_id)
                return ABORT

            step, inner = self._consume_resume(resume, node_id)
            resume = None

            self._pause_point(node)
            self._spend(node_id)
            guard += 1
            self._watch_node_start()

            ntype = node.get("type")

            if node.get("enabled") is False:
                self.log(u"--  건너뜀 (사용 안 함): %s (%s)"
                         % (self._name(node), node.get("id")))
                node_id = self.graph.target(node_id, graph_model.skip_pin(ntype))
                continue

            if ntype == "break":
                self._log_entry(node)
                return BREAK

            if ntype == "if":
                self._log_entry(node)
                self.stats["steps"] += 1
                failed = False
                result = False
                try:
                    result = self.evaluate(node["condition"])
                except (MacroError, BudgetExceeded):
                    raise
                except (Exception, Throwable), e:
                    self.log(u"    오류 %s: %s" % (e.__class__.__name__, e))
                    self.stats["failed"] += 1
                    failed = True
                if failed:
                    node_id = self._on_failure(node_id, node)
                    if node_id is None:
                        return ABORT
                    if node_id == END_OF_CHAIN:
                        return NORMAL
                    continue
                self.log(u"    조건 -> %s" % result)
                node_id = self.graph.target(node_id, "true" if result else "false")
                continue

            if ntype == "repeat":
                status = self._run_loop(
                    node, depth,
                    resume=(step, inner) if step is not None
                                            and step.get("enter") == "loop"
                                         else None)
                if status == BREAK:
                    return BREAK
                if status == ABORT:
                    node_id = self._on_failure(node_id, node)
                    if node_id is None:
                        return ABORT
                    if node_id == END_OF_CHAIN:
                        return NORMAL
                    continue
                node_id = self.graph.target(node_id, "completed")
                continue

            if ntype == "call":
                if not self._run_call(
                        node,
                        resume=inner if step is not None
                                        and step.get("enter") == "call"
                                     else None):
                    node_id = self._on_failure(node_id, node)
                    if node_id is None:
                        return ABORT
                    if node_id == END_OF_CHAIN:
                        return NORMAL
                    continue
                node_id = self.graph.target(node_id, "next")
                continue

            if not self._attempt(node):
                node_id = self._on_failure(node_id, node)
                if node_id is None:
                    return ABORT
                if node_id == END_OF_CHAIN:
                    return NORMAL
                continue
            node_id = self.graph.target(node_id, "next")

        return NORMAL

    def _run_call(self, node, resume=None):
        """다른 매크로를 함수처럼 호출한다.

        호출된 매크로는 자기 폴더를 기준으로 이미지를 찾고 자기 설정을 쓴다.
        예산은 루트와, 호출 사슬은 호출한 쪽과 공유한다.
        """
        self.stats["steps"] += 1
        ref = node.get("macro")
        self._log_entry(node, u"  [호출: %s]" % ref)

        if not ref:
            self.log(u"    호출할 매크로가 지정되지 않았습니다")
            return self._call_failed(node)

        path = graph_model.resolve_macro_ref(ref, self.base_dir)
        if path is None:
            self.log(u"    매크로를 찾을 수 없습니다: %s" % ref)
            return self._call_failed(node)

        # 하위 매크로는 그 부모와 형제만 부를 수 있다. 참조 표기("./" 여부)가
        # 아니라 **파일 위치**로 판정하므로 "부모/하위" 식 경로로 남의 하위를
        # 집어도 여기서 걸린다.
        target_dir = os.path.dirname(os.path.abspath(path))
        target_owner = graph_model.family_root(target_dir)
        target_is_sub = target_owner != target_dir
        if target_is_sub and os.path.normcase(target_owner) != \
                os.path.normcase(graph_model.family_root(self.base_dir)):
            self.log(u"    '%s' 는 다른 매크로의 하위 매크로입니다. "
                     u"하위 매크로는 부모와 형제만 호출할 수 있습니다" % ref)
            return self._call_failed(node)

        key = os.path.normcase(os.path.abspath(path))
        stack = self.call_stack
        if key in stack:
            self.log(u"    순환 호출입니다. 호출 사슬: %s"
                     % u" -> ".join(os.path.basename(os.path.dirname(p))
                                    for p in stack + [key]))
            return self._call_failed(node)
        if len(stack) >= graph_model.MAX_CALL_DEPTH:
            self.log(u"    호출 깊이가 상한 %d를 넘었습니다"
                     % graph_model.MAX_CALL_DEPTH)
            return self._call_failed(node)

        try:
            handle = open(path, "rb")
            try:
                data = json.loads(handle.read().decode("utf-8"))
            finally:
                handle.close()
        except (Exception, Throwable), e:
            self.log(u"    매크로를 읽지 못했습니다: %s: %s"
                     % (e.__class__.__name__, e))
            return self._call_failed(node)

        sub_dir = os.path.dirname(os.path.abspath(path))
        if target_is_sub:
            # 하위 매크로는 UE 함수처럼 소유자의 문맥에서 돈다 - 설정은
            # 호출한 쪽 것을 물려받고(형제끼리는 부모 것이 전파된다),
            # 이미지는 부모 폴더에서 찾는다. base_dir 를 부모로 두면
            # "./" 참조 해석도 가족 기준이 되어 형제 호출이 그대로 된다.
            data = dict(data)
            data["settings"] = dict(self.macro.get("settings") or {})
            sub_dir = target_owner
        stack.append(key)
        indent = u"    " * (len(stack))

        def sub_logger(message):
            self.log(u"%s| %s" % (indent, message))

        # 반복 변수를 넘기는 {"$param": 이름} 을 지금 값으로 바꾼다.
        # 범위에 없으면 여기서 멈춘다 - 비워서 넘기면 왜 안 먹는지 찾을 수 없다.
        supplied, trouble = graph_model.resolve_args(node.get("args"),
                                                     self.params)
        if trouble:
            for line in trouble:
                self.log(u"    매개변수 오류: %s" % line)
            stack.pop()
            return self._call_failed(node)

        # 넘길 값을 선언과 맞춰 본다. 어긋나면 실행하지 않는다 -
        # 조용히 넘어가면 왜 안 먹는지 찾을 수 없다.
        bound, trouble = graph_model.bind_params(data, supplied)
        if trouble:
            for line in trouble:
                self.log(u"    매개변수 오류: %s" % line)
            stack.pop()
            return self._call_failed(node)
        if bound:
            self.log(u"    매개변수: %s"
                     % u", ".join(u"%s=%s" % (k, self._param_text(bound[k]))
                                  for k in sorted(bound.keys())))

        # 호출된 매크로의 감시는 그 매크로가 도는 동안만 바깥 감시 뒤에 붙는다.
        watching = False
        if self.watch is not None and graph_model.handler_refs(data):
            try:
                self.watch.push(self, data, sub_dir, path)
            except MacroError, e:
                self.log(u"    감시를 걸 수 없습니다: %s" % e)
                stack.pop()
                return self._call_failed(node)
            watching = True

        spot = self._here(node.get("id"), "call", ref=ref)
        self.root.frames.append(spot)
        try:
            if graph_model.is_graph(data):
                sub = GraphEngine(data, sub_dir, sub_logger,
                                  root=self.root, call_stack=stack,
                                  params=bound, resume_path=resume)
            else:
                if resume:
                    self.log(u"    트리 형식 매크로는 중간부터 이어서 할 수 "
                             u"없습니다. 처음부터 돕니다")
                sub = Engine(data, sub_dir, sub_logger, params=bound)
            sub.watch = self.watch
            ok = sub.run()
        finally:
            self.root.frames.pop()
            stack.pop()
            if watching:
                self.watch.pop(self)

        self.stats["failed"] += sub.stats.get("failed", 0)
        if not ok:
            self.log(u"    호출한 매크로가 실패했습니다: %s" % ref)
            return self._call_failed(node)
        self.log(u"    호출 완료: %s" % ref)
        return True

    def _call_failed(self, node):
        """호출 실패를 기록만 한다. 어디로 갈지는 _on_failure 가 정한다."""
        self.stats["failed"] += 1
        return False

    def _body(self, body_start, depth, inner):
        """반복 본문 한 회차. `inner` 가 있으면 그 안쪽부터 이어서 한다."""
        if inner:
            return self._run_chain(inner[0]["node"], depth + 1, resume=inner)
        return self._run_chain(body_start, depth + 1)

    def _run_loop(self, node, depth, resume=None):
        body_start = self.graph.target(node.get("id"), "body")
        frame, inner = resume if resume else (None, None)
        # 이어서 하는 경우 이미 끝낸 횟수부터 시작한다. 진행 중이던 회차는
        # 처음부터 다시 도는데, 그 회차가 어디까지 갔는지는 inner 가 안다.
        resume_from = int(frame.get("done", 0)) if frame else 0

        # 반복 방식은 times / while / forEach 셋 중 하나뿐이다. 둘 이상 있으면
        # 어느 쪽이 뜻인지 알 수 없다. 예전에는 times 가 조용히 이겨서, 조건을
        # 넣어 둔 반복이 조건을 한 번도 보지 않고 끝났다 (times=0 이면 본문 없이
        # 곧장 '완료' 핀으로 나간다). 짐작하지 않는다.
        modes = [key for key in ("times", "while", "forEach") if key in node]
        if len(modes) > 1:
            raise MacroError(
                u"노드 %s: 반복 방식을 하나만 골라야 합니다 (지금 %s 가 함께 "
                u"있습니다)" % (node.get("id"), u", ".join(modes)))

        spec = graph_model.foreach_spec(node)
        if spec is not None:
            return self._run_foreach(node, spec, body_start, depth,
                                     resume_from, inner)

        if "times" in node:
            count = int(node["times"])
            if count > HARD_ITERATION_CAP:
                raise MacroError(u"반복 횟수 %d가 상한 %d를 넘습니다"
                                 % (count, HARD_ITERATION_CAP))
            self._log_entry(node, u" (%d회)" % count)
            if resume_from:
                self.log(u"    %d회까지는 끝난 것으로 보고 이어서 합니다"
                         % resume_from)
            spot = self._here(node.get("id"), "loop", mode="times", done=0)
            self.root.frames.append(spot)
            try:
                for i in range(resume_from, count):
                    spot["done"] = i
                    self.log(u"    %d/%d" % (i + 1, count))
                    status = self._body(body_start, depth, inner)
                    inner = None
                    if status == ABORT:
                        return ABORT
                    if status == BREAK:
                        self.log(u"    break")
                        return NORMAL
            finally:
                self.root.frames.pop()
            return NORMAL

        if "while" in node:
            if "maxIterations" not in node:
                raise MacroError(u"노드 %s: 조건 반복에는 maxIterations가 필수입니다"
                                 % node.get("id"))
            limit = int(node["maxIterations"])
            if limit > HARD_ITERATION_CAP:
                raise MacroError(u"maxIterations %d가 상한 %d를 넘습니다"
                                 % (limit, HARD_ITERATION_CAP))
            self._log_entry(node, u" (조건 반복, 최대 %d)" % limit)
            if resume_from:
                self.log(u"    %d회 돈 상태에서 이어서 합니다 (조건은 다시 봅니다)"
                         % resume_from)
            spot = self._here(node.get("id"), "loop", mode="while", done=0)
            self.root.frames.append(spot)
            try:
                i = resume_from
                while i < limit:
                    spot["done"] = i
                    # 이어서 하는 첫 회차는 조건을 다시 묻지 않는다. 아까
                    # 참이어서 들어갔던 회차를 마저 하는 것이기 때문이다.
                    if inner is None and not self.evaluate(node["while"]):
                        self.log(u"    조건 거짓, %d회 후 종료" % i)
                        return NORMAL
                    i += 1
                    self.log(u"    %d (최대 %d)" % (i, limit))
                    status = self._body(body_start, depth, inner)
                    inner = None
                    if status == ABORT:
                        return ABORT
                    if status == BREAK:
                        self.log(u"    break")
                        return NORMAL
            finally:
                self.root.frames.pop()
            self.log(u"    최대 반복 도달 (%d)" % limit)
            return NORMAL

        raise MacroError(u"노드 %s: times / while / forEach 중 하나가 필요합니다"
                         % node.get("id"))

    def _run_foreach(self, node, spec, body_start, depth,
                     resume_from=0, inner=None):
        """값 목록을 하나씩 변수에 넣으며 본문을 돈다.

        반복 변수는 **본문 안에서만** 산다. 끝나면 이전 값으로 되돌려서,
        루프 밖에서 남은 값을 실수로 읽는 일이 없게 한다. 같은 이름의 반복이
        중첩돼도 안쪽이 끝나면 바깥 값이 그대로 돌아온다.
        """
        problems = graph_model.validate_foreach(node)
        if problems:
            raise MacroError(problems[0])

        name = spec.get("param")
        values = graph_model.foreach_values(
            spec, u"노드 %s의 값 반복" % node.get("id"))
        if len(values) > HARD_ITERATION_CAP:
            raise MacroError(u"반복할 값이 %d개로 상한 %d를 넘습니다"
                             % (len(values), HARD_ITERATION_CAP))

        self._log_entry(node, u" (%s = %s)" % (
            name, u", ".join(self._param_text(v) for v in values)))

        if resume_from:
            self.log(u"    %d개까지는 끝난 것으로 보고 이어서 합니다" % resume_from)
        had = name in self.params
        previous = self.params.get(name)
        spot = self._here(node.get("id"), "loop", mode="forEach", done=0)
        self.root.frames.append(spot)
        try:
            for index in range(resume_from, len(values)):
                value = values[index]
                spot["done"] = index
                self.params[name] = value
                self.log(u"    %d/%d  %s = %s" % (
                    index + 1, len(values), name, self._param_text(value)))
                status = self._body(body_start, depth, inner)
                inner = None
                if status == ABORT:
                    return ABORT
                if status == BREAK:
                    self.log(u"    break")
                    return NORMAL
        finally:
            self.root.frames.pop()
            if had:
                self.params[name] = previous
            else:
                self.params.pop(name, None)
        return NORMAL


# ------------------------------------------------------------- 감시 매크로

# 감시 조건에서 화면을 읽는 종류. 확인할 때 기다리지 않도록 제한시간을 0으로 둔다.
_SCREEN_CONDITIONS = ("imageExists", "imageMissing", "textExists", "textMissing")


def _instant(cond):
    """감시 조건의 사본. 화면을 읽는 조건은 기다리지 않고 한 번만 본다.

    조건 노드의 기본 제한시간(3초)을 그대로 쓰면 감시 한 바퀴마다 메인이
    몇 초씩 멈춘다. 감시는 '지금 떠 있는가' 만 묻는다.
    """
    copy = dict(cond)
    if copy.get("type") in _SCREEN_CONDITIONS:
        copy["timeout"] = 0
    if isinstance(copy.get("condition"), dict):
        copy["condition"] = _instant(copy["condition"])
    if isinstance(copy.get("conditions"), list):
        copy["conditions"] = [_instant(c) for c in copy["conditions"]]
    return copy


class _Handler(object):
    """걸려 있는 감시 매크로 하나."""

    def __init__(self, ref, key, macro, base_dir, owner):
        self.ref = ref
        self.key = key              # macro.json 절대 경로 (normcase)
        self.macro = macro          # 하위 매크로면 부모 설정을 물려받은 사본
        self.base_dir = base_dir    # 이미지를 찾을 폴더
        self.owner = owner          # 이 감시를 건 매크로 이름 (로그용)
        self.name = macro.get("name") or ref
        self.condition = _instant(graph_model.watch_condition(macro))
        # 조건 확인 전용 엔진. 로그를 남기지 않는다 - 매 바퀴 "없음" 이
        # 찍히면 실행 로그가 감시로 뒤덮인다.
        self.probe = Engine(macro, base_dir, logger=lambda _m: None)
        # 메인이 나아가지 못하는 동안 연달아 걸린 횟수
        self.streak = 0
        self.fired_at = None
        self.warned = False


class WatchManager(object):
    """감시 매크로 목록과 확인 주기를 갖는다. 실행 전체에 하나 (루트 엔진 소유).

    목록은 호출 단계마다 한 겹씩 쌓인다 (`scopes`). 최상위 매크로의 겹이
    실행 내내 걸리는 전역 감시이고, 호출/하위 매크로의 겹은 그 매크로가
    끝나면 걷힌다. 한 바퀴는 바깥 겹부터 안쪽 겹 순서로 확인한다.

    별도 스레드로 돌지 않는다. 메인이 노드 사이와 대기 중에 tick() 을
    부를 때만 확인한다 - 입력 장치가 하나뿐이라 동시에 돌면 입력이 섞인다.
    """

    def __init__(self, root, interval):
        self.root = root
        self.interval = float(interval)
        self.scopes = []
        self.busy = False           # 감시를 처리하는 중 (다시 들어가지 않는다)
        self.held = set()           # mouseDown 으로 누른 채인 버튼
        self.progress = 0           # 메인이 시작한 노드 수
        self.last_round = None      # 마지막 바퀴가 끝난 시각

    def active(self):
        for scope in self.scopes:
            if scope:
                return True
        return False

    def handlers(self):
        out = []
        for scope in self.scopes:
            out.extend(scope)
        return out

    def push(self, engine, macro, base_dir, macro_path):
        """macro 가 건 감시를 한 겹 쌓는다. 걸 수 없으면 MacroError.

        이미 바깥 겹에 걸린 감시는 다시 걸지 않는다 - 바깥 자리에서 한 번만
        확인한다.
        """
        errors, _warnings = graph_model.check_handler_refs(
            macro, base_dir, macro_path)
        if errors:
            raise MacroError(u"; ".join(errors))
        owner = macro.get("name") or u"?"
        known = set(h.key for h in self.handlers())
        added = []
        for ref in graph_model.handler_refs(macro):
            path = graph_model.resolve_macro_ref(ref, base_dir)
            key = os.path.normcase(os.path.abspath(path))
            if key in known:
                continue
            known.add(key)
            added.append(self._load(ref, path, key, owner))
        self.scopes.append(added)
        # 감시 매크로의 엔진을 만들면서 글자 인식 설정이 바뀌었을 수 있다
        engine._reapply_ocr()
        if added:
            engine.log(u"감시 시작 (%s): %s" % (
                owner, u", ".join(h.name for h in added)))

    def pop(self, engine):
        scope = self.scopes.pop()
        if scope:
            engine.log(u"감시 끝 (%s): %s" % (
                scope[0].owner, u", ".join(h.name for h in scope)))

    @staticmethod
    def _load(ref, path, key, owner):
        try:
            handle = open(path, "rb")
            try:
                data = json.loads(handle.read().decode("utf-8"))
            finally:
                handle.close()
        except (Exception, Throwable), e:
            raise MacroError(u"감시 매크로를 읽지 못했습니다: %s: %s" % (ref, e))
        # 하위 매크로면 호출될 때와 같이 부모의 설정과 이미지 폴더를 쓴다
        data, folder, _parent = _adopt_parent_context(
            data, os.path.dirname(os.path.abspath(path)))
        return _Handler(ref, key, data, folder, owner)

    # ------------------------------------------------------------------ 확인

    def tick(self, engine):
        """확인할 때가 됐으면 한 바퀴 돈다.

        반환값은 감시를 **처리하는 데** 쓴 시간(초)이다. 아무것도 걸리지
        않은 바퀴는 0 을 준다 - 확인만 하는 시간은 짧고, 그걸 빼 주면 대기
        노드의 '멈춤 확인' 처럼 시간을 재는 쪽이 매 바퀴 처음부터 다시 잰다.
        """
        if self.busy or self.held or not self.active():
            return 0.0
        now = time.time()
        if self.last_round is not None and now - self.last_round < self.interval:
            return 0.0

        self.busy = True
        fired = 0
        try:
            for handler in self.handlers():
                if self._seen(handler, engine):
                    fired += 1
                    self._fire(handler, engine)
        finally:
            self.busy = False
            self.last_round = time.time()
        if not fired:
            return 0.0
        engine._reapply_ocr()
        spent = self.last_round - now
        engine.log(u"    [감시] 처리에 %.1f초 - 그동안 메인의 시계는 멈춰 "
                   u"있었습니다 (대기 중이던 노드는 그만큼 더 기다립니다)" % spent)
        return spent

    @staticmethod
    def _seen(handler, engine):
        try:
            return bool(handler.probe.evaluate(handler.condition))
        except MacroError, e:
            raise MacroError(u"감시 매크로 '%s' 의 조건 오류: %s"
                             % (handler.name, e))
        except BudgetExceeded:
            raise
        except (Exception, Throwable), e:
            # 화면을 한 번 못 읽었다고 실행을 멈추지는 않는다. 다음 바퀴에 다시 본다.
            # 알리기는 처음 한 번만 - 매 바퀴 찍히면 로그가 이것으로 뒤덮인다.
            if not handler.warned:
                handler.warned = True
                engine.log(u"    [감시] '%s' 조건을 확인하지 못했습니다 (같은 "
                           u"오류는 다시 알리지 않습니다): %s: %s"
                           % (handler.name, e.__class__.__name__, e))
            return False

    def _fire(self, handler, engine):
        if handler.fired_at == self.progress:
            handler.streak += 1
        else:
            handler.streak = 1
        handler.fired_at = self.progress
        if handler.streak > graph_model.HANDLER_REPEAT_LIMIT:
            raise WatchStuck(
                u"감시 '%s' 가 메인이 한 노드도 나아가지 못하는 동안 %d번 "
                u"연달아 걸렸습니다. 처리 동작이 대상을 없애지 못하는 것 "
                u"같습니다 (감시 매크로의 동작과 감시 조건을 확인하세요)"
                % (handler.name, graph_model.HANDLER_REPEAT_LIMIT))

        engine.log(u"!! 감시 '%s' 걸림 (%s 의 감시) - 메인을 멈추고 처리합니다"
                   % (handler.name, handler.owner))

        def body_logger(message):
            engine.log(u"    [감시] | %s" % message)

        params, _notes = _standalone_params(handler.macro)
        root = self.root
        # 감시 처리 중의 실패는 메인의 '실패한 위치' 가 아니다. 남기면 이어서
        # 실행이 감시 매크로 안으로 들어가려 한다.
        saved = (root.failed_at, root.failed_name)
        try:
            if graph_model.is_graph(handler.macro):
                # 예산은 메인과 함께 쓴다 (root 공유). 호출 사슬은 따로 둔다 -
                # 메인이 지나고 있는 매크로를 감시가 불러도 순환이 아니다.
                body = GraphEngine(handler.macro, handler.base_dir, body_logger,
                                   root=root, call_stack=[handler.key],
                                   params=params)
            else:
                body = Engine(handler.macro, handler.base_dir, body_logger,
                              params=params)
            body.watch = None
            ok = body.run()
        finally:
            root.failed_at, root.failed_name = saved
        if ok:
            engine.log(u"!! 감시 '%s' 처리 끝 - 메인을 이어 갑니다" % handler.name)
        else:
            engine.log(u"!! 감시 '%s' 처리가 실패했습니다. 메인은 그대로 "
                       u"이어 갑니다" % handler.name)


def _adopt_parent_context(macro, base_dir):
    """하위 매크로를 직접 실행할 때 부모의 설정과 이미지 폴더를 물려받는다.

    호출로 실행될 때는 _run_call 이 같은 일을 한다. 여기는 편집기에서 하위
    매크로를 열어 F5 로 바로 돌리는 경우다 - 이 처리가 없으면 단독 실행과
    호출 실행의 동작이 달라져서 테스트가 통하고도 본 실행이 깨진다.

    반환: (macro, base_dir, 부모 폴더 또는 None)
    """
    root_dir = graph_model.family_root(base_dir)
    if root_dir == os.path.abspath(base_dir):
        return macro, base_dir, None
    if graph_model.family_root(root_dir) != root_dir:
        raise MacroError(u"하위 매크로 안의 하위 매크로는 지원하지 않습니다: %s"
                         % base_dir)
    parent_path = os.path.join(root_dir, "macro.json")
    try:
        handle = open(parent_path, "rb")
        try:
            parent = json.loads(handle.read().decode("utf-8"))
        finally:
            handle.close()
    except (Exception, Throwable), e:
        raise MacroError(u"부모 매크로를 읽지 못했습니다: %s: %s"
                         % (parent_path, e))
    macro = dict(macro)
    macro["settings"] = dict(parent.get("settings") or {})
    return macro, root_dir, root_dir


def _standalone_params(macro):
    """단독 실행(편집기의 F5 / Shift+F5)일 때 쓸 매개변수 값.

    호출로 들어올 때는 _run_call 이 bind_params 로 값을 만들어 준다.
    단독 실행에는 값을 넘겨주는 쪽이 없어서 예전에는 매개변수가 전부 비어
    있었고, 선언에 기본값을 적어 둔 것까지 None 으로 읽혔다. 조건 비교가
    말없이 어긋나는 원인이라 여기서 선언의 기본값을 그대로 적용한다.

    기본값이 없는 매개변수는 채울 방법이 없으므로 비워 두고 알리기만 한다 -
    여기서 실행을 막으면 매개변수를 가진 매크로는 단독으로 열어 볼 수 없다.

    반환: (값 dict, 알릴 줄 목록)
    """
    values = {}
    notes = []
    missing = []
    for param in graph_model.declared_params(macro):
        name = param.get("name")
        if not name:
            continue
        if "default" not in param:
            missing.append(name)
            continue
        try:
            values[name] = graph_model.coerce_param(
                param["default"], param.get("type"), u"매개변수 '%s'" % name)
        except graph_model.ParamError as exc:
            missing.append(name)
            notes.append(u"매개변수 '%s' 의 기본값을 쓸 수 없습니다: %s"
                         % (name, exc))
    if values:
        notes.append(u"단독 실행 - 매개변수 기본값을 씁니다: %s"
                     % u", ".join(u"%s=%s" % (k, values[k])
                                  for k in sorted(values)))
    if missing:
        notes.append(u"단독 실행 - 기본값이 없어 비워 둔 매개변수: %s"
                     % u", ".join(sorted(missing)))
    return values, notes


def make_engine(macro, base_dir, logger=None, start_node=None, params=None,
                resume_path=None, macro_path=None):
    """형식을 보고 트리/그래프 실행기를 고른다.

    `start_node` 는 이번 실행만 그 노드에서 시작하게 한다. 노드라는 개념이
    없는 트리 형식에는 쓸 수 없다.

    `params` 를 주지 않으면 선언된 기본값으로 채운다 (_standalone_params).

    `resume_path` 를 주면 저장해 둔 위치부터 이어서 실행한다.
    """
    original = os.path.abspath(os.path.join(base_dir, "macro.json"))
    macro, base_dir, adopted = _adopt_parent_context(macro, base_dir)
    # 실행 하나에 기준 하나다. 호출된 매크로와 감시 매크로도 이 값을 쓴다.
    problems = graph_model.validate_scaling(macro)
    if problems:
        raise MacroError(u"; ".join(problems))
    SCALE.configure(graph_model.scaling_of(macro))
    notes = []
    if params is None:
        params, notes = _standalone_params(macro)
    if graph_model.is_graph(macro):
        engine = GraphEngine(macro, base_dir, logger, start_node=start_node,
                             params=params, resume_path=resume_path)
        engine.macro_path = macro_path or original
        if adopted:
            parent_path = os.path.join(adopted, "macro.json")
            parent = graph_model.read_macro_file(parent_path)
            if parent is not None and graph_model.handler_refs(parent):
                engine.inherited_handlers = (parent, adopted, parent_path)
    else:
        if start_node:
            raise MacroError("start node is only supported for graph macros")
        if resume_path:
            raise MacroError("resume is only supported for graph macros")
        engine = Engine(macro, base_dir, logger, params=params)
    SCALE.attach(engine.log)
    if adopted:
        engine.log(u"하위 매크로 - 부모(%s)의 설정과 이미지 폴더를 사용합니다"
                   % os.path.basename(adopted))
    for line in notes:
        engine.log(line)
    return engine
