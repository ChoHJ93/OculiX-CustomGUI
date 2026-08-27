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


HARD_ITERATION_CAP = 10000   # last-resort guard against a runaway macro

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

        self.screen = Screen(self.screen_index)
        default_region = settings.get("searchRegion")
        if default_region:
            self.default_region = self._make_region(default_region)
        else:
            self.default_region = self.screen

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
        self._set_psm(settings.get("ocrPsm", 11))

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

    def _make_region(self, spec):
        if spec is None:
            return self.default_region
        if len(spec) != 4:
            raise MacroError("region must be [x, y, w, h], got %r" % (spec,))
        return Region(int(spec[0]), int(spec[1]), int(spec[2]), int(spec[3]))

    def _image_path(self, name):
        """Images live next to the macro's .json file, like a .sikuli bundle."""
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
        pattern = Pattern(self._image_path(image)).similar(similarity)
        offset = step.get("targetOffset")
        if offset:
            pattern = pattern.targetOffset(int(offset[0]), int(offset[1]))
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

    def _find(self, step):
        """Locate the step's image. Returns Match or None - never raises."""
        region = self._make_region(step.get("region"))
        return region.exists(self._pattern(step), self._timeout(step))

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
        if language == self._language:
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
        region = self._make_region(step.get("region"))
        deadline = time.time() + self._timeout(step)
        while True:
            hit = self._scan_text(region, query, for_click)
            if hit is not None:
                return hit
            if time.time() >= deadline:
                return None
            time.sleep(0.3)

    def _search_note(self, step):
        """어떤 조건으로 찾는지 한 줄로. 실패했을 때 무엇을 조일지 알려 준다."""
        return u"정확도 %.2f 이상, 제한 %.0f초, 범위 %s" % (
            float(step.get("similarity", self.default_similarity)),
            self._timeout(step),
            step.get("region") or u"화면 전체")

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
            self.log(u"    %s좌표 지정 (%d,%d)"
                     % (head, int(point[0]), int(point[1])))
            return Location(int(point[0]), int(point[1]))
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
            point = cond["point"]
            rgb = pixel_util.get_pixel_rgb(int(point[0]), int(point[1]))
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
            time.sleep(float(step.get("seconds", 1)))
            return True

        if stype == "run":
            return self._run_program(step)

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
            region = self._make_region(step.get("region"))
            gone = region.waitVanish(self._pattern(step), self._timeout(step))
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
            self.screen.mouseDown(_BUTTONS[step.get("button", "LEFT").upper()])
            return True

        if stype == "mouseUp":
            self.screen.mouseUp(_BUTTONS[step.get("button", "LEFT").upper()])
            return True

        if stype == "drag":
            src = self._target(step.get("from", {}), label=u"시작")
            dst = self._target(step.get("to", {}), label=u"끝")
            if src is None or dst is None:
                # 어느 쪽이 안 됐는지 밝힌다. 둘 다 실패로 보이면 엉뚱한 쪽을 고친다.
                self.log(u"    드래그를 못 합니다 - 시작 %s, 끝 %s"
                         % (u"OK" if src is not None else u"못 찾음",
                            u"OK" if dst is not None else u"못 찾음"))
                return False
            waypoints = step.get("waypoints") or []
            route = [self._spot_text(src)]
            route.extend(u"경유 (%d,%d)" % (int(p[0]), int(p[1]))
                         for p in waypoints)
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
            point = step["point"]
            got = pixel_util.wait_pixel_color(
                int(point[0]), int(point[1]), tuple(step["rgb"]),
                tolerance=step.get("tolerance", 10),
                timeout=self._timeout(step),
                interval=float(step.get("interval", 0.1)))
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
                 start_node=None, params=None):
        Engine.__init__(self, macro, base_dir, logger, params=params)
        self.graph = graph_model.Graph(macro)
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
        # 루트 엔진 하나가 전체 실행의 예산과 호출 스택을 갖는다.
        self.root = root or self
        self.call_stack = call_stack if call_stack is not None else []

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
            self.log(u"예산: 최대 %d단계 / %.0f초" % (self.max_steps, self.max_seconds))
            self.deadline = time.time() + self.max_seconds

        try:
            status = self._run_chain(start, 0)
        except BudgetExceeded, e:
            # 예산은 실행 전체에 하나뿐이다. 호출된 매크로 안에서 터졌다면
            # 여기서 삼키지 말고 루트까지 올려보내 실행 전체를 멈춘다.
            if not is_root:
                raise
            self.log(u"!! %s" % e)
            self.log(u"=== 예산 초과로 중단 (실행 %d단계) ===" % self.root.executed)
            return False

        ok = status != ABORT
        self.log(u"=== 노드 %d회 실행, 실패 %d -> %s ===" % (
            self.root.executed if is_root else self.stats["steps"],
            self.stats["failed"], "OK" if ok else "ABORTED"))
        return ok

    # ------------------------------------------------------------------ 실행

    def _spend(self, node_id):
        root = self.root
        root.executed += 1
        if root.executed > root.max_steps:
            raise BudgetExceeded(
                u"실행 단계가 상한 %d를 넘었습니다 (노드 %s). "
                u"연결에 순환이 있는지 확인하세요." % (root.max_steps, node_id))
        if root.deadline is not None and time.time() > root.deadline:
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
            return target
        if node.get("onFail") == "continue":
            carry = self.graph.target(node_id,
                                      graph_model.skip_pin(node.get("type")))
            if carry:
                self.log(u"    실패했지만 계속 진행 (onFail=continue)")
                return carry
            self.log(u"    실패했지만 계속 진행 - 이어진 노드가 없어 여기서 끝")
            return END_OF_CHAIN
        self.log(u"    실패 - 매크로 중단")
        return None

    def _run_chain(self, node_id, depth):
        """실행 링크를 따라 체인을 실행한다.

        연결이 끊긴 지점에서 자연히 끝나고, 그때 호출자(루프 또는 최상위)로
        돌아간다. 블루프린트의 실행 핀과 같은 동작이다.
        """
        guard = 0
        while node_id:
            node = self.graph.node(node_id)
            if node is None:
                self.log(u"!! 연결된 노드를 찾을 수 없습니다: %s" % node_id)
                return ABORT

            self._spend(node_id)
            guard += 1

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
                except MacroError:
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
                status = self._run_loop(node, depth)
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
                if not self._run_call(node):
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

    def _run_call(self, node):
        """다른 매크로를 함수처럼 호출한다.

        호출된 매크로는 자기 폴더를 기준으로 이미지를 찾고 자기 설정을 쓴다.
        예산과 호출 스택만 루트와 공유한다.
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
        stack = self.root.call_stack
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

        try:
            if graph_model.is_graph(data):
                sub = GraphEngine(data, sub_dir, sub_logger,
                                  root=self.root, call_stack=stack,
                                  params=bound)
            else:
                sub = Engine(data, sub_dir, sub_logger, params=bound)
            ok = sub.run()
        finally:
            stack.pop()

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

    def _run_loop(self, node, depth):
        body_start = self.graph.target(node.get("id"), "body")

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
            return self._run_foreach(node, spec, body_start, depth)

        if "times" in node:
            count = int(node["times"])
            if count > HARD_ITERATION_CAP:
                raise MacroError(u"반복 횟수 %d가 상한 %d를 넘습니다"
                                 % (count, HARD_ITERATION_CAP))
            self._log_entry(node, u" (%d회)" % count)
            for i in range(count):
                self.log(u"    %d/%d" % (i + 1, count))
                status = self._run_chain(body_start, depth + 1)
                if status == ABORT:
                    return ABORT
                if status == BREAK:
                    self.log(u"    break")
                    return NORMAL
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
            i = 0
            while i < limit:
                if not self.evaluate(node["while"]):
                    self.log(u"    조건 거짓, %d회 후 종료" % i)
                    return NORMAL
                i += 1
                self.log(u"    %d (최대 %d)" % (i, limit))
                status = self._run_chain(body_start, depth + 1)
                if status == ABORT:
                    return ABORT
                if status == BREAK:
                    self.log(u"    break")
                    return NORMAL
            self.log(u"    최대 반복 도달 (%d)" % limit)
            return NORMAL

        raise MacroError(u"노드 %s: times / while / forEach 중 하나가 필요합니다"
                         % node.get("id"))

    def _run_foreach(self, node, spec, body_start, depth):
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

        had = name in self.params
        previous = self.params.get(name)
        try:
            for index, value in enumerate(values):
                self.params[name] = value
                self.log(u"    %d/%d  %s = %s" % (
                    index + 1, len(values), name, self._param_text(value)))
                status = self._run_chain(body_start, depth + 1)
                if status == ABORT:
                    return ABORT
                if status == BREAK:
                    self.log(u"    break")
                    return NORMAL
        finally:
            if had:
                self.params[name] = previous
            else:
                self.params.pop(name, None)
        return NORMAL



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


def make_engine(macro, base_dir, logger=None, start_node=None, params=None):
    """형식을 보고 트리/그래프 실행기를 고른다.

    `start_node` 는 이번 실행만 그 노드에서 시작하게 한다. 노드라는 개념이
    없는 트리 형식에는 쓸 수 없다.

    `params` 를 주지 않으면 선언된 기본값으로 채운다 (_standalone_params).
    """
    macro, base_dir, adopted = _adopt_parent_context(macro, base_dir)
    notes = []
    if params is None:
        params, notes = _standalone_params(macro)
    if graph_model.is_graph(macro):
        engine = GraphEngine(macro, base_dir, logger, start_node=start_node,
                             params=params)
    else:
        if start_node:
            raise MacroError("start node is only supported for graph macros")
        engine = Engine(macro, base_dir, logger, params=params)
    if adopted:
        engine.log(u"하위 매크로 - 부모(%s)의 설정과 이미지 폴더를 사용합니다"
                   % os.path.basename(adopted))
    for line in notes:
        engine.log(line)
    return engine
