# -*- coding: utf-8 -*-
# RunMacro.sikuli - 범용 매크로 실행기.
#
# JSON으로 정의된 매크로를 읽어서 실행한다. 매크로마다 .sikuli를 만들 필요 없이
# 이 실행기 하나로 전부 돌린다.
#
# 사용:
#   java -jar D:\Apps\oculixide-4.0.0-windows.jar ^
#        -r D:\Programming\Oculix-Automation\Scripts\Runner\RunMacro.sikuli -c ^
#        -- D:\Programming\Oculix-Automation\Macros\Example\macro.json [--from=<노드id>]
#
# --from 을 주면 저장된 시작 노드 대신 그 노드부터 실행한다 (그래프 형식만).
# 매크로 파일은 건드리지 않는다. 긴 흐름의 중간부터 확인할 때 쓴다.
#
# --resume 을 주면 지난번 실패 때 남긴 위치(Logs\resume.json)의 **실패한 노드**
# 부터 이어서 실행한다. 그 순간 지나고 있던 반복이 몇 겹이든(하위 매크로 안의
# 반복까지) 각각 몇 회째였는지 되살린다.
#
# --pause-file=<경로> 는 편집기가 준다. 그 파일이 있는 동안 노드 사이와 대기
# 중에 멈춘다 (일시정지). 주지 않으면 확인하지 않는다.

from sikuli import *
import sys
import os
import json

sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import macro_engine


def say(message):
    """Jython 의 stdout 은 기본이 ascii 라, 한글을 그냥 print 하면
    UnicodeEncodeError 로 죽는다. 엔진 로거와 같은 방식으로 직접 인코딩한다."""
    if isinstance(message, unicode):
        try:
            message = message.encode("utf-8")
        except Exception:
            message = message.encode("ascii", "replace")
    print(message)


def load_resume(macro_path):
    """지난번 실패 때 남긴 위치를 읽는다. (경로, 문제설명) 을 돌려준다.

    다른 매크로의 기록으로 이어서 실행하면 엉뚱한 노드를 돌게 되므로
    매크로가 같은지 반드시 확인한다.
    """
    path = macro_engine.RESUME_FILE
    if not os.path.exists(path):
        return None, u"이어서 실행할 위치가 없습니다: %s" % path
    f = open(path, "r")
    try:
        raw = f.read()
    finally:
        f.close()
    try:
        saved = json.loads(raw.decode("utf-8"))
    except Exception, e:
        return None, u"저장된 위치를 읽지 못했습니다: %s" % e

    same = (os.path.normcase(os.path.abspath(saved.get("macro") or u""))
            == os.path.normcase(os.path.abspath(macro_path)))
    if not same:
        return None, (u"저장된 위치는 다른 매크로의 것입니다: %s"
                      % saved.get("macro"))
    steps = saved.get("failedAt")
    if not steps:
        return None, u"실패한 위치가 기록돼 있지 않아 이어서 실행할 수 없습니다"
    return steps, None


def main():
    args = list(sys.argv[1:])
    start_node = None
    resume = False
    rest = []
    for arg in args:
        if arg.startswith("--from="):
            start_node = arg[len("--from="):].strip()
        elif arg == "--resume":
            resume = True
        elif arg.startswith("--pause-file="):
            macro_engine.PAUSE.configure(arg[len("--pause-file="):].strip())
        else:
            rest.append(arg)

    if not rest:
        say(u"usage: RunMacro.sikuli -- <macro.json 경로> "
            u"[--from=<노드id>] [--resume]")
        say(u"  전달된 argv: %r" % (sys.argv,))
        return 2

    macro_path = rest[0]
    if not os.path.exists(macro_path):
        say(u"매크로 파일을 찾을 수 없습니다: %s" % macro_path)
        return 2

    f = open(macro_path, "r")
    try:
        raw = f.read()
    finally:
        f.close()

    try:
        macro = json.loads(raw.decode("utf-8"))
    except Exception, e:
        say(u"JSON 파싱 실패: %s: %s" % (e.__class__.__name__, e))
        return 2

    base_dir = os.path.dirname(os.path.abspath(macro_path))

    resume_path = None
    if resume:
        resume_path, problem = load_resume(macro_path)
        if problem:
            say(problem)
            return 2

    try:
        engine = macro_engine.make_engine(macro, base_dir,
                                          start_node=start_node or None,
                                          resume_path=resume_path,
                                          macro_path=os.path.abspath(macro_path))
    except macro_engine.MacroError, e:
        say(u"매크로 정의 오류: %s" % e)
        return 2

    try:
        ok = engine.run()
    except macro_engine.MacroError, e:
        say(u"매크로 정의 오류: %s" % e)
        return 2

    return 0 if ok else 1


sys.exit(main())
