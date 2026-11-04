# -*- coding: utf-8 -*-
"""해상도 대응 검증 - 실제 OculiX 로 돌려서 로그와 파일을 확인한다.

창과 화면 크기는 RunMacro 의 --simulate-* 로 준다. 모니터를 바꾸지 않고 어떤
환경이든 흉내 낼 수 있다.

**입력을 보내지 않는다.** 게임을 켜 둔 채로 돌려도 된다. 좌표 변환은 드래그의
시작점 로그로 확인한다 - 끝 지점 이미지가 없어서 끌기 전에 실패하므로 마우스가
움직이지 않는다.

실행: python scaletest.py
"""

import atexit
import ctypes
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT, "Scripts", "Common"))

import graph_model

JAVA = r"D:\Apps\jdk-21.0.12+8\bin\java.exe"
JAR = r"D:\Apps\oculixide-4.0.0-windows.jar"
RUNNER = os.path.join(PROJECT, "Scripts", "Runner", "RunMacro.sikuli")

PASS = []
FAIL = []
SKIP = []
WORK = tempfile.mkdtemp(prefix="scaletest_")

# 일부러 실패시키는 매크로가 있어서 엔진이 이 파일에 위치를 남긴다. 그대로 두면
# 사용자의 [이어서 실행] 기록이 테스트 매크로 것으로 바뀐다.
RESUME_FILE = os.path.join(PROJECT, "Logs", "resume.json")
SAVED_RESUME = None
if os.path.isfile(RESUME_FILE):
    with open(RESUME_FILE, "rb") as handle:
        SAVED_RESUME = handle.read()


def restore_resume():
    if SAVED_RESUME is not None:
        with open(RESUME_FILE, "wb") as out:
            out.write(SAVED_RESUME)
    elif os.path.isfile(RESUME_FILE):
        os.remove(RESUME_FILE)


atexit.register(restore_resume)

SPEC = {"window": {"title": u"SCALETEST-없는-창"},
        "client": [1, 30, 1364, 1072],
        "screen": [2048, 1152]}

# 1920x1080 @100% 에서 왼쪽 2/3 스냅했을 때의 창 안쪽
TARGET = ["--simulate-client=1,31,1278,1000", "--simulate-screen=1920,1080"]
REFERENCE = ["--simulate-client=1,30,1364,1072", "--simulate-screen=2048,1152"]


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(u"  [%s] %s" % ("PASS" if condition else "FAIL", name))
    if not condition and detail:
        print(u"         %s" % detail)
    return condition


def skip(name, why):
    SKIP.append(name)
    print(u"  [SKIP] %-52s %s" % (name, why))


def section(title):
    print("")
    print(u"=== %s ===" % title)


def write_png(path, width, height, alpha_hole=False):
    """화면과 겹칠 리 없는 무늬의 PNG. 외부 라이브러리 없이 만든다."""
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            value = (x * 2654435761 ^ y * 40503) & 0xFFFFFF
            rows.extend(((value >> 16) & 255, (value >> 8) & 255, value & 255))
            if alpha_hole:
                rows.append(0 if x < width // 2 else 255)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha_hole else 2,
                         0, 0, 0)
    # 편집기 캡처처럼 DPI 120 을 기록한다. 96 DPI 환경에서 위험한 조합이다.
    dpi = struct.pack(">IIB", 4724, 4724, 1)
    with open(path, "wb") as out:
        out.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                  + chunk(b"pHYs", dpi)
                  + chunk(b"IDAT", zlib.compress(bytes(rows)))
                  + chunk(b"IEND", b""))


def png_size(path):
    with open(path, "rb") as handle:
        head = handle.read(24)
    return struct.unpack(">II", head[16:24])


def macro(name, nodes, scaling=SPEC, **extra):
    """노드를 차례로 이은 매크로."""
    data = graph_model.blank(name)
    graph = graph_model.Graph(data)
    previous = None
    for index, node in enumerate(nodes):
        node = dict(node)
        node["id"] = "n%d" % (index + 1)
        graph.add_node(node, 0, index * 100)
        if previous:
            is_branch = graph.node(previous).get("type") == "if"
            for pin in ("true", "false") if is_branch else ("next",):
                graph.connect(previous, pin, node["id"])
        previous = node["id"]
    data["entry"] = "n1"
    if scaling is not None:
        data["settings"]["scaling"] = scaling
    data.update(extra)
    return data


def save(folder, data):
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "macro.json")
    with open(path, "wb") as out:
        out.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return path


def run(path, args=(), jvm=()):
    """(종료 코드, 출력 전체) 를 준다."""
    command = ([JAVA] + list(jvm)
               + ["-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8",
                  "-jar", JAR, "-r", RUNNER, "-c", "--", path] + list(args))
    done = subprocess.run(command, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, cwd=WORK, timeout=180,
                          creationflags=0x08000000)
    text = done.stdout.decode("utf-8", "replace")
    return done.returncode, text


def point_probe(point, **extra):
    """시작점 좌표를 로그에 남기고 마우스는 움직이지 않는 드래그."""
    node = {"type": "drag", "from": {"point": point},
            "to": {"image": "absent.png", "timeout": 0}, "onFail": "continue"}
    node.update(extra)
    return node


def region_probe(image, region, **extra):
    """검색 범위를 로그에 남기는 조건 노드. 없는 그림이라 바로 넘어간다."""
    cond = {"type": "imageExists", "image": image, "region": region,
            "timeout": 0, "similarity": 0.99}
    cond.update(extra)
    return {"type": "if", "condition": cond}


# ---------------------------------------------------------------- 설정 없음

section(u"설정이 없는 매크로")

folder = os.path.join(WORK, "plain")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "foo.png"), 341, 61)
code, text = run(save(folder, macro(u"plain", [
    point_probe([88, 73]),
    region_probe("foo.png", [934, 898, 429, 206]),
], scaling=None)), TARGET)
check(u"좌표가 그대로다", u"좌표 지정 (88,73)\r" in text or
      u"좌표 지정 (88,73)\n" in text, text[-300:])
check(u"영역이 그대로다", u"범위 [934, 898, 429, 206])" in text)
check(u"해상도 대응 로그가 없다", u"해상도 대응" not in text)
check(u"축소본을 만들지 않는다",
      not os.path.exists(os.path.join(folder, graph_model.SCALED_FOLDER)))
check(u"정상 종료", code == 0, u"exit=%s" % code)


# ---------------------------------------------------------------- 기준 환경

section(u"기준 환경 (설정은 있지만 창이 같다)")

folder = os.path.join(WORK, "reference")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "foo.png"), 341, 61)
path = save(folder, macro(u"reference", [
    point_probe([88, 73]),
    region_probe("foo.png", [934, 898, 429, 206]),
]))
code, text = run(path, REFERENCE)
check(u"같은 크기라고 알린다", u"기준과 같은 크기" in text, text[:400])
check(u"좌표를 바꾸지 않는다", u"좌표 지정 (88,73) ->" not in text
      and u"좌표 지정 (88,73)" in text)
check(u"영역을 바꾸지 않는다", u"범위 [934, 898, 429, 206])" in text)
check(u"축소본을 만들지 않는다",
      not os.path.exists(os.path.join(folder, graph_model.SCALED_FOLDER)))

code, text = run(path, ["--simulate-client=0.8,30.4,1364.0,1072.8",
                        "--simulate-screen=2048,1152"])
check(u"물리값을 나눈 소수값도 기준으로 본다", u"기준과 같은 크기" in text)

code, text = run(path, ["--simulate-client=100,200,1364.0,1072.8",
                        "--simulate-screen=2048,1152"])
check(u"창 위치만 다르면 그렇게 알린다", u"창 위치만 다릅니다" in text, text[:500])
check(u"창 위치만 다르면 좌표만 옮긴다", u"좌표 지정 (88,73) -> (187,243)" in text)
check(u"창 위치만 다르면 축소본을 만들지 않는다",
      not os.path.exists(os.path.join(folder, graph_model.SCALED_FOLDER))
      and u"축소본" not in text)


# ---------------------------------------------------------------- 1080p

section(u"1920x1080 @100%")

folder = os.path.join(WORK, "target")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "foo.png"), 341, 61)
path = save(folder, macro(u"target", [
    point_probe([88, 73]),
    region_probe("foo.png", [934, 898, 429, 206]),
    region_probe("foo.png", [278, 57, 1171, 1106]),
]))
code, text = run(path, TARGET)
check(u"배율을 알린다", u"기준 1364x1072 -> 현재 1278x1000" in text
      and u"이미지 0.9349" in text, text[:500])
check(u"좌표를 변환한다", u"좌표 지정 (88,73) -> (83,71)" in text)
check(u"영역을 변환한다",
      u"[934, 898, 429, 206] -> [871, 836, 411, 201]" in text)
check(u"화면 밖으로 나가는 영역을 자른다",
      u"[278, 57, 1171, 1106] -> [256, 52, 1106, 1028]" in text)
scaled = os.path.join(folder, graph_model.SCALED_FOLDER, "1278x1000", "foo.png")
check(u"축소본을 반올림 크기로 만든다",
      os.path.isfile(scaled) and png_size(scaled) == (319, 57),
      u"%r" % (png_size(scaled) if os.path.isfile(scaled) else None,))
check(u"축소본을 만들었다고 알린다", u"341x61 -> 319x57" in text)
check(u"가로세로비 경고가 없다", u"가로세로비" not in text)

code, text = run(path, TARGET)
check(u"두 번째 실행은 다시 만들지 않는다", u"축소본을 만들었습니다" not in text)

os.utime(os.path.join(folder, "foo.png"), (1000000000, 1000000000))
code, text = run(path, TARGET)
check(u"원본을 옛 파일로 바꿔도 다시 만든다", u"축소본을 만들었습니다" in text)

code, text = run(path, ["--simulate-client=1,31,1278,950",
                        "--simulate-screen=1920,1080"])
check(u"가로세로비가 벌어지면 경고한다", u"가로세로비" in text)


# ---------------------------------------------------------------- 좌표 공간

section(u"좌표 공간")

folder = os.path.join(WORK, "space")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "taskbar.png"), 38, 36)
write_png(os.path.join(folder, "game.png"), 100, 50)
code, text = run(save(folder, macro(u"space", [
    point_probe([1000, 500]),
    region_probe("taskbar.png", [145, 1104, 1607, 48]),
    region_probe("game.png", [934, 898, 429, 206], space="window"),
    point_probe([1000, 500], space="window"),
], space="screen")), TARGET)
check(u"화면 공간은 화면 크기에 비례한다",
      u"좌표 지정 (1000,500) -> (938,469)" in text, text[-400:])
check(u"작업 표시줄 영역이 화면 안에 들어온다",
      u"[145, 1104, 1607, 48] -> [131, 1031, 1516, 49]" in text)
check(u"화면 공간의 이미지는 줄이지 않는다", not os.path.exists(os.path.join(
    folder, graph_model.SCALED_FOLDER, "1278x1000", "taskbar.png")))
check(u"노드의 space 가 매크로 기본값보다 우선한다",
      u"좌표 지정 (1000,500) -> (937," in text
      and os.path.isfile(os.path.join(
          folder, graph_model.SCALED_FOLDER, "1278x1000", "game.png")))


# ---------------------------------------------------------------- @ 폴더

section(u"다시 찍은 이미지")

folder = os.path.join(WORK, "capture")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "foo.png"), 341, 61)
capture = os.path.join(folder, "@1920x1080")
write_png(os.path.join(capture, "foo.png"), 200, 50)
write_png(os.path.join(capture, "only.png"), 100, 50)
graph_model.write_capture_info(capture, (1920, 1080), [1, 31, 1278, 1000])
path = save(folder, macro(u"capture", [
    region_probe("foo.png", [0, 0, 500, 500]),
    region_probe("only.png", [0, 0, 500, 500]),
]))

code, text = run(path, TARGET)
check(u"그 화면의 이미지를 그대로 쓴다",
      u"이미지 foo.png: @1920x1080 의 것을 씁니다" in text, text[-500:])
check(u"축소본을 만들지 않는다",
      not os.path.exists(os.path.join(folder, graph_model.SCALED_FOLDER)))

code, text = run(path, REFERENCE)
check(u"기준 환경은 기준 이미지를 쓴다", u"foo.png: @1920x1080" not in text)
upscaled = os.path.join(folder, graph_model.SCALED_FOLDER, "1364x1072",
                        "only.png")
check(u"기준 이미지가 없으면 다른 @폴더에서 키워 쓴다",
      os.path.isfile(upscaled) and png_size(upscaled) == (107, 53),
      u"%r" % (png_size(upscaled) if os.path.isfile(upscaled) else None,))

code, text = run(path, ["--simulate-client=1,31,1200,940",
                        "--simulate-screen=1920,1080"])
rescaled = os.path.join(folder, graph_model.SCALED_FOLDER, "1200x940",
                        "foo.png")
check(u"찍을 때와 창 크기가 다르면 그 창 기준으로 다시 맞춘다",
      os.path.isfile(rescaled) and png_size(rescaled) == (188, 47),
      u"%r" % (png_size(rescaled) if os.path.isfile(rescaled) else None,))


# ---------------------------------------------------------------- 창이 없을 때

section(u"기준 창이 없을 때")

folder = os.path.join(WORK, "missing")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "foo.png"), 100, 50)
started = time.time()
code, text = run(save(folder, macro(u"missing", [
    {"type": "waitImage", "image": "foo.png", "timeout": 2.0,
     "onFail": "continue"},
    {"type": "hover", "point": [88, 73]},
])))
check(u"창을 못 찾았다고 한 번만 알린다",
      text.count(u"기준 창을 찾을 수 없습니다") == 1, text[-500:])
check(u"이미지 노드는 제한시간까지 기다린다", u"not found: foo.png" in text)
check(u"좌표 노드는 바로 실패한다 (입력을 보내지 않는다)",
      u"WindowMissing" in text and code == 1, u"exit=%s" % code)


# ---------------------------------------------------------------- 96 DPI

section(u"96 DPI 와 투명 템플릿")

folder = os.path.join(WORK, "dpi")
write_png(os.path.join(folder, "hole.png"), 160, 80, alpha_hole=True)
path = save(folder, macro(u"dpi", [
    region_probe("hole.png", [0, 0, 800, 600]),
]))
# 창이 기준과 같아서 DPI 120 기록이 있는 원본을 그대로 쓰는 경우다. 축소본은
# DPI 기록이 없어 96 으로 읽히므로 96 DPI 환경에서는 애초에 걸리지 않는다.
code, text = run(path, ["--simulate-client=1,30,1364,1072",
                        "--simulate-screen=1920,1080"],
                 jvm=["-Dsun.java2d.uiScale=1.0"])
check(u"시스템 DPI 96 으로 돈다", u"시스템 DPI 96" in text, text[:300])
check(u"원본을 그대로 쓰는 투명 템플릿이 예외 없이 '없음' 이 된다",
      u"CvException" not in text and u"hole.png 없음" in text and code == 0,
      u"exit=%s %s" % (code, text[-300:]))

# 반대 경우다. 축소본은 96 으로 읽히는데 시스템이 120 이면 비율이 어긋난다.
code, text = run(path, TARGET)
check(u"시스템 DPI 120 으로 돈다", u"시스템 DPI 120" in text, text[:300])
check(u"축소본의 투명 템플릿도 예외 없이 '없음' 이 된다",
      u"CvException" not in text and u"hole.png 없음" in text and code == 0,
      u"exit=%s %s" % (code, text[-300:]))


# ---------------------------------------------------------------- 잘못된 설정

section(u"잘못된 설정")

folder = os.path.join(WORK, "invalid")
code, text = run(save(folder, macro(u"invalid", [
    {"type": "log", "message": "x"},
], scaling={"client": [1, 2, 3], "screen": [10, 10]})))
check(u"실행하지 않고 알린다", code == 2 and u"매크로 정의 오류" in text,
      u"exit=%s %s" % (code, text[-200:]))


# ---------------------------------------------------------------- 호출과 감시

section(u"호출과 감시 매크로")

folder = os.path.join(WORK, "family")
write_png(os.path.join(folder, "absent.png"), 40, 40)
write_png(os.path.join(folder, "popup.png"), 120, 60)
path = save(folder, macro(u"family", [
    {"type": "call", "macro": "./Child", "label": "child"},
    {"type": "wait", "seconds": 0.3},
], handlers=["./Watcher"]))
data = macro(u"Child", [point_probe([88, 73])], scaling=None)
save(os.path.join(folder, "Child"), data)
data = macro(u"Watcher", [{"type": "log", "message": "fired"}], scaling=None,
             watch={"type": "imageExists", "image": "popup.png",
                    "region": [0, 0, 300, 300], "similarity": 0.99})
save(os.path.join(folder, "Watcher"), data)
data_main = json.loads(open(path, "rb").read().decode("utf-8"))
data_main["settings"]["handlerInterval"] = 0
save(folder, data_main)

code, text = run(path, TARGET)
check(u"하위 매크로도 같은 변환을 쓴다",
      u"좌표 지정 (88,73) -> (83,71)" in text, text[-400:])
check(u"감시 조건도 축소본을 쓴다", os.path.isfile(os.path.join(
    folder, graph_model.SCALED_FOLDER, "1278x1000", "popup.png")))

child_path = os.path.join(folder, "Child", "macro.json")
code, text = run(child_path, TARGET)
check(u"하위 매크로를 단독으로 돌려도 부모 설정을 쓴다",
      u"좌표 지정 (88,73) -> (83,71)" in text, text[-400:])


# ---------------------------------------------------------------- 실제 창

section(u"실제 게임 창 측정")

user32 = ctypes.windll.user32
user32.FindWindowW.restype = ctypes.c_void_p
REAL = {"class": "UnityWndClass", "title": u"마비노기 모바일"}
if user32.FindWindowW(REAL["class"], REAL["title"]):
    folder = os.path.join(WORK, "real")
    write_png(os.path.join(folder, "absent.png"), 40, 40)
    spec = dict(SPEC)
    spec["window"] = REAL
    code, text = run(save(folder, macro(u"real", [point_probe([88, 73])],
                                        scaling=spec)))
    check(u"실제 창을 재서 변환을 정한다",
          u"기준과 같은 크기" in text or u"기준 1364x1072 -> 현재" in text,
          text[:400])
else:
    skip(u"실제 창을 재서 변환을 정한다", u"게임이 떠 있지 않다")


# ---------------------------------------------------------------- 뒷정리

section(u"뒷정리")

restore_resume()
if SAVED_RESUME is None:
    check(u"이어서 실행 기록을 남기지 않는다", not os.path.exists(RESUME_FILE))
else:
    with open(RESUME_FILE, "rb") as handle:
        check(u"이어서 실행 기록을 건드리지 않는다",
              handle.read() == SAVED_RESUME)


# ------------------------------------------------------------------ 결과

shutil.rmtree(WORK, ignore_errors=True)
print("")
print("=" * 62)
print("passed %d / %d%s" % (len(PASS), len(PASS) + len(FAIL),
                            (u"   건너뜀 %d" % len(SKIP)) if SKIP else ""))
if FAIL:
    print(u"실패:")
    for name in FAIL:
        print("  - %s" % name)
    sys.exit(1)
print("SCALETEST_OK")
sys.exit(0)
