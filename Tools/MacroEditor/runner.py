# -*- coding: utf-8 -*-
"""OculiX 호출 - 매크로 실행, 영역 캡처, 좌표계 확인.

전부 별도 프로세스로 돌리고 출력은 콜백으로 흘려보낸다.
GUI 스레드를 막지 않도록 실행은 백그라운드 스레드에서 한다.
"""

import os
import subprocess
import threading

JAVA = r"D:\Apps\jdk-21.0.12+8\bin\java.exe"
IDE_JAR = r"D:\Apps\oculixide-4.0.0-windows.jar"
PROJECT = r"D:\Programming\Oculix-Automation"

RUN_MACRO = os.path.join(PROJECT, "Scripts", "Runner", "RunMacro.sikuli")
CAPTURE_REGION = os.path.join(PROJECT, "Scripts", "Tests", "CaptureRegion.sikuli")
READ_PIXEL = os.path.join(PROJECT, "Scripts", "Tests", "ReadPixel.sikuli")

# 한글 로그가 Jython의 ascii stdout에서 죽지 않게 하려면 필수
_ENCODING_FLAGS = ["-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8"]

# 콘솔 창이 깜빡이지 않도록
_NO_WINDOW = 0x08000000


def available():
    """OculiX와 JDK가 제자리에 있는지."""
    missing = [p for p in (JAVA, IDE_JAR) if not os.path.exists(p)]
    return (not missing), missing


def _command(script, args):
    cmd = [JAVA] + _ENCODING_FLAGS + ["-jar", IDE_JAR, "-r", script, "-c"]
    if args:
        cmd.append("--")
        cmd.extend(str(a) for a in args)
    return cmd


def _run_blocking(script, args, on_line=None, timeout=300):
    """OculiX를 돌리고 (exit_code, 출력줄 목록)을 반환."""
    cmd = _command(script, args)
    lines = []
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=_NO_WINDOW)
    except OSError as exc:
        message = u"OculiX 실행 실패: %s" % exc
        if on_line:
            on_line(message)
        return 127, [message]

    for raw in iter(proc.stdout.readline, b""):
        text = raw.decode("utf-8", "replace").rstrip("\r\n")
        if text.startswith("[DEBUG STARTUP]"):
            continue
        lines.append(text)
        if on_line:
            on_line(text)
    proc.stdout.close()
    code = proc.wait(timeout=timeout)
    return code, lines


class Job(object):
    """백그라운드에서 도는 OculiX 실행 하나."""

    def __init__(self, script, args, on_line, on_done):
        self.script = script
        self.args = args
        self.on_line = on_line
        self.on_done = on_done
        self._proc = None
        self._thread = None
        self.cancelled = False

    def start(self):
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def _work(self):
        cmd = _command(self.script, self.args)
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=_NO_WINDOW)
        except OSError as exc:
            self.on_line(u"OculiX 실행 실패: %s" % exc)
            self.on_done(127)
            return

        for raw in iter(self._proc.stdout.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            if text.startswith("[DEBUG STARTUP]"):
                continue
            self.on_line(text)
        self._proc.stdout.close()
        code = self._proc.wait()
        if self.cancelled:
            self.on_line(u"-- 사용자가 중지했습니다 --")
        self.on_done(code)

    def stop(self):
        """실행 중단. OculiX에는 신뢰할 만한 중단 단축키가 없어서 프로세스를 끝낸다."""
        self.cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()


def run_macro(macro_path, on_line, on_done, start_node=None):
    """매크로를 실행한다.

    `start_node` 를 주면 저장된 시작 노드 대신 그 노드부터 돈다.
    매크로 파일은 고치지 않는다 - 실행 인자로만 전달한다.
    """
    args = [macro_path]
    if start_node:
        args.append("--from=%s" % start_node)
    job = Job(RUN_MACRO, args, on_line, on_done)
    job.start()
    return job


def capture_region(x, y, w, h, dest_png, on_line=None):
    """OculiX에게 영역 캡처를 시킨다.

    편집기가 GDI로 직접 캡처하지 않는 이유는 screenutil 모듈 설명 참조 -
    GDI는 물리 해상도로 캡처해서 실행 시점의 논리 해상도와 배율이 어긋난다.
    """
    code, lines = _run_blocking(CAPTURE_REGION, [x, y, w, h, dest_png], on_line)
    saved = any(line.startswith("SAVED=") for line in lines)
    if code == 0 and saved and os.path.exists(dest_png):
        return True, dest_png
    detail = u"\n".join(lines[-8:])
    return False, detail


def read_pixel_via_oculix(x, y, on_line=None):
    """OculiX 좌표계로 픽셀 색을 읽는다. 좌표계 대조에 쓴다."""
    code, lines = _run_blocking(READ_PIXEL, [x, y], on_line)
    if code != 0:
        return None
    for line in lines:
        if line.startswith("PIXEL="):
            return tuple(int(v) for v in line[6:].split(","))
    return None
