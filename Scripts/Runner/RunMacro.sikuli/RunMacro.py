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


def main():
    args = list(sys.argv[1:])
    start_node = None
    rest = []
    for arg in args:
        if arg.startswith("--from="):
            start_node = arg[len("--from="):].strip()
        else:
            rest.append(arg)

    if not rest:
        say(u"usage: RunMacro.sikuli -- <macro.json 경로> [--from=<노드id>]")
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
    try:
        engine = macro_engine.make_engine(macro, base_dir,
                                          start_node=start_node or None)
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
