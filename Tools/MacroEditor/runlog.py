# -*- coding: utf-8 -*-
"""편집기에서 돌린 매크로의 실행 로그를 파일로 남긴다.

실행 로그 패널만으로는 나중에 되짚어 볼 수가 없다. 편집기를 닫으면 사라지고,
오래 도는 매크로는 앞부분이 버퍼(2000줄)에서 밀려 나간다. 문제가 났을 때
"그때 무슨 줄이 찍혔는지"가 바로 필요한 정보라서 같은 내용을 파일에도 적는다.

    Logs\\Runs\\20260828-153012_아침퀘스트.log   실행 하나당 파일 하나
    Logs\\Runs\\latest.log                       가장 최근 실행의 사본

한 줄 쓸 때마다 flush 한다. 매크로가 멈춰서 편집기를 강제로 끝내는 상황이
곧 로그가 필요한 상황인데, 버퍼에 남아 있으면 그때 아무것도 안 남는다.

파일은 `Logs\\` 아래라 git 추적 대상이 아니다(.gitignore). 화면에서 읽은
글자와 로컬 경로가 그대로 들어가므로 공개 저장소에 올리지 않는다.
"""

import datetime
import os
import re
import shutil
import sys

# Tools\MacroEditor\runlog.py → 프로젝트 루트
PROJECT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(PROJECT, "Logs", "Runs")
LATEST = os.path.join(LOG_DIR, "latest.log")

# 최근 실행 몇 개를 남길지. 넘치면 오래된 것부터 지운다.
KEEP = 60

_RULE = u"-" * 60

# 정리 대상은 이 모듈이 만든 파일뿐이다. latest.log 나 사용자가 따로 둔
# 파일을 지우지 않으려고 이름 형식으로 가른다.
_STAMPED = re.compile(r"^\d{8}-\d{6}_.*\.log$")
_UNSAFE = re.compile(r'[\/:*?"<>|\r\n\t]+')


def ensure_dir():
    """로그 폴더를 만들고 경로를 돌려준다."""
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR)
    return LOG_DIR


def _safe_name(text):
    """매크로 이름을 파일 이름으로 쓸 수 있게 다듬는다."""
    name = _UNSAFE.sub(u"_", u"%s" % (text or u"")).strip(u" ._")
    return name[:40] or u"매크로"


def _outcome(code, cancelled):
    if cancelled:
        return u"사용자가 중지"
    if code == 0:
        return u"정상 종료"
    if code == 1:
        return u"단계 실패로 중단"
    return u"오류"


class RunLog(object):
    """실행 하나에 대응하는 로그 파일. `start()` 로 만든다."""

    def __init__(self, path, handle, started):
        self.path = path
        self.started = started
        self._handle = handle

    def line(self, text):
        """한 줄 적는다. 이미 닫혔으면 아무 일도 하지 않는다.

        로그 기록 때문에 실행이 멈추면 안 되므로 실패해도 삼킨다. 대신
        핸들을 버려서 같은 오류가 줄마다 반복되지 않게 한다.
        """
        if self._handle is None:
            return
        try:
            self._handle.write(u"%s\n" % (text if text is not None else u""))
            self._handle.flush()
        except Exception:
            self._handle = None

    def finish(self, code, cancelled=False):
        """실행 결과를 적고 닫는다."""
        self._footer(u"종료: exit %s (%s)" % (code, _outcome(code, cancelled)))

    def abort(self, reason):
        """결과를 모르는 채 끝났을 때. 편집기를 닫는 경우 등."""
        self._footer(u"중단: %s" % reason)

    # ------------------------------------------------------------- 내부

    def _header(self, macro_path, macro_name, start_node, start_label):
        self.line(u"===== OculiX 매크로 실행 =====")
        self.line(u"시각      : %s" % self.started.strftime("%Y-%m-%d %H:%M:%S"))
        if macro_name:
            self.line(u"매크로    : %s" % macro_name)
        self.line(u"파일      : %s" % (macro_path or u"(저장 안 됨)"))
        if start_node:
            self.line(u"시작 노드 : %s%s"
                      % (start_node,
                         u" (%s)" % start_label if start_label else u""))
        self.line(u"편집기    : Python %s" % sys.version.split()[0])
        self.line(_RULE)

    def _footer(self, text):
        if self._handle is None:
            return
        seconds = (datetime.datetime.now() - self.started).total_seconds()
        self.line(_RULE)
        self.line(u"===== %s — %.1f초 =====" % (text, seconds))
        try:
            self._handle.close()
        except Exception:
            pass
        self._handle = None
        try:
            shutil.copyfile(self.path, LATEST)
        except Exception:
            pass          # 사본은 편의 기능이다. 원본만 있으면 된다.


def start(macro_path, macro_name=None, start_node=None, start_label=None):
    """실행 로그 파일을 열고 머리말을 적는다.

    폴더를 만들거나 파일을 열지 못하면 예외를 그대로 올린다. 부르는 쪽이
    이유를 사용자에게 보여줄 수 있어야 하기 때문이다.
    """
    ensure_dir()
    now = datetime.datetime.now()
    label = _safe_name(macro_name
                       or os.path.basename(os.path.dirname(macro_path or u"")))
    stamp = now.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(LOG_DIR, u"%s_%s.log" % (stamp, label))
    serial = 2
    while os.path.exists(path):       # 같은 초에 두 번 실행한 경우
        path = os.path.join(LOG_DIR, u"%s_%s_%d.log" % (stamp, label, serial))
        serial += 1

    handle = open(path, "w", encoding="utf-8")
    log = RunLog(path, handle, now)
    log._header(macro_path, macro_name, start_node, start_label)
    prune()
    return log


def recent(limit=KEEP):
    """최근 로그 파일 경로를 새 것부터 돌려준다."""
    try:
        names = [n for n in os.listdir(LOG_DIR) if _STAMPED.match(n)]
    except OSError:
        return []
    names.sort(reverse=True)          # 이름이 곧 시각순이다
    return [os.path.join(LOG_DIR, n) for n in names[:limit]]


def prune(keep=KEEP):
    """오래된 로그를 지운다. 실패해도 실행을 막지 않는다."""
    try:
        names = sorted((n for n in os.listdir(LOG_DIR) if _STAMPED.match(n)),
                       reverse=True)
    except OSError:
        return 0
    removed = 0
    for name in names[keep:]:
        try:
            os.remove(os.path.join(LOG_DIR, name))
            removed += 1
        except OSError:
            pass
    return removed
