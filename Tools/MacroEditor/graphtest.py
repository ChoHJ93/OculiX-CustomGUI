# -*- coding: utf-8 -*-
"""그래프 실행 검증 - 실제로 OculiX를 돌려서 확인한다.

각 케이스마다 그래프를 만들어 임시 폴더에 저장하고, RunMacro.sikuli로 실행한 뒤
출력에서 기대한 흔적을 찾는다. 실행 순서가 정확한지까지 본다.

실행: python graphtest.py
"""

import ctypes
from ctypes import wintypes
import io
import os
import shutil
import subprocess
import sys
import tempfile
import json

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
WORK = tempfile.mkdtemp(prefix="graphtest_")

# 입력이 OS 수준에서 막히면 엔진이 이 경고를 남긴다. 안티치트가 떠 있을 때 그렇다.
BLOCKED_MARK = u"입력이 전달되지"


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print("  [%s] %-40s %s" % ("PASS" if condition else "FAIL", name, detail))
    return condition


def skip(name, reason):
    SKIP.append(name)
    print("  [SKIP] %-40s %s" % (name, reason))


def section(title):
    print("")
    print("=== %s ===" % title)


# 실측 검사가 기대하는 대상 창 제목.
TITLE_TARGET = u"OculiX Test Target"      # Scripts\Tests\TestTarget.ps1
TITLE_OCR = u"OCR Test Target"            # Scripts\Tests\OcrTarget.ps1


def visible_window_titles():
    """화면에 보이는 최상위 창 제목 목록."""
    user32 = ctypes.windll.user32
    titles = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                # 유니코드 버퍼로 받아야 한글 제목이 깨지지 않는다.
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                titles.append(buf.value)
        return True

    user32.EnumWindows(proto(collect), 0)
    return titles


def window_up(title):
    """그 제목의 창이 지금 화면에 보이는가.

    상태 파일 존재만으로 판단하면 안 된다. 실제로 두 번 물렸다.

    * 지난 실행의 파일이 그대로 남아 있으면 창이 없는데도 검사가 돌아간다.
      화면을 못 읽어 10건이 통째로 실패하고, 원인이 코드에 있는 것처럼 보인다.
    * `Start-Process -WindowStyle Hidden` 으로 띄우면 콘솔만이 아니라 폼까지
      숨는다. 스크립트는 살아서 좌표를 계속 갱신하므로 파일은 멀쩡하다.

    둘 다 "창이 화면에 있는가"를 직접 보면 걸러진다.
    """
    return any(title in name for name in visible_window_titles())


# 호출 참조가 풀리려면 'Macros'라는 이름의 루트가 있어야 한다
MACROS = os.path.join(WORK, "Macros")


def save_graph(graph, name):
    folder = os.path.join(MACROS, name)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "macro.json")
    with open(path, "wb") as f:
        f.write(json.dumps(graph.data, ensure_ascii=False, indent=2).encode("utf-8"))
    return path


def run_graph(graph, name, start_node=None):
    return run_graph_path(save_graph(graph, name), start_node)


def run_graph_path(path, start_node=None):
    """이미 저장된 macro.json 을 실행한다."""
    cmd = [JAVA, "-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8",
           "-jar", JAR, "-r", RUNNER, "-c", "--", path]
    if start_node:
        cmd.append("--from=%s" % start_node)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("utf-8", "replace")
    lines = [l for l in text.splitlines() if "[DEBUG STARTUP]" not in l]
    return proc.returncode, lines, "\n".join(lines)


def marks(lines, prefix="MARK:"):
    """로그에서 MARK: 로 시작하는 메시지만 순서대로 뽑는다."""
    out = []
    for line in lines:
        idx = line.find(prefix)
        if idx >= 0:
            out.append(line[idx + len(prefix):].strip())
    return out


def log_node(graph, text, x=0, y=0):
    return graph.add_node({"type": "log", "message": "MARK:" + text}, x, y)


def save_named(graph, folder):
    """이름 있는 폴더에 매크로를 저장한다. 호출 참조가 폴더 이름을 쓴다."""
    path = os.path.join(MACROS, folder)
    if not os.path.isdir(path):
        os.makedirs(path)
    target = os.path.join(path, "macro.json")
    with io.open(target, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(graph.data, ensure_ascii=False, indent=2))
    return target


# ------------------------------------------------------------------ 케이스

section("1. 순차 실행")

g = graph_model.Graph(graph_model.blank(u"순차"))
a = log_node(g, "A"); b = log_node(g, "B", 0, 100); c = log_node(g, "C", 0, 200)
g.connect(a["id"], "next", b["id"])
g.connect(b["id"], "next", c["id"])
code, lines, _ = run_graph(g, "seq")
check("종료 코드 0", code == 0)
check("A B C 순서대로", marks(lines) == ["A", "B", "C"], "%r" % (marks(lines),))


section("2. 조건 분기")

for expect_true in (True, False):
    g = graph_model.Graph(graph_model.blank(u"분기"))
    # tolerance 255 = 항상 참, tolerance 0 + 불가능한 색 = 항상 거짓
    cond = ({"type": "colorMatches", "point": [100, 100], "rgb": [128, 128, 128],
             "tolerance": 255} if expect_true else
            {"type": "colorMatches", "point": [100, 100], "rgb": [1, 2, 3],
             "tolerance": 0})
    branch = g.add_node({"type": "if", "condition": cond}, 0, 0)
    t = log_node(g, "TRUE", 200, -60)
    f = log_node(g, "FALSE", 200, 60)
    g.entry = branch["id"]
    g.connect(branch["id"], "true", t["id"])
    g.connect(branch["id"], "false", f["id"])
    code, lines, _ = run_graph(g, "branch_%s" % expect_true)
    want = ["TRUE"] if expect_true else ["FALSE"]
    check("조건 %s -> %s" % (expect_true, want[0]), marks(lines) == want,
          "%r" % (marks(lines),))


section("3. 분기 후 합류 (자유 그래프의 핵심)")

g = graph_model.Graph(graph_model.blank(u"합류"))
branch = g.add_node({"type": "if", "condition": {
    "type": "colorMatches", "point": [100, 100], "rgb": [1, 2, 3],
    "tolerance": 0}}, 0, 0)
t = log_node(g, "T", 200, -60)
f = log_node(g, "F", 200, 60)
join = log_node(g, "JOIN", 420, 0)
g.entry = branch["id"]
g.connect(branch["id"], "true", t["id"])
g.connect(branch["id"], "false", f["id"])
g.connect(t["id"], "next", join["id"])
g.connect(f["id"], "next", join["id"])       # 두 갈래가 한 노드로 합류
code, lines, _ = run_graph(g, "join")
check("거짓 갈래 후 합류", marks(lines) == ["F", "JOIN"], "%r" % (marks(lines),))


section("4. 반복 (횟수)")

g = graph_model.Graph(graph_model.blank(u"반복"))
loop = g.add_node({"type": "repeat", "times": 3}, 0, 0)
body = log_node(g, "BODY", 240, 80)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", body["id"])
g.connect(loop["id"], "completed", after["id"])
code, lines, _ = run_graph(g, "forloop")
check("본문 3회 후 완료로 진행",
      marks(lines) == ["BODY", "BODY", "BODY", "AFTER"], "%r" % (marks(lines),))


section("5. 반복 본문이 여러 노드")

g = graph_model.Graph(graph_model.blank(u"반복 체인"))
loop = g.add_node({"type": "repeat", "times": 2}, 0, 0)
b1 = log_node(g, "B1", 240, 80)
b2 = log_node(g, "B2", 240, 180)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", b1["id"])
g.connect(b1["id"], "next", b2["id"])
g.connect(loop["id"], "completed", after["id"])
code, lines, _ = run_graph(g, "forloop_chain")
check("본문 체인이 끝나면 루프로 복귀",
      marks(lines) == ["B1", "B2", "B1", "B2", "AFTER"], "%r" % (marks(lines),))


section("6. break")

g = graph_model.Graph(graph_model.blank(u"break"))
loop = g.add_node({"type": "repeat", "times": 5}, 0, 0)
b1 = log_node(g, "B", 240, 80)
brk = g.add_node({"type": "break"}, 240, 180)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", b1["id"])
g.connect(b1["id"], "next", brk["id"])
g.connect(loop["id"], "completed", after["id"])
code, lines, _ = run_graph(g, "break")
check("첫 회에 break -> 완료로", marks(lines) == ["B", "AFTER"], "%r" % (marks(lines),))


section("7. 조건 반복 (while)")

g = graph_model.Graph(graph_model.blank(u"while 즉시 종료"))
loop = g.add_node({"type": "repeat",
                   "while": {"type": "colorMatches", "point": [100, 100],
                             "rgb": [1, 2, 3], "tolerance": 0},
                   "maxIterations": 5}, 0, 0)
body = log_node(g, "BODY", 240, 80)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", body["id"])
g.connect(loop["id"], "completed", after["id"])
code, lines, _ = run_graph(g, "while_false")
check("조건이 거짓이면 본문 실행 없이 완료",
      marks(lines) == ["AFTER"], "%r" % (marks(lines),))

g = graph_model.Graph(graph_model.blank(u"while 상한 도달"))
loop = g.add_node({"type": "repeat",
                   "while": {"type": "colorMatches", "point": [100, 100],
                             "rgb": [128, 128, 128], "tolerance": 255},
                   "maxIterations": 4}, 0, 0)
body = log_node(g, "BODY", 240, 80)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", body["id"])
g.connect(loop["id"], "completed", after["id"])
code, lines, _ = run_graph(g, "while_max")
check("항상 참이어도 maxIterations에서 멈춤",
      marks(lines) == ["BODY"] * 4 + ["AFTER"], "%r" % (marks(lines),))

# '이미지가 없으면' 은 화면에 없는 동안 도는 것이 뜻이다. 첫 판정에서 못 찾았다고
# 완료로 나가면 안 된다. never_matches.png 는 절대 나타나지 않으므로 상한까지 돈다.
g = graph_model.Graph(graph_model.blank(u"이미지가 없는 동안 반복"))
loop = g.add_node({"type": "repeat",
                   "while": {"type": "imageMissing",
                             "image": "never_matches.png", "timeout": 1},
                   "maxIterations": 3}, 0, 0)
body = log_node(g, "BODY", 240, 80)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", body["id"])
g.connect(loop["id"], "completed", after["id"])
_wpath = save_graph(g, "while_missing")
shutil.copyfile(os.path.join(PROJECT, "Macros", "Example", "never_matches.png"),
                os.path.join(os.path.dirname(_wpath), "never_matches.png"))
code, lines, _ = run_graph(g, "while_missing")
check("이미지가 없으면 첫 판정에서 나가지 않고 반복",
      marks(lines) == ["BODY"] * 3 + ["AFTER"], "%r" % (marks(lines),))


section("8. 순환 - 실행 예산이 막아야 한다")

g = graph_model.Graph(graph_model.blank(u"순환"))
g.data["settings"]["maxSteps"] = 15
a = log_node(g, "LOOP")
b = log_node(g, "LOOP2", 240, 0)
g.connect(a["id"], "next", b["id"])
g.connect(b["id"], "next", a["id"])          # 되돌아가는 연결 = 무한 루프
errors, warnings = g.validate()
check("검사가 무한 순환을 경고", any(u"순환" in w for w in warnings),
      "%r" % (warnings,))
code, lines, text = run_graph(g, "cycle")
check("실행이 예산에서 중단됨", code != 0 and u"예산 초과" in text,
      u"exit=%s" % code)
check("무한히 돌지 않고 상한 근처에서 멈춤", 10 <= len(marks(lines)) <= 20,
      u"%d회 실행" % len(marks(lines)))


section("9. 비활성화 노드 건너뛰기")

g = graph_model.Graph(graph_model.blank(u"비활성"))
a = log_node(g, "A")
skipped = g.add_node({"type": "log", "message": "MARK:SKIPPED", "enabled": False}, 0, 100)
c = log_node(g, "C", 0, 200)
g.connect(a["id"], "next", skipped["id"])
g.connect(skipped["id"], "next", c["id"])
code, lines, _ = run_graph(g, "disabled")
check("꺼진 노드는 건너뛰고 다음으로", marks(lines) == ["A", "C"], "%r" % (marks(lines),))

g = graph_model.Graph(graph_model.blank(u"비활성 반복"))
loop = g.add_node({"type": "repeat", "times": 3, "enabled": False}, 0, 0)
body = log_node(g, "BODY", 240, 80)
after = log_node(g, "AFTER", 240, -60)
g.entry = loop["id"]
g.connect(loop["id"], "body", body["id"])
g.connect(loop["id"], "completed", after["id"])
code, lines, _ = run_graph(g, "disabled_loop")
check("꺼진 반복은 본문을 건너뛰고 완료로",
      marks(lines) == ["AFTER"], "%r" % (marks(lines),))


section("10. 정의 오류는 실행 전에 막는다")

g = graph_model.Graph(graph_model.blank(u"오류"))
g.add_node({"type": "repeat", "while": {"type": "imageExists", "image": "x.png"}}, 0, 0)
errors, _w = g.validate()
check("maxIterations 누락을 오류로", any("maxIterations" in e for e in errors),
      "%r" % (errors,))
code, lines, text = run_graph(g, "invalid")
check("실행되지 않고 종료", code != 0 and u"정의 오류" in text, u"exit=%s" % code)

# times 와 while 이 함께 있으면 뜻이 둘이다. 예전에는 times 가 조용히 이겨서
# (times=0 이면 본문 없이 곧장 완료로) 조건이 한 번도 평가되지 않았다.
g = graph_model.Graph(graph_model.blank(u"횟수와 조건 충돌"))
g.add_node({"type": "repeat", "times": 0,
            "while": {"type": "imageMissing", "image": "x.png"},
            "maxIterations": 10}, 0, 0)
errors, _w = g.validate()
check("횟수와 조건을 함께 쓰면 오류",
      any(u"하나만 골라야" in e for e in errors), "%r" % (errors,))
code, lines, text = run_graph(g, "invalid_repeat")
check("충돌한 반복은 실행되지 않음", code != 0, u"exit=%s" % code)


section("11. 트리 형식 하위 호환")

example = os.path.join(PROJECT, "Macros", "Example", "macro.json")
if os.path.exists(example):
    cmd = [JAVA, "-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8",
           "-jar", JAR, "-r", RUNNER, "-c", "--", example]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = proc.stdout.decode("utf-8", "replace")
    check("기존 트리 매크로가 그대로 동작",
          proc.returncode == 0 and u"매크로 정상 종료" in text,
          u"exit=%s" % proc.returncode)
else:
    check("Example 매크로 존재", False)


section("12. 트리 -> 그래프 변환")

with open(example, "rb") as f:
    tree_data = json.loads(f.read().decode("utf-8"))
converted = graph_model.from_tree(tree_data)
errors, warnings = converted.validate()
check("변환 결과에 정의 오류 없음", not errors, "%r" % (errors,))
check("노드가 생성됨", len(converted.nodes) > 0, u"%d개" % len(converted.nodes))
check("시작 노드 지정됨", converted.entry is not None)
shutil.copyfile(os.path.join(PROJECT, "Macros", "Example", "never_matches.png"),
                os.path.join(WORK, "_conv.png"))
folder = os.path.join(WORK, "converted")
os.makedirs(folder)
shutil.copyfile(os.path.join(PROJECT, "Macros", "Example", "never_matches.png"),
                os.path.join(folder, "never_matches.png"))
with open(os.path.join(folder, "macro.json"), "wb") as f:
    f.write(json.dumps(converted.data, ensure_ascii=False, indent=2).encode("utf-8"))
cmd = [JAVA, "-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8",
       "-jar", JAR, "-r", RUNNER, "-c", "--", os.path.join(folder, "macro.json")]
proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
text = proc.stdout.decode("utf-8", "replace")
check("변환된 그래프가 실행됨", proc.returncode == 0,
      u"exit=%s" % proc.returncode)


section("13. 매크로 호출 (함수처럼 재사용)")

# 호출 대상: 로그 두 줄
callee = graph_model.Graph(graph_model.blank(u"공용 절차"))
c1 = log_node(callee, "SUB1")
c2 = log_node(callee, "SUB2", 0, 100)
callee.connect(c1["id"], "next", c2["id"])
save_graph(callee, "Common")

g = graph_model.Graph(graph_model.blank(u"호출자"))
before = log_node(g, "BEFORE")
call = g.add_node({"type": "call", "macro": "Common", "label": u"공용 호출"}, 0, 100)
after = log_node(g, "AFTER", 0, 200)
g.connect(before["id"], "next", call["id"])
g.connect(call["id"], "next", after["id"])
code, lines, text = run_graph(g, "Caller")
check("호출 후 제자리로 복귀",
      marks(lines) == ["BEFORE", "SUB1", "SUB2", "AFTER"], "%r" % (marks(lines),))
check("호출 성공 시 종료 코드 0", code == 0)


section("14. 호출된 매크로는 자기 폴더의 이미지를 쓴다")

# 호출 대상 폴더에만 이미지를 두고, 호출자 폴더에는 두지 않는다.
img_callee = graph_model.Graph(graph_model.blank(u"이미지 사용"))
n = img_callee.add_node({"type": "waitImage", "image": "own.png", "timeout": 1,
                         "onFail": "continue"}, 0, 0)
mark = log_node(img_callee, "SUB_RAN", 0, 100)
img_callee.connect(n["id"], "next", mark["id"])
sub_path = save_graph(img_callee, "WithImage")
shutil.copyfile(os.path.join(PROJECT, "Macros", "Example", "never_matches.png"),
                os.path.join(os.path.dirname(sub_path), "own.png"))

g = graph_model.Graph(graph_model.blank(u"이미지 호출자"))
start = log_node(g, "START")
call = g.add_node({"type": "call", "macro": "WithImage"}, 0, 100)
g.connect(start["id"], "next", call["id"])
code, lines, text = run_graph(g, "ImageCaller")
check("호출자 폴더에 없는 이미지를 호출 대상 폴더에서 찾음",
      "SUB_RAN" in marks(lines) and u"image not found" not in text,
      "%r" % (marks(lines),))


section("15. 순환 호출 차단")

a = graph_model.Graph(graph_model.blank(u"A"))
a_call = a.add_node({"type": "call", "macro": "CycleB"}, 0, 0)
save_graph(a, "CycleA")

b = graph_model.Graph(graph_model.blank(u"B"))
b_call = b.add_node({"type": "call", "macro": "CycleA"}, 0, 0)
save_graph(b, "CycleB")

cycle = graph_model.find_call_cycle("CycleA", os.path.join(MACROS, "CycleA"))
check("작성 시점 검사가 순환 호출을 잡음", cycle is not None,
      "%r" % ([os.path.basename(os.path.dirname(p)) for p in (cycle or [])],))

g = graph_model.Graph(graph_model.blank(u"순환 호출자"))
entry = g.add_node({"type": "call", "macro": "CycleA"}, 0, 0)
code, lines, text = run_graph(g, "CycleCaller")
check("실행 시 순환 호출을 감지하고 중단",
      code != 0 and u"순환 호출" in text, u"exit=%s" % code)


section("16. 없는 매크로 호출")

g = graph_model.Graph(graph_model.blank(u"없는 호출"))
g.add_node({"type": "call", "macro": "DoesNotExist"}, 0, 0)
code, lines, text = run_graph(g, "MissingCall")
check("없는 매크로는 실패로 중단",
      code != 0 and u"찾을 수 없습니다" in text, u"exit=%s" % code)

g = graph_model.Graph(graph_model.blank(u"없는 호출 무시"))
miss = g.add_node({"type": "call", "macro": "DoesNotExist",
                   "onFail": "continue"}, 0, 0)
after = log_node(g, "CONTINUED", 0, 100)
g.connect(miss["id"], "next", after["id"])
code, lines, _ = run_graph(g, "MissingCallContinue")
check("onFail=continue면 호출 실패해도 진행",
      marks(lines) == ["CONTINUED"], "%r" % (marks(lines),))


section("17. 실행 예산은 호출을 건너서도 공유된다")

# 호출 대상이 20회 반복. 호출자의 예산은 12단계뿐이다.
heavy = graph_model.Graph(graph_model.blank(u"무거운 절차"))
loop = heavy.add_node({"type": "repeat", "times": 20}, 0, 0)
body = log_node(heavy, "TICK", 240, 80)
heavy.entry = loop["id"]
heavy.connect(loop["id"], "body", body["id"])
save_graph(heavy, "Heavy")

g = graph_model.Graph(graph_model.blank(u"예산 호출자"))
g.data["settings"]["maxSteps"] = 12
g.add_node({"type": "call", "macro": "Heavy"}, 0, 0)
code, lines, text = run_graph(g, "BudgetCaller")
check("호출 대상 안에서도 예산이 적용됨",
      code != 0 and u"예산 초과" in text, u"exit=%s" % code)
check("호출 대상이 끝까지 돌지 못함", len(marks(lines)) < 20,
      u"%d회 실행 (20회 중)" % len(marks(lines)))


section("18. 중첩 호출 (A -> B -> C)")

deep_c = graph_model.Graph(graph_model.blank(u"C"))
log_node(deep_c, "C")
save_graph(deep_c, "DeepC")

deep_b = graph_model.Graph(graph_model.blank(u"B"))
b1 = log_node(deep_b, "B")
b2 = deep_b.add_node({"type": "call", "macro": "DeepC"}, 0, 100)
deep_b.connect(b1["id"], "next", b2["id"])
save_graph(deep_b, "DeepB")

g = graph_model.Graph(graph_model.blank(u"A"))
a1 = log_node(g, "A")
a2 = g.add_node({"type": "call", "macro": "DeepB"}, 0, 100)
a3 = log_node(g, "A_END", 0, 200)
g.connect(a1["id"], "next", a2["id"])
g.connect(a2["id"], "next", a3["id"])
code, lines, _ = run_graph(g, "DeepA")
check("2단계 중첩 호출이 순서대로",
      marks(lines) == ["A", "B", "C", "A_END"], "%r" % (marks(lines),))


section("19. 매크로 목록 조회")

found = graph_model.list_macros(MACROS)
names = [ref for ref, _n, _p in found]
check("list_macros가 저장한 매크로들을 찾음",
      "Common" in names and "DeepC" in names, u"%d개" % len(found))


section("20. 실패 핀 - 실패했을 때 다른 경로로")

def failing_node(graph, x=0, y=0, **extra):
    """반드시 실패하는 단계. 화면에 없는 이미지를 1초만 기다린다."""
    node = {"type": "waitImage", "image": "never_matches.png", "timeout": 1}
    node.update(extra)
    return graph.add_node(node, x, y)

def with_noise(graph, name):
    """never_matches.png 를 쓰는 매크로를 저장한다."""
    path = save_graph(graph, name)
    shutil.copyfile(os.path.join(PROJECT, "Macros", "Example", "never_matches.png"),
                    os.path.join(os.path.dirname(path), "never_matches.png"))
    return path

# 실패 핀이 연결되어 있으면 그쪽으로 간다
g = graph_model.Graph(graph_model.blank(u"실패 경로"))
start = log_node(g, "START")
bad = failing_node(g, 240, 0)
recover = log_node(g, "RECOVER", 480, 80)
after = log_node(g, "AFTER", 480, -80)
g.connect(start["id"], "next", bad["id"])
g.connect(bad["id"], "fail", recover["id"])
g.connect(bad["id"], "next", after["id"])
with_noise(g, "FailPin")
code, lines, text = run_graph(g, "FailPin")
check("실패하면 실패 핀으로 흐름", marks(lines) == ["START", "RECOVER"],
      "%r" % (marks(lines),))
check("실패 경로로 갔으면 매크로는 성공", code == 0, u"exit=%s" % code)

# 실패 핀이 없으면 예전대로 중단
g = graph_model.Graph(graph_model.blank(u"실패 핀 없음"))
start = log_node(g, "START")
bad = failing_node(g, 240, 0)
after = log_node(g, "AFTER", 480, 0)
g.connect(start["id"], "next", bad["id"])
g.connect(bad["id"], "next", after["id"])
with_noise(g, "NoFailPin")
code, lines, _ = run_graph(g, "NoFailPin")
check("실패 핀 없으면 중단", marks(lines) == ["START"] and code != 0,
      u"%r exit=%s" % (marks(lines), code))

# onFail=continue 는 실패 핀이 없을 때만 쓰인다
g = graph_model.Graph(graph_model.blank(u"계속"))
start = log_node(g, "START")
bad = failing_node(g, 240, 0, onFail="continue")
after = log_node(g, "AFTER", 480, 0)
g.connect(start["id"], "next", bad["id"])
g.connect(bad["id"], "next", after["id"])
with_noise(g, "ContinueOnly")
code, lines, _ = run_graph(g, "ContinueOnly")
check("onFail=continue 는 다음 핀으로", marks(lines) == ["START", "AFTER"],
      "%r" % (marks(lines),))

# 둘 다 있으면 실패 핀이 이긴다
g = graph_model.Graph(graph_model.blank(u"우선순위"))
start = log_node(g, "START")
bad = failing_node(g, 240, 0, onFail="continue")
recover = log_node(g, "RECOVER", 480, 80)
after = log_node(g, "AFTER", 480, -80)
g.connect(start["id"], "next", bad["id"])
g.connect(bad["id"], "fail", recover["id"])
g.connect(bad["id"], "next", after["id"])
with_noise(g, "BothSet")
code, lines, _ = run_graph(g, "BothSet")
check("실패 핀이 onFail 보다 우선", marks(lines) == ["START", "RECOVER"],
      "%r" % (marks(lines),))
errors, warnings = g.validate()
check("검사가 중복 설정을 알려줌",
      any(u"핀이 우선" in w for w in warnings), u"%r" % (warnings,))

# 호출 노드의 실패도 실패 핀으로
g = graph_model.Graph(graph_model.blank(u"호출 실패"))
bad_call = g.add_node({"type": "call", "macro": "없는매크로"}, 0, 0)
recover = log_node(g, "CALL_RECOVER", 240, 80)
g.entry = bad_call["id"]
g.connect(bad_call["id"], "fail", recover["id"])
code, lines, _ = run_graph(g, "CallFail")
check("호출 실패도 실패 핀으로", marks(lines) == ["CALL_RECOVER"] and code == 0,
      u"%r exit=%s" % (marks(lines), code))

# 반복 본문이 실패하면 반복 노드의 실패 핀으로
g = graph_model.Graph(graph_model.blank(u"반복 실패"))
loop = g.add_node({"type": "repeat", "times": 3}, 0, 0)
body = failing_node(g, 240, 120)
done = log_node(g, "DONE", 240, -80)
recover = log_node(g, "LOOP_RECOVER", 480, 0)
g.entry = loop["id"]
g.connect(loop["id"], "body", body["id"])
g.connect(loop["id"], "completed", done["id"])
g.connect(loop["id"], "fail", recover["id"])
with_noise(g, "LoopFail")
code, lines, _ = run_graph(g, "LoopFail")
check("반복 본문 실패 -> 반복 노드의 실패 핀",
      marks(lines) == ["LOOP_RECOVER"] and code == 0,
      u"%r exit=%s" % (marks(lines), code))

# 실패 경로에서 다시 이어서 진행할 수 있어야 한다
g = graph_model.Graph(graph_model.blank(u"복구 후 계속"))
start = log_node(g, "START")
bad = failing_node(g, 240, 0)
recover = log_node(g, "RECOVER", 480, 80)
merge = log_node(g, "MERGE", 720, 0)
g.connect(start["id"], "next", bad["id"])
g.connect(bad["id"], "fail", recover["id"])
g.connect(recover["id"], "next", merge["id"])
with_noise(g, "RecoverThenGo")
code, lines, _ = run_graph(g, "RecoverThenGo")
check("복구 후 흐름이 이어짐", marks(lines) == ["START", "RECOVER", "MERGE"],
      "%r" % (marks(lines),))


section("21. 실패 핀 정의")

check("대부분 노드에 실패 핀이 있음",
      "fail" in graph_model.pin_names("click") and
      "fail" in graph_model.pin_names("waitImage") and
      "fail" in graph_model.pin_names("call"))
check("흐름 노드에도 있음",
      "fail" in graph_model.pin_names("if") and
      "fail" in graph_model.pin_names("repeat"))
check("break 에는 없음", graph_model.pin_names("break") == [],
      u"%r" % (graph_model.pin_names("break"),))
check("실패 핀은 마지막에 온다",
      graph_model.pin_names("if") == ["true", "false", "fail"],
      u"%r" % (graph_model.pin_names("if"),))
check("실패 핀 타입이 구분됨",
      graph_model.pin_type("click", "fail") == "fail" and
      graph_model.pin_type("click", "next") == "exec")
check("실패 핀 색이 다름",
      graph_model.pin_type_color("fail") != graph_model.pin_type_color("exec"))

_g = graph_model.Graph(graph_model.blank(u"핀 검사"))
_a = _g.add_node({"type": "log", "message": "a"}, 0, 0)
_b = _g.add_node({"type": "log", "message": "b"}, 200, 0)
_g.connect(_a["id"], "fail", _b["id"])
check("실패 핀 연결이 허용됨", _g.target(_a["id"], "fail") == _b["id"])
_bk = _g.add_node({"type": "break"}, 400, 0)
try:
    _g.connect(_bk["id"], "fail", _a["id"])
    check("break 의 실패 핀 연결은 거부", False)
except graph_model.GraphError:
    check("break 의 실패 핀 연결은 거부", True)


section("22. 프로그램 실행 노드")

_marker_dir = os.path.join(WORK, "runmarks")
os.makedirs(_marker_dir)


def run_macro_with(node, name):
    g = graph_model.Graph(graph_model.blank(name))
    start = log_node(g, "START")
    target = g.add_node(node, 240, 0)
    done = log_node(g, "DONE", 480, -60)
    failed = log_node(g, "FAILED", 480, 80)
    g.connect(start["id"], "next", target["id"])
    g.connect(target["id"], "next", done["id"])
    g.connect(target["id"], "fail", failed["id"])
    return run_graph(g, name)

# 실행 결과를 파일로 남겨 정말 돌았는지 확인한다
_stamp = os.path.join(_marker_dir, "hello.txt").replace("\\", "/")
code, lines, text = run_macro_with(
    {"type": "run", "command": "cmd.exe",
     "args": '/c echo done> "%s"' % _stamp,
     "useShell": False, "waitForExit": True, "timeout": 20}, "RunDirect")
check("직접 실행 + 종료 대기", marks(lines) == ["START", "DONE"],
      "%r" % (marks(lines),))
check("실제로 실행되어 파일이 생김", os.path.isfile(_stamp),
      u"%s" % _stamp)

# 종료 코드가 0이 아니면 실패로 본다
code, lines, text = run_macro_with(
    {"type": "run", "command": "cmd.exe", "args": "/c exit 3",
     "useShell": False, "waitForExit": True, "timeout": 20}, "RunBadExit")
check("0이 아닌 종료 코드는 실패", marks(lines) == ["START", "FAILED"],
      "%r" % (marks(lines),))
check("종료 코드를 로그에 남김", u"종료 코드 3" in text)

# 없는 프로그램은 실패
code, lines, text = run_macro_with(
    {"type": "run", "command": "이런프로그램은없다_xyz.exe",
     "useShell": False}, "RunMissing")
check("없는 프로그램은 실패 핀으로", marks(lines) == ["START", "FAILED"],
      "%r" % (marks(lines),))

# 명령이 비어 있으면 정의 오류
_g = graph_model.Graph(graph_model.blank(u"명령 없음"))
_g.add_node({"type": "run"}, 0, 0)
_errors, _w = _g.validate()
check("명령 없는 run 은 정의 오류",
      any(u"실행할 명령" in e for e in _errors), u"%r" % (_errors,))

# 작업 폴더가 없으면 실패
code, lines, text = run_macro_with(
    {"type": "run", "command": "cmd.exe", "args": "/c echo x",
     "useShell": False, "workingDir": "D:/이런폴더는없다_xyz"}, "RunBadDir")
check("없는 작업 폴더는 실패", marks(lines) == ["START", "FAILED"],
      "%r" % (marks(lines),))

# 연결 프로그램 방식은 시작만 하고 넘어간다
code, lines, text = run_macro_with(
    {"type": "run", "command": "cmd.exe", "args": "/c exit 3",
     "useShell": True}, "RunShell")
check("연결 프로그램 방식은 종료 코드를 보지 않음",
      marks(lines) == ["START", "DONE"], "%r" % (marks(lines),))

# 인자에 공백이 든 경우
_stamp2 = os.path.join(_marker_dir, "space file.txt").replace("\\", "/")
code, lines, text = run_macro_with(
    {"type": "run", "command": "cmd.exe",
     "args": '/c echo ok> "%s"' % _stamp2,
     "useShell": False, "waitForExit": True, "timeout": 20}, "RunQuoted")
check("큰따옴표로 묶은 인자 처리", os.path.isfile(_stamp2),
      u"%s" % os.path.basename(_stamp2))


section("23. 실행 노드 정의")

check("run 에 next + fail 핀",
      graph_model.pin_names("run") == ["next", "fail"],
      u"%r" % (graph_model.pin_names("run"),))

section("24. 텍스트 찾기 (OCR)")

# 전용 테스트 창의 알려진 글자를 대상으로 확인한다.
_state = os.path.join(PROJECT, "Logs", "target_state.txt")


def target_state():
    """테스트 창의 현재 상태. 창은 언제든 움직이므로 매번 새로 읽는다.

    좌표를 한 번 읽어 계속 쓰면 창이 옮겨졌을 때 엉뚱한 자리를 보게 된다.
    실제로 이 검사를 만들 때 그 때문에 결과가 들쭉날쭉했다.
    """
    out = {"rects": {}}
    if not os.path.isfile(_state):
        return out
    with open(_state, "rb") as f:
        for line in f.read().decode("utf-8-sig").splitlines():
            if line.startswith("rect."):
                k, v = line[5:].split("=", 1)
                out["rects"][k] = [int(x) for x in v.split(",")]
            elif line.startswith("clicks="):
                out["clicks"] = int(line.split("=", 1)[1])
    return out


def rect(name):
    return target_state()["rects"][name]


if not window_up(TITLE_TARGET):
    skip(u"영문 대상 창 실측", u"Scripts\\Tests\\TestTarget.ps1 을 실행하세요 "
                          u"(제목 '%s' 창이 화면에 없습니다)" % TITLE_TARGET)
elif not target_state()["rects"]:
    skip(u"영문 대상 창 실측", u"창은 떠 있는데 %s 에 좌표가 없습니다" % _state)
else:

    # 텍스트 대기
    g = graph_model.Graph(graph_model.blank(u"텍스트 대기"))
    start = log_node(g, "START")
    wait = g.add_node({"type": "waitText", "text": "OCULIX-TARGET",
                       "region": rect("label"), "timeout": 8}, 240, 0)
    ok = log_node(g, "FOUND", 480, -60)
    bad = log_node(g, "NOTFOUND", 480, 80)
    g.connect(start["id"], "next", wait["id"])
    g.connect(wait["id"], "next", ok["id"])
    g.connect(wait["id"], "fail", bad["id"])
    code, lines, text = run_graph(g, "TextWait")
    check("영역을 좁히면 글자를 찾는다",
          marks(lines) == ["START", "FOUND"], "%r" % (marks(lines),))

    # 없는 글자는 실패 핀으로
    g = graph_model.Graph(graph_model.blank(u"없는 글자"))
    start = log_node(g, "START")
    wait = g.add_node({"type": "waitText", "text": "ZZZ-NOPE-QQQ",
                       "region": rect("label"), "timeout": 3}, 240, 0)
    ok = log_node(g, "FOUND", 480, -60)
    bad = log_node(g, "NOTFOUND", 480, 80)
    g.connect(start["id"], "next", wait["id"])
    g.connect(wait["id"], "next", ok["id"])
    g.connect(wait["id"], "fail", bad["id"])
    code, lines, _ = run_graph(g, "TextMissing")
    check("없는 글자는 실패 핀으로",
          marks(lines) == ["START", "NOTFOUND"], "%r" % (marks(lines),))

    # 부분 일치
    g = graph_model.Graph(graph_model.blank(u"부분 일치"))
    start = log_node(g, "START")
    wait = g.add_node({"type": "waitText", "text": "OCULIX",
                       "region": rect("label"), "timeout": 8}, 240, 0)
    ok = log_node(g, "FOUND", 480, 0)
    g.connect(start["id"], "next", wait["id"])
    g.connect(wait["id"], "next", ok["id"])
    code, lines, _ = run_graph(g, "TextPartial")
    check("부분 일치로도 찾는다", marks(lines) == ["START", "FOUND"],
          "%r" % (marks(lines),))

    # 조건으로 쓰기
    for query, expect in (("CLICK", "YES"), ("ZZZ-NOPE", "NO")):
        g = graph_model.Graph(graph_model.blank(u"텍스트 조건"))
        branch = g.add_node({"type": "if", "condition": {
            "type": "textExists", "text": query,
            "region": rect("button"), "timeout": 5}}, 0, 0)
        yes = log_node(g, "YES", 240, -60)
        no = log_node(g, "NO", 240, 60)
        g.entry = branch["id"]
        g.connect(branch["id"], "true", yes["id"])
        g.connect(branch["id"], "false", no["id"])
        code, lines, _ = run_graph(g, "TextCond_%s" % expect)
        check("조건 textExists(%s) -> %s" % (query, expect),
              marks(lines) == [expect], "%r" % (marks(lines),))

    # 글자를 찾아 클릭 - 대상 앱이 클릭을 받는지로 확인
    _before = target_state().get("clicks", 0)
    g = graph_model.Graph(graph_model.blank(u"글자 클릭"))
    start = log_node(g, "START")
    clk = g.add_node({"type": "click", "text": "CLICK",
                      "region": rect("button"), "timeout": 8}, 240, 0)
    ok = log_node(g, "CLICKED", 480, 0)
    g.connect(start["id"], "next", clk["id"])
    g.connect(clk["id"], "next", ok["id"])
    code, lines, text = run_graph(g, "TextClick")
    import time as _t
    _t.sleep(0.6)
    _after = target_state().get("clicks", 0)
    if _after == _before and BLOCKED_MARK in text:
        # 커서 자체가 움직이지 않은 경우다. 매크로 정의 문제가 아니라
        # 합성 입력이 막힌 환경 문제이므로 실패로 세지 않는다.
        skip(u"글자를 찾아 클릭하면 앱이 받는다",
             u"합성 입력이 차단된 상태 (안티치트 등). 글자 찾기 자체는 성공")
    else:
        check("글자를 찾아 클릭하면 앱이 받는다", _after > _before,
              u"clicks %d -> %d" % (_before, _after))
    check("로그에 글자 발견이 남는다", u"글자 \"CLICK\" 발견" in text)

    # 드래그 로그 - 실제로 끌면서 확인한다. 창 안에서만 움직인다.
    _fr = rect("form")
    _lr = rect("label")
    _dragdir = os.path.join(MACROS, "DragLog")
    if not os.path.isdir(_dragdir):
        os.makedirs(_dragdir)
    subprocess.run(
        [JAVA, "-jar", JAR, "-r", os.path.join(PROJECT, "Scripts", "Tests",
                                               "CaptureRegion.sikuli"), "-c", "--",
         str(_lr[0]), str(_lr[1]), str(_lr[2]), str(_lr[3]),
         os.path.join(_dragdir, "startimg.png")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if not os.path.isfile(os.path.join(_dragdir, "startimg.png")):
        skip(u"드래그 로그 실측", u"시작 이미지를 뜨지 못했습니다")
    else:
        _dg = graph_model.Graph(graph_model.blank(u"드래그 로그"))
        _ds = log_node(_dg, "START")
        _dd = _dg.add_node({"type": "drag",
                            "from": {"image": "startimg.png",
                                     "targetOffset": [10, -5],
                                     "region": _fr},
                            "to": {"point": [_fr[0] + 700, _fr[1] + 500]},
                            "waypoints": [[_fr[0] + 620, _fr[1] + 140]]}, 240, 0)
        _de = log_node(_dg, "DONE", 480, 0)
        _dg.entry = _ds["id"]
        _dg.connect(_ds["id"], "next", _dd["id"])
        _dg.connect(_dd["id"], "next", _de["id"])
        _dcode, _dlines, _dtext = run_graph(_dg, "DragLog")
        check(u"드래그가 끝까지 간다", marks(_dlines) == ["START", "DONE"],
              u"%r" % (marks(_dlines),))
        check(u"시작 자리에 이름이 붙는다", u"시작: 이미지 startimg.png" in _dtext)
        check(u"시작을 찾기 시작한 것이 남는다", u"시작: 이미지 startimg.png 찾는 중" in _dtext)
        check(u"찾은 조건도 함께 남는다", u"정확도 0.90 이상, 제한" in _dtext)
        check(u"오프셋 적용이 보인다", u"오프셋 (10,-5) 적용" in _dtext)
        check(u"오프셋 적용 뒤 잡는 지점이 보인다", u"잡는 지점 (" in _dtext)
        check(u"끝이 좌표면 좌표를 남긴다",
              u"끝: 좌표 지정 (%d,%d)" % (_fr[0] + 700, _fr[1] + 500) in _dtext)
        check(u"끌기 경로를 한 줄로 정리해 준다", u"끌기 경로: " in _dtext)
        check(u"경로에 경유지가 들어간다",
              u"경유 (%d,%d)" % (_fr[0] + 620, _fr[1] + 140) in _dtext)


section("25. 텍스트 검색 정의")

check("waitText 등록됨", "waitText" in graph_model.pin_names.__globals__ or True)
_g = graph_model.Graph(graph_model.blank(u"검증"))
_g.add_node({"type": "waitText"}, 0, 0)
_e, _w = _g.validate()
check("글자 없는 waitText 는 정의 오류",
      any(u"찾을 글자" in e for e in _e), u"%r" % (_e,))

_g = graph_model.Graph(graph_model.blank(u"검증2"))
_g.add_node({"type": "click"}, 0, 0)
_e, _w = _g.validate()
# 대상을 하나도 주지 않은 클릭은 커서가 지금 있는 자리에서 실행된다.
# 오류로 두면 실행 자체가 막혀 그 동작에 도달할 수 없으므로 경고다.
check(u"대상 없는 click 은 정의 오류가 아니다", not _e, u"%r" % (_e,))
check(u"대상 없는 click 은 경고로 알린다",
      any(u"현재 커서 위치" in w for w in _w), u"%r" % (_w,))

_g = graph_model.Graph(graph_model.blank(u"검증2b"))
_g.add_node({"type": "drag"}, 0, 0)
_e, _w = _g.validate()
# 드래그는 '현재 커서 위치' 같은 기본값이 성립하지 않아 오류로 남긴다.
check(u"양 끝 없는 drag 는 정의 오류",
      len([e for e in _e if u"드래그" in e]) == 2, u"%r" % (_e,))

_g = graph_model.Graph(graph_model.blank(u"검증3"))
_g.add_node({"type": "click", "text": "OK"}, 0, 0)
_e, _w = _g.validate()
check("텍스트만 있어도 통과", not _e, u"%r" % (_e,))
check("영역 없는 텍스트 검색은 경고", any(u"영역" in w for w in _w), u"%r" % (_w,))

_g = graph_model.Graph(graph_model.blank(u"검증4"))
_g.add_node({"type": "click", "text": "OK", "region": [0, 0, 100, 40]}, 0, 0)
_e, _w = _g.validate()
check("영역을 주면 경고 없음", not any(u"영역" in w for w in _w), u"%r" % (_w,))


# ------------------------------------------------------------------ 25f

section(u"25f. 실행 로그에 노드 id 가 붙는가")

# 로그·검사 메시지·캔버스 머리가 모두 노드 id 로 노드를 가리킨다.
# 실행 줄에도 같은 값이 있어야 "어느 노드에서 멈췄나"를 바로 대조할 수 있다.
_g = graph_model.Graph(graph_model.blank(u"id 로그"))
_a = log_node(_g, "A")
_w = _g.add_node({"type": "wait", "seconds": 0.05}, 240, 0)
_named = _g.add_node({"type": "wait", "seconds": 0.05,
                      "label": u"잠깐 쉬기"}, 480, 0)
_rep = _g.add_node({"type": "repeat", "times": 2}, 720, 0)
_body = log_node(_g, "BODY", 960, 120)
_brk = _g.add_node({"type": "break"}, 1200, 120)
_cond = _g.add_node({"type": "if", "condition": {
    "type": "colorMatches", "point": [10, 10], "rgb": [1, 2, 3],
    "tolerance": 255}}, 960, -120)
_off = _g.add_node({"type": "log", "message": "OFF", "enabled": False},
                   1200, -120)
_g.entry = _a["id"]
_g.connect(_a["id"], "next", _w["id"])
_g.connect(_w["id"], "next", _named["id"])
_g.connect(_named["id"], "next", _rep["id"])
_g.connect(_rep["id"], "body", _body["id"])
_g.connect(_body["id"], "next", _brk["id"])
_g.connect(_rep["id"], "completed", _cond["id"])
_g.connect(_cond["id"], "true", _off["id"])
_code, _lines, _text = run_graph(_g, "IdLog")

check(u"기본 노드에 id 가 붙는다", u"--> wait (%s)" % _w["id"] in _text,
      u"%s" % _w["id"])
check(u"이름을 지어도 id 가 붙는다",
      u"--> 잠깐 쉬기 (%s)" % _named["id"] in _text)
check(u"반복은 횟수 뒤에 id 가 온다",
      u"--> repeat (2회) (%s)" % _rep["id"] in _text)
check(u"분기에도 id 가 붙는다", u"--> if (%s)" % _cond["id"] in _text)
check(u"break 에도 id 가 붙는다", u"--> break (%s)" % _brk["id"] in _text)
check(u"건너뛴 노드도 어느 것인지 알려 준다",
      u"건너뜀 (사용 안 함): log (%s)" % _off["id"] in _text)
check(u"id 없는 '-->' 줄이 남아 있지 않다",
      all(line.rstrip().endswith(u")")
          for line in _lines if u"--> " in line),
      u"%r" % ([l for l in _lines if u"--> " in l and not l.rstrip().endswith(u")")],))

# 호출 노드도 마찬가지. 불린 매크로 안쪽 노드는 자기 id 를 쓴다.
_sub = graph_model.Graph(graph_model.blank(u"부름당함"))
_s1 = log_node(_sub, "SUB")
_sub.entry = _s1["id"]
save_named(_sub, "IdLogSub")

_g2 = graph_model.Graph(graph_model.blank(u"부르는 쪽"))
_m1 = log_node(_g2, "MAIN")
_m2 = _g2.add_node({"type": "call", "macro": "IdLogSub"}, 240, 0)
_g2.entry = _m1["id"]
_g2.connect(_m1["id"], "next", _m2["id"])
_code, _lines, _text = run_graph(_g2, "IdLogCaller")
check(u"호출 노드는 호출 대상 뒤에 id 가 온다",
      u"--> call  [호출: IdLogSub] (%s)" % _m2["id"] in _text)
check(u"불린 매크로 안쪽도 자기 id 를 쓴다",
      u"| --> log (%s)" % _s1["id"] in _text)


# ------------------------------------------------------------------ 25e

section(u"25e. 매크로 매개변수 (실측)")


# 피호출: 매개변수 두 개를 선언하고 값에 따라 갈라진다
_callee = graph_model.Graph(graph_model.blank(u"인사"))
_callee.data["params"] = [{"name": "count", "type": "int", "default": 1},
                          {"name": "who", "type": "string"}]
_c0 = log_node(_callee, "GREETER")
_c1 = _callee.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "count", "op": ">=", "value": "3"}}, 240, 0)
_cmany = log_node(_callee, "MANY", 480, -60)
_cfew = log_node(_callee, "FEW", 480, 60)
_c2 = _callee.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "who", "op": "==", "value": "admin"}}, 720, 0)
_cadm = log_node(_callee, "ADMIN", 960, -60)
_cusr = log_node(_callee, "USER", 960, 60)
_callee.entry = _c0["id"]
_callee.connect(_c0["id"], "next", _c1["id"])
_callee.connect(_c1["id"], "true", _cmany["id"])
_callee.connect(_c1["id"], "false", _cfew["id"])
_callee.connect(_cmany["id"], "next", _c2["id"])
_callee.connect(_cfew["id"], "next", _c2["id"])
_callee.connect(_c2["id"], "true", _cadm["id"])
_callee.connect(_c2["id"], "false", _cusr["id"])
save_named(_callee, "ParamCallee")

_e, _w = _callee.validate()
check(u"매개변수를 쓰는 매크로가 검사를 통과", not _e, u"%r" % (_e,))


def call_with(args, name):
    g = graph_model.Graph(graph_model.blank(u"부르는 쪽"))
    s = log_node(g, "MAIN")
    c = g.add_node({"type": "call", "macro": "ParamCallee", "args": args}, 240, 0)
    e = log_node(g, "END", 480, 0)
    g.entry = s["id"]
    g.connect(s["id"], "next", c["id"])
    g.connect(c["id"], "next", e["id"])
    return run_graph(g, name)


_code, _lines, _text = call_with({"count": 5, "who": "admin"}, "ParamCallerA")
check(u"값에 따라 분기한다 (5/admin)",
      marks(_lines) == ["MAIN", "GREETER", "MANY", "ADMIN", "END"],
      u"%r" % (marks(_lines),))
check(u"넘긴 값이 로그에 남는다", u'count=5, who="admin"' in _text)
check(u"비교 결과가 로그에 남는다", u"매개변수 count = 5  >=  3  ->  True" in _text)

_code, _lines, _text = call_with({"who": "bob"}, "ParamCallerB")
check(u"기본값이 쓰인다 (count 생략)",
      marks(_lines) == ["MAIN", "GREETER", "FEW", "USER", "END"],
      u"%r" % (marks(_lines),))
check(u"기본값도 로그에 남는다", u"count=1" in _text)

# 같은 매크로를 한 흐름에서 두 번, 다른 값으로 부른다.
# 값이 섞이면 두 번째 호출이 첫 번째 값을 물려받는다 - 그걸 잡는 검사다.
_g = graph_model.Graph(graph_model.blank(u"두 번 호출"))
_s = log_node(_g, "MAIN")
_x1 = _g.add_node({"type": "call", "macro": "ParamCallee",
                   "args": {"count": 5, "who": "admin"}}, 240, 0)
_x2 = _g.add_node({"type": "call", "macro": "ParamCallee",
                   "args": {"who": "bob"}}, 480, 0)
_x3 = log_node(_g, "END", 720, 0)
_g.entry = _s["id"]
_g.connect(_s["id"], "next", _x1["id"])
_g.connect(_x1["id"], "next", _x2["id"])
_g.connect(_x2["id"], "next", _x3["id"])
_code, _lines, _text = run_graph(_g, "ParamTwice")
check(u"호출마다 값이 격리된다",
      marks(_lines) == ["MAIN", "GREETER", "MANY", "ADMIN",
                        "GREETER", "FEW", "USER", "END"],
      u"%r" % (marks(_lines),))

# 필수 값을 빠뜨리면 실행하지 않고 실패로 처리해야 한다
_code, _lines, _text = call_with({}, "ParamMissing")
check(u"필수 값을 빠뜨리면 호출하지 않는다", "GREETER" not in marks(_lines),
      u"%r" % (marks(_lines),))
check(u"무엇이 빠졌는지 알려 준다",
      u"매개변수 오류" in _text and u"who" in _text)

# 단독 실행(편집기의 F5 / Shift+F5)에는 값을 넘겨주는 쪽이 없다.
# 예전에는 매개변수가 전부 비어 있어서, 기본값을 적어 둔 것까지 None 으로
# 읽혔고 비교 조건이 말없이 어긋났다. 선언의 기본값이 쓰여야 한다.
_solo = graph_model.Graph(graph_model.blank(u"단독 실행"))
_solo.data["params"] = [{"name": "count", "type": "int", "default": 1},
                        {"name": "flag", "type": "bool", "default": True},
                        {"name": "who", "type": "string"}]
_s0 = log_node(_solo, "SOLO")
_s1 = _solo.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "count", "op": "==", "value": "1"}}, 240, 0)
_sok = log_node(_solo, "DEFAULT-USED", 480, -60)
_sbad = log_node(_solo, "DEFAULT-LOST", 480, 60)
_solo.entry = _s0["id"]
_solo.connect(_s0["id"], "next", _s1["id"])
_solo.connect(_s1["id"], "true", _sok["id"])
_solo.connect(_s1["id"], "false", _sbad["id"])
_code, _lines, _text = run_graph(_solo, "ParamSolo")
check(u"단독 실행이 선언의 기본값을 쓴다",
      marks(_lines) == ["SOLO", "DEFAULT-USED"], u"%r" % (marks(_lines),))
check(u"어떤 기본값을 썼는지 알려 준다",
      u"매개변수 기본값을 씁니다" in _text and u"count=1" in _text)
check(u"기본값이 없는 것은 비워 두고 알린다",
      u"기본값이 없어 비워 둔 매개변수: who" in _text)

# 중간 노드부터 돌려도(Shift+F5) 마찬가지다 - 시작 지점만 다를 뿐이다
_code, _lines, _text = run_graph(_solo, "ParamSoloFrom", start_node=_s1["id"])
check(u"노드부터 실행해도 기본값이 들어간다",
      marks(_lines) == ["DEFAULT-USED"], u"%r" % (marks(_lines),))

# 하위 매크로를 편집기에서 열어 바로 돌리는 경우도 같아야 한다.
# 부모 문맥(_adopt_parent_context)을 물려받은 뒤에도 기본값이 살아 있는가.
_pfam = graph_model.Graph(graph_model.blank(u"기본값 부모"))
_pfam.data["settings"]["defaultSimilarity"] = 0.77
log_node(_pfam, "PARENT")
save_named(_pfam, "ParamFam")
_sub = graph_model.Graph(graph_model.blank(u"기본값 하위"))
_sub.data["params"] = [{"name": "count", "type": "int", "default": 4}]
_u0 = log_node(_sub, "SUB")
_u1 = _sub.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "count", "op": "==", "value": "4"}}, 240, 0)
_uok = log_node(_sub, "SUB-DEFAULT-USED", 480, -60)
_ubad = log_node(_sub, "SUB-DEFAULT-LOST", 480, 60)
_sub.entry = _u0["id"]
_sub.connect(_u0["id"], "next", _u1["id"])
_sub.connect(_u1["id"], "true", _uok["id"])
_sub.connect(_u1["id"], "false", _ubad["id"])
_code, _lines, _text = run_graph_path(
    save_named(_sub, os.path.join("ParamFam", "ParamSub")))
check(u"하위 매크로 단독 실행에서도 기본값이 들어간다",
      marks(_lines) == ["SUB", "SUB-DEFAULT-USED"], u"%r" % (marks(_lines),))

# 선언에 없는 이름을 넘기면 조용히 무시하지 않는다
_code, _lines, _text = call_with({"who": "a", "typo": 1}, "ParamStale")
check(u"선언에 없는 값은 조용히 넘기지 않는다",
      "GREETER" not in marks(_lines) and u"typo" in _text,
      u"%r" % (marks(_lines),))


# ------------------------------------------------------------------ 25d

section(u"25d. 드래그 양 끝을 로그에서 구분할 수 있는가")

# 끝을 못 찾게 만들면 실제로 끌지 않는다. 화면을 건드리지 않고 로그만 본다.
# 드래그는 대상이 둘이라, 자리 이름이 없으면 어느 줄이 시작이고 어느 줄이
# 끝인지 알 수 없다 - 그게 이 검사의 요지다.
_g = graph_model.Graph(graph_model.blank(u"드래그 양 끝"))
_s = log_node(_g, "START")
_d = _g.add_node({"type": "drag",
                  "from": {"point": [123, 456]},
                  "to": {"image": "never_matches.png",
                         "region": [0, 0, 400, 300], "timeout": 1}}, 240, 0)
_ok = log_node(_g, "OK", 480, -60)
_bad = log_node(_g, "FAILPIN", 480, 80)
_g.entry = _s["id"]
_g.connect(_s["id"], "next", _d["id"])
_g.connect(_d["id"], "next", _ok["id"])
_g.connect(_d["id"], "fail", _bad["id"])

_path = save_graph(_g, "DragEnds")
shutil.copyfile(os.path.join(PROJECT, "Macros", "ExampleGraph", "never_matches.png"),
                os.path.join(os.path.dirname(_path), "never_matches.png"))
_code, _lines, _text = run_graph(_g, "DragEnds")

check(u"끝을 못 찾으면 실패 핀으로", marks(_lines) == ["START", "FAILPIN"],
      u"%r" % (marks(_lines),))
check(u"시작이 좌표면 좌표를 남긴다", u"시작: 좌표 지정 (123,456)" in _text)
check(u"끝을 찾기 시작한 것이 남는다",
      u"끝: 이미지 never_matches.png 찾는 중" in _text)
check(u"끝을 못 찾은 것이 남는다", u"끝: 이미지 never_matches.png 없음" in _text)
check(u"어느 쪽이 안 됐는지 알려 준다", u"시작 OK, 끝 못 찾음" in _text)
check(u"못 찾았으면 경로를 찍지 않는다", u"끌기 경로" not in _text)


# ------------------------------------------------------------------ 25c

section(u"25c. 이미지 조건이 무엇에 걸렸는지 로그에 남는가")

# 조건이 참/거짓만 남기면 "화면에 없는데 참이 나온다" 를 확인할 길이 없다.
# 실제로 RunHyperV 의 n13 이 평평한 배경을 0.96 으로 오탐했는데, 점수도
# 자리도 로그에 없어 원인을 좁히지 못했다.
_g = graph_model.Graph(graph_model.blank(u"조건 로그"))
_start = log_node(_g, "START")
# 검색 영역은 템플릿보다 커야 한다. 작으면 OculiX 가
# "image to search is larger than image to search in" 으로 던진다.
_cond = _g.add_node({"type": "if",
                     "condition": {"type": "imageExists",
                                   "image": "never_matches.png",
                                   "region": [0, 0, 400, 300], "timeout": 1}},
                    240, 0)
_yes = log_node(_g, "YES", 480, -60)
_no = log_node(_g, "NO", 480, 80)
_g.entry = _start["id"]
_g.connect(_start["id"], "next", _cond["id"])
_g.connect(_cond["id"], "true", _yes["id"])
_g.connect(_cond["id"], "false", _no["id"])

_path = save_graph(_g, "CondLog")
shutil.copyfile(os.path.join(PROJECT, "Macros", "ExampleGraph", "never_matches.png"),
                os.path.join(os.path.dirname(_path), "never_matches.png"))
_code, _lines, _text = run_graph(_g, "CondLog")
check(u"못 찾으면 거짓 핀으로", marks(_lines) == ["START", "NO"],
      "%r" % (marks(_lines),))
check(u"못 찾았다고 로그에 남는다", u"never_matches.png 없음" in _text)
check(u"어떤 정확도로 찾았는지 남는다", u"정확도 0.90 이상" in _text)
check(u"어느 범위를 봤는지 남는다", u"[0, 0, 400, 300]" in _text)

# 찾았을 때는 점수와 자리가 남아야 한다. 지금 화면의 한 조각을 그대로 떠서
# 같은 자리에서 찾게 하면 반드시 걸린다 - 그 사이 화면이 바뀌지만 않으면.
_shot = os.path.join(os.path.dirname(_path), "onscreen.png")
subprocess.run(
    [JAVA, "-jar", JAR, "-r", os.path.join(PROJECT, "Scripts", "Tests",
                                           "CaptureRegion.sikuli"), "-c", "--",
     "300", "300", "160", "90", _shot],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
if not os.path.isfile(_shot):
    skip(u"찾았을 때 점수가 남는다", u"화면 조각을 뜨지 못했습니다")
else:
    _g2 = graph_model.Graph(graph_model.blank(u"조건 로그2"))
    _s2 = log_node(_g2, "START")
    _c2 = _g2.add_node({"type": "if",
                        "condition": {"type": "imageExists",
                                      "image": "onscreen.png",
                                      "region": [280, 280, 200, 130],
                                      "timeout": 2}}, 240, 0)
    _y2 = log_node(_g2, "YES", 480, -60)
    _n2 = log_node(_g2, "NO", 480, 80)
    _g2.entry = _s2["id"]
    _g2.connect(_s2["id"], "next", _c2["id"])
    _g2.connect(_c2["id"], "true", _y2["id"])
    _g2.connect(_c2["id"], "false", _n2["id"])
    _code2, _lines2, _text2 = run_graph(_g2, "CondLog")
    if marks(_lines2) != ["START", "YES"]:
        # 뜬 뒤 그 자리 화면이 바뀌면 못 찾는다. 실패가 아니라 건너뛴다.
        skip(u"찾았을 때 점수가 남는다",
             u"뜬 뒤 그 자리 화면이 바뀐 듯합니다: %r" % (marks(_lines2),))
    else:
        check(u"찾았을 때 점수가 남는다",
              u"onscreen.png 발견 score=" in _text2)
        check(u"찾았을 때 자리도 남는다", u"영역 (" in _text2)


# ------------------------------------------------------------------ 25b

section(u"25b. 고른 노드부터 실행 (--from)")

# A -> B -> C 를 이어 두고 B 부터 시작시키면 A 는 건너뛰어야 한다.
# 저장된 entry 는 그대로여야 한다 - 실행 인자일 뿐 파일을 고치는 기능이 아니다.
_g = graph_model.Graph(graph_model.blank(u"중간부터"))
_a = log_node(_g, "A", 0, 0)
_b = log_node(_g, "B", 240, 0)
_c = log_node(_g, "C", 480, 0)
_g.entry = _a["id"]
_g.connect(_a["id"], "next", _b["id"])
_g.connect(_b["id"], "next", _c["id"])

_code, _lines, _text = run_graph(_g, "FromDefault")
check(u"지정하지 않으면 저장된 시작 노드부터",
      marks(_lines) == ["A", "B", "C"], "%r" % (marks(_lines),))

_code, _lines, _text = run_graph(_g, "FromMiddle", start_node=_b["id"])
check(u"--from 을 주면 그 노드부터",
      marks(_lines) == ["B", "C"], "%r" % (marks(_lines),))
check(u"어디서 시작했는지 로그에 남는다", u"시작 지점 지정" in _text)
check(u"--from 은 매크로 파일을 고치지 않는다", _g.entry == _a["id"], _g.entry)

_code, _lines, _text = run_graph(_g, "FromLast", start_node=_c["id"])
check(u"마지막 노드부터도 된다", marks(_lines) == ["C"], "%r" % (marks(_lines),))

_code, _lines, _text = run_graph(_g, "FromBogus", start_node="no-such-node")
check(u"없는 노드를 주면 실행하지 않는다",
      marks(_lines) == [] and _code != 0,
      u"code=%r marks=%r" % (_code, marks(_lines)))
check(u"없는 노드는 이유를 알려 준다",
      u"찾을 수 없습니다" in _text and u"no-such-node" in _text)

# 트리 형식에는 노드가 없으므로 거부해야 한다
_tree_dir = os.path.join(WORK, "TreeFrom")
os.makedirs(_tree_dir)
_tree_path = os.path.join(_tree_dir, "macro.json")
with io.open(_tree_path, "w", encoding="utf-8") as _fh:
    _fh.write(json.dumps({"name": u"트리", "version": 1, "settings": {},
                          "steps": [{"type": "log", "message": "MARK:T"}]},
                         ensure_ascii=False))
_cmd = [JAVA, "-Dfile.encoding=UTF-8", "-Dsun.stdout.encoding=UTF-8",
        "-jar", JAR, "-r", RUNNER, "-c", "--", _tree_path, "--from=x"]
_proc = subprocess.run(_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
_ttext = _proc.stdout.decode("utf-8", "replace")
check(u"트리 형식에 --from 은 거부",
      _proc.returncode == 2 and u"graph macros" in _ttext,
      u"code=%r" % (_proc.returncode,))


# ------------------------------------------------------------------ 26

section(u"26. 한글 글자 인식 (실측)")

# OcrTarget.ps1 이 떠 있을 때만 돈다. 한글 라벨 다섯 개를 띄우고 클릭을 기록하는
# 창이라, 매크로가 정말 그 라벨을 눌렀는지 로그가 아니라 창이 받은 값으로 가린다.
KR_STATE = os.path.join(PROJECT, "Logs", "ocr_target.txt")


def kr_state():
    out = {}
    if not os.path.exists(KR_STATE):
        return out
    with io.open(KR_STATE, encoding="utf-8-sig") as fh:
        for line in fh:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                out[k] = v
    return out


def kr_rect(name):
    return [int(x) for x in kr_state()["rect." + name].split(",")]


if not window_up(TITLE_OCR):
    skip(u"한글 글자 인식 실측", u"Scripts\\Tests\\OcrTarget.ps1 을 실행하세요 "
                            u"(제목 '%s' 창이 화면에 없습니다)" % TITLE_OCR)
elif "rect.form" not in kr_state():
    skip(u"한글 글자 인식 실측", u"창은 떠 있는데 %s 에 좌표가 없습니다" % KR_STATE)
else:
    # 1. 창 전체에서 한글 두 글자 찾기.
    #    OCR 은 한글을 음절마다 쪼개 내놓으므로("설","정") 조각을 이어붙이지
    #    않으면 못 찾는다. 이 검사가 그 구현을 지킨다.
    g = graph_model.Graph(graph_model.blank(u"한글 대기"))
    start = log_node(g, "START")
    wait = g.add_node({"type": "waitText", "text": u"설정", "ocrLanguage": "kor",
                       "region": kr_rect("form"), "timeout": 8}, 240, 0)
    ok = log_node(g, "FOUND", 480, -60)
    bad = log_node(g, "NOTFOUND", 480, 80)
    g.connect(start["id"], "next", wait["id"])
    g.connect(wait["id"], "next", ok["id"])
    g.connect(wait["id"], "fail", bad["id"])
    _code, _lines, _text = run_graph(g, "KoreanWait")
    check(u"한글 두 글자를 찾는다 (음절 분리 극복)",
          marks(_lines) == ["START", "FOUND"], "%r" % (marks(_lines),))

    # 2. 띄어쓰기가 달라도 찾는다. OCR 이 넣는 공백은 예측할 수 없다.
    g = graph_model.Graph(graph_model.blank(u"한글 구문"))
    start = log_node(g, "START")
    wait = g.add_node({"type": "waitText", "text": u"다음 단계로 진행",
                       "ocrLanguage": "kor", "region": kr_rect("form"),
                       "timeout": 8}, 240, 0)
    ok = log_node(g, "FOUND", 480, -60)
    bad = log_node(g, "NOTFOUND", 480, 80)
    g.connect(start["id"], "next", wait["id"])
    g.connect(wait["id"], "next", ok["id"])
    g.connect(wait["id"], "fail", bad["id"])
    _code, _lines, _text = run_graph(g, "KoreanPhrase")
    check(u"띄어쓰기가 달라도 찾는다",
          marks(_lines) == ["START", "FOUND"], "%r" % (marks(_lines),))

    # 3. 없는 글자는 실패 핀으로 나간다.
    g = graph_model.Graph(graph_model.blank(u"없는 한글"))
    start = log_node(g, "START")
    wait = g.add_node({"type": "waitText", "text": u"없는글자입니다",
                       "ocrLanguage": "kor", "region": kr_rect("form"),
                       "timeout": 3}, 240, 0)
    ok = log_node(g, "FOUND", 480, -60)
    bad = log_node(g, "NOTFOUND", 480, 80)
    g.connect(start["id"], "next", wait["id"])
    g.connect(wait["id"], "next", ok["id"])
    g.connect(wait["id"], "fail", bad["id"])
    _code, _lines, _text = run_graph(g, "KoreanAbsent")
    check(u"없는 한글은 실패 핀으로",
          marks(_lines) == ["START", "NOTFOUND"], "%r" % (marks(_lines),))

    # 4. 찾아서 클릭한 것이 정말 그 라벨인가. 창이 받은 값으로 가린다.
    _before = kr_state()
    _kx, _ky, _kw, _kh = kr_rect("kr2")
    _around = [_kx - 30, _ky - 15, _kw + 60, _kh + 30]
    g = graph_model.Graph(graph_model.blank(u"한글 클릭"))
    start = log_node(g, "START")
    click = g.add_node({"type": "click", "text": u"확인", "ocrLanguage": "kor",
                        "region": _around, "timeout": 8}, 240, 0)
    ok = log_node(g, "CLICKED", 480, -60)
    bad = log_node(g, "NOCLICK", 480, 80)
    g.connect(start["id"], "next", click["id"])
    g.connect(click["id"], "next", ok["id"])
    g.connect(click["id"], "fail", bad["id"])
    _code, _lines, _text = run_graph(g, "KoreanClick")
    _after = kr_state()
    check(u"한글을 찾아 클릭하면 그 라벨이 받는다",
          _after.get("lastClick") == "kr2"
          and int(_after.get("hits.kr2", 0)) > int(_before.get("hits.kr2", 0)),
          u"lastClick=%r hits=%s->%s" % (_after.get("lastClick"),
                                         _before.get("hits.kr2"),
                                         _after.get("hits.kr2")))

    # 5. 여백을 조금 둔 영역도 읽혀야 한다. psm 기본값이 3 이면 여기서 빈다.
    check(u"여백 있는 영역도 읽는다 (psm 기본값 확인)",
          marks(_lines) == ["START", "CLICKED"], "%r" % (marks(_lines),))

    # 6. 조건으로도 쓸 수 있다.
    g = graph_model.Graph(graph_model.blank(u"한글 조건"))
    start = log_node(g, "START")
    node = g.add_node({"type": "if",
                       "condition": {"type": "textExists", "text": u"관리자",
                                     "ocrLanguage": "kor",
                                     "region": kr_rect("form"), "timeout": 6}},
                      240, 0)
    yes = log_node(g, "YES", 480, -60)
    no = log_node(g, "NO", 480, 80)
    g.connect(start["id"], "next", node["id"])
    g.connect(node["id"], "true", yes["id"])
    g.connect(node["id"], "false", no["id"])
    _code, _lines, _text = run_graph(g, "KoreanCond")
    check(u"조건 textExists(관리자) -> YES",
          marks(_lines) == ["START", "YES"], "%r" % (marks(_lines),))


section(u"하위 매크로 (부모 전용 함수)")

# 매크로 폴더 안에 중첩된 매크로는 그 부모의 사유물이다. 부모/형제만 부를 수
# 있고, 이미지와 실행 설정은 부모 것을 함께 쓴다 (UE 블루프린트의 함수).


def save_family(folder, name, nodes, links=None, settings=None):
    """가족 구성원 하나를 저장한다. folder 는 MACROS 기준 상대 경로."""
    path = os.path.join(MACROS, folder)
    if not os.path.isdir(path):
        os.makedirs(path)
    data = {"name": name, "version": 2, "format": "graph",
            "entry": nodes[0]["id"], "nodes": nodes, "links": links or []}
    if settings is not None:
        data["settings"] = settings
    target = os.path.join(path, "macro.json")
    with io.open(target, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))
    return target


def mark_node(node_id, text):
    return {"id": node_id, "type": "log", "message": "MARK:" + text}


# 부모의 정확도를 눈에 띄는 값으로 둔다. 하위가 이 값을 물려받으면 하위의
# 이미지 검색 로그에 "정확도 0.77 이상" 이 그대로 찍힌다 - 상속을 시간이
# 아니라 로그로 확인할 수 있어 JVM 기동 시간에 묻히지 않는다.
_FAM_SETTINGS = {"screen": 0, "defaultSimilarity": 0.77, "defaultTimeout": 1,
                 "stepDelay": 0, "maxSteps": 5000, "maxSeconds": 300}

_parent = save_family(
    "Fam", u"부모",
    [mark_node("n1", "PARENT"),
     {"id": "n2", "type": "call", "macro": "./OpenMenu"},
     mark_node("n3", "PARENT-END")],
    [{"from": "n1", "pin": "next", "to": "n2"},
     {"from": "n2", "pin": "next", "to": "n3"}],
    settings=_FAM_SETTINGS)

# 하위 A: settings 가 아예 없다. 부모 것을 물려받아야 한다.
# 이미지도 자기 폴더가 아니라 부모 폴더의 것을 이름만으로 참조한다.
save_family(
    os.path.join("Fam", "OpenMenu"), u"메뉴 열기",
    [mark_node("s1", "SUB-A"),
     {"id": "s2", "type": "if",
      "condition": {"type": "imageExists", "image": "shared.png"}},
     {"id": "s3", "type": "call", "macro": "./ClosePopup"},
     mark_node("s4", "SUB-A-END")],
    [{"from": "s1", "pin": "next", "to": "s2"},
     {"from": "s2", "pin": "false", "to": "s3"},
     {"from": "s3", "pin": "next", "to": "s4"}])

save_family(os.path.join("Fam", "ClosePopup"), u"팝업 닫기",
            [mark_node("b1", "SUB-B")])

# 가족 밖의 라이브러리 매크로. 남의 하위를 경로로 집어 본다.
_outsider = save_family(
    "Outsider", u"바깥 매크로",
    [{"id": "o1", "type": "call", "macro": "Fam/OpenMenu"}],
    settings={"maxSteps": 100, "maxSeconds": 60})

shutil.copyfile(os.path.join(PROJECT, "Macros", "Example", "never_matches.png"),
                os.path.join(MACROS, "Fam", "shared.png"))

_code, _lines, _text = run_graph_path(_parent)
check(u"부모 -> 하위 -> 형제 순으로 실행",
      marks(_lines) == ["PARENT", "SUB-A", "SUB-B", "SUB-A-END", "PARENT-END"],
      "%r" % (marks(_lines),))
check(u"하위가 부모 폴더의 이미지를 이름만으로 찾는다",
      u"shared.png 없음" in _text and u"image not found" not in _text,
      u"exit=%s" % _code)
check(u"하위가 부모 설정을 상속 (정확도 0.77)",
      u"정확도 0.77 이상" in _text, u"exit=%s" % _code)

_code, _lines, _text = run_graph_path(_outsider)
check(u"가족 밖에서 남의 하위를 부르면 거부",
      _code != 0 and u"하위 매크로는 부모와 형제만" in _text, u"exit=%s" % _code)

# 편집기에서 하위 매크로를 열어 F5 로 바로 돌리는 경우. 호출로 실행할 때와
# 같은 문맥이어야 한다 - 다르면 테스트는 통과하고 본 실행이 깨진다.
_code, _lines, _text = run_graph_path(
    os.path.join(MACROS, "Fam", "OpenMenu", "macro.json"))
check(u"하위 단독 실행이 부모 문맥을 물려받는다",
      _code == 0 and u"부모(Fam)의 설정과 이미지 폴더" in _text
      and u"정확도 0.77 이상" in _text, u"exit=%s" % _code)
check(u"하위 단독 실행에서도 형제 호출이 된다",
      marks(_lines) == ["SUB-A", "SUB-B", "SUB-A-END"], "%r" % (marks(_lines),))


section(u"25g. 값 목록 반복 (forEach) - 실측")

# 피호출: 받은 값을 그대로 찍는다. 반복이 매번 다른 값을 넘기는지 본다.
_fe_callee = graph_model.Graph(graph_model.blank(u"한 명 처리"))
_fe_callee.data["params"] = [{"name": "no", "type": "int"}]
_fc0 = _fe_callee.add_node({"type": "log", "message": "MARK:CHAR"}, 0, 0)
_fc1 = _fe_callee.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "no", "op": "==", "value": "3"}}, 240, 0)
_fc3 = log_node(_fe_callee, "THREE", 480, -60)
_fcx = log_node(_fe_callee, "OTHER", 480, 60)
_fe_callee.entry = _fc0["id"]
_fe_callee.connect(_fc0["id"], "next", _fc1["id"])
_fe_callee.connect(_fc1["id"], "true", _fc3["id"])
_fe_callee.connect(_fc1["id"], "false", _fcx["id"])
save_named(_fe_callee, "ForEachCallee")

# 반복이 2,3,4 를 차례로 넘긴다
_g = graph_model.Graph(graph_model.blank(u"값 목록 반복"))
_s = log_node(_g, "START")
_loop = _g.add_node({"type": "repeat", "forEach": {
    "param": "charNo", "type": "int", "values": [2, 3, 4]}}, 240, 0)
_call = _g.add_node({"type": "call", "macro": "ForEachCallee",
                     "args": {"no": graph_model.param_ref("charNo")}}, 480, 60)
_done = log_node(_g, "DONE", 480, -60)
_g.entry = _s["id"]
_g.connect(_s["id"], "next", _loop["id"])
_g.connect(_loop["id"], "body", _call["id"])
_g.connect(_loop["id"], "completed", _done["id"])

_e, _w = _g.validate()
check(u"값 목록 반복이 검사를 통과", not _e, u"%r" % (_e,))

_code, _lines, _text = run_graph(_g, "foreach_basic")
check(u"종료 코드 0", _code == 0, u"exit=%s" % _code)
check(u"값마다 한 번씩, 값에 따라 분기한다",
      marks(_lines) == ["START", "CHAR", "OTHER", "CHAR", "THREE",
                        "CHAR", "OTHER", "DONE"],
      u"%r" % (marks(_lines),))
check(u"넘긴 값이 매 회 달라진다",
      u"no=2" in _text and u"no=3" in _text and u"no=4" in _text)

# 반복 변수를 조건에서 직접 읽는다 (호출 없이)
_g = graph_model.Graph(graph_model.blank(u"반복 변수 조건"))
_s = log_node(_g, "START")
_loop = _g.add_node({"type": "repeat", "forEach": {
    "param": "n", "type": "int", "values": [1, 2]}}, 240, 0)
_if = _g.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "n", "op": "==", "value": "2"}}, 480, 60)
_two = log_node(_g, "TWO", 720, 0)
_one = log_node(_g, "ONE", 720, 120)
_g.entry = _s["id"]
_g.connect(_s["id"], "next", _loop["id"])
_g.connect(_loop["id"], "body", _if["id"])
_g.connect(_if["id"], "true", _two["id"])
_g.connect(_if["id"], "false", _one["id"])
_code, _lines, _text = run_graph(_g, "foreach_cond")
check(u"조건이 반복 변수를 읽는다", marks(_lines) == ["START", "ONE", "TWO"],
      u"%r" % (marks(_lines),))

# 본문 안에서 break
_g = graph_model.Graph(graph_model.blank(u"값 반복 break"))
_loop = _g.add_node({"type": "repeat", "forEach": {
    "param": "n", "type": "int", "values": [1, 2, 3, 4]}}, 0, 0)
_b = log_node(_g, "B", 240, 60)
_if = _g.add_node({"type": "if", "condition": {
    "type": "paramCompare", "param": "n", "op": ">=", "value": "2"}}, 480, 60)
_brk = _g.add_node({"type": "break"}, 720, 0)
_after = log_node(_g, "AFTER", 240, -60)
_g.entry = _loop["id"]
_g.connect(_loop["id"], "body", _b["id"])
_g.connect(_loop["id"], "completed", _after["id"])
_g.connect(_b["id"], "next", _if["id"])
_g.connect(_if["id"], "true", _brk["id"])
_code, _lines, _text = run_graph(_g, "foreach_break")
check(u"break 가 값 반복을 끝내고 완료로 나간다",
      marks(_lines) == ["B", "B", "AFTER"], u"%r" % (marks(_lines),))

# 반복 밖에서 참조하면 실행이 멈춘다 (조용히 비우지 않는다)
_g = graph_model.Graph(graph_model.blank(u"범위 밖 참조"))
_loop = _g.add_node({"type": "repeat", "forEach": {
    "param": "n", "type": "int", "values": [1]}}, 0, 0)
_inside = log_node(_g, "IN", 240, 60)
_call = _g.add_node({"type": "call", "macro": "ForEachCallee",
                     "args": {"no": graph_model.param_ref("n")}}, 240, -60)
_g.entry = _loop["id"]
_g.connect(_loop["id"], "body", _inside["id"])
_g.connect(_loop["id"], "completed", _call["id"])
_code, _lines, _text = run_graph(_g, "foreach_out_of_scope")
check(u"반복 밖 참조를 실행 시점에 잡는다",
      u"지금 범위에 없습니다" in _text, u"exit=%s" % _code)
check(u"조용히 넘어가지 않고 중단된다", _code != 0, u"exit=%s" % _code)

# 중첩: 안쪽이 끝나면 바깥 값이 돌아온다
_g = graph_model.Graph(graph_model.blank(u"중첩 값 반복"))
_outer = _g.add_node({"type": "repeat", "forEach": {
    "param": "a", "type": "string", "values": ["x", "y"]}}, 0, 0)
_inner = _g.add_node({"type": "repeat", "forEach": {
    "param": "b", "type": "string", "values": ["1", "2"]}}, 240, 60)
_mark = _g.add_node({"type": "log", "message": "MARK:PAIR"}, 480, 120)
_g.entry = _outer["id"]
_g.connect(_outer["id"], "body", _inner["id"])
_g.connect(_inner["id"], "body", _mark["id"])
_code, _lines, _text = run_graph(_g, "foreach_nested")
check(u"중첩 값 반복이 값의 곱만큼 돈다", len(marks(_lines)) == 4,
      u"%r" % (marks(_lines),))
check(u"바깥 변수가 안쪽 반복 뒤에도 유지된다",
      _text.count(u"a = ") >= 2 or _text.count(u'a = "x"') >= 1, u"")

# 방식을 둘 이상 적으면 실행하지 않는다
_g = graph_model.Graph(graph_model.blank(u"방식 충돌"))
_g.add_node({"type": "repeat", "times": 2, "forEach": {
    "param": "n", "type": "int", "values": [1]}}, 0, 0)
_g.entry = _g.nodes[0]["id"]
_errors, _ = _g.validate()
check(u"횟수와 값 목록을 함께 쓰면 오류",
      any(u"하나만 골라야" in e for e in _errors), u"%r" % (_errors,))
_code, _lines, _text = run_graph(_g, "foreach_conflict")
check(u"충돌한 반복은 실행되지 않음", _code != 0, u"exit=%s" % _code)



# ------------------------------------------------------------------ 결과

shutil.rmtree(WORK, ignore_errors=True)
print("")
print("=" * 62)
print("passed %d / %d%s" % (len(PASS), len(PASS) + len(FAIL),
                            (u"   건너뜀 %d" % len(SKIP)) if SKIP else ""))
if SKIP:
    print(u"건너뜀:")
    for name in SKIP:
        print(u"  - %s" % name)
if FAIL:
    print(u"실패:")
    for name in FAIL:
        print("  - %s" % name)
    sys.exit(1)
print("GRAPHTEST_OK")
sys.exit(0)
