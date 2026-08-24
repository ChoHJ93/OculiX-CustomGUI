# -*- coding: utf-8 -*-
# OcrCheck.sikuli - 화면의 실제 글자를 읽고 위치까지 맞는지 확인한다.
# 전용 테스트 창(TestTarget.ps1)이 떠 있어야 한다.

from sikuli import *
import os
import time

screen = Screen(0)
STATE = "D:/Programming/Oculix-Automation/Logs/target_state.txt"


def rects():
    out = {}
    handle = open(STATE, "r")
    try:
        for line in handle.read().splitlines():
            if line.startswith("rect."):
                key, value = line[5:].split("=", 1)
                out[key] = [int(v) for v in value.split(",")]
    finally:
        handle.close()
    return out


r = rects()
form = Region(*r["form"])
print("대상 창 %s / 라벨 %s" % (r["form"], r["label"]))

print("=== 1. 영역의 글자 읽기 ===")
t0 = time.time()
text = form.text()
print("  걸린 시간 %.2fs" % (time.time() - t0))
for line in [l for l in text.splitlines() if l.strip()][:12]:
    print("    %r" % line.strip())

print("=== 2. findText / existsText 로 위치 찾기 ===")
for query in ["OCULIX-TARGET", "CLICK ME", "VANISH-7Q", "NOT-ON-SCREEN-XYZ"]:
    t0 = time.time()
    try:
        m = form.existsText(query, 3)
    except Exception, e:
        print("  %-18s 오류 %s: %s" % (query, e.__class__.__name__, e))
        continue
    if m is None:
        print("  %-18s 못 찾음 (%.2fs)" % (query, time.time() - t0))
    else:
        print("  %-18s 찾음 (%d,%d) %dx%d  중앙 (%d,%d)  %.2fs"
              % (query, m.getX(), m.getY(), m.getW(), m.getH(),
                 m.getTarget().getX(), m.getTarget().getY(),
                 time.time() - t0))

print("=== 3. 찾은 위치가 실제 라벨 안인가 ===")
m = form.existsText("OCULIX-TARGET", 3)
if m:
    lx, ly, lw, lh = r["label"]
    tx, ty = m.getTarget().getX(), m.getTarget().getY()
    print("  라벨 영역 (%d,%d) %dx%d" % (lx, ly, lw, lh))
    print("  OCR 중앙  (%d,%d)" % (tx, ty))
    print("  라벨 안에 있는가: %s"
          % ((lx <= tx <= lx + lw) and (ly <= ty <= ly + lh)))

print("=== 4. 사용 가능 언어 ===")
try:
    print("  %s" % OCR.availableLanguages())
except Exception, e:
    print("  조회 실패: %s: %s" % (e.__class__.__name__, e))
print("CHECK_DONE")
