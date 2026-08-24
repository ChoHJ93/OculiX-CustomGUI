# -*- coding: utf-8 -*-
# OcrProbe.sikuli - OculiX 4.0.0 의 텍스트 인식 기능을 확인한다.
# 주의: sikuli 전역 type() 이 내장 type() 을 가리므로 __class__ 를 쓴다.

from sikuli import *
import os
import sys

mod = sys.modules["sikuli"]
screen = Screen(0)
region = Region(0, 0, 800, 400)

print("=== OCR 관련 API 존재 여부 ===")
for name in ["OCR", "TextOCR", "Finder"]:
    print("  sikuli.%-10s %s" % (name, hasattr(mod, name)))

print("=== Region 의 텍스트 메서드 ===")
for name in ["text", "textLines", "textWords", "findText", "findAllText",
             "findWord", "findWords", "findLine", "findLines",
             "existsText", "waitText", "hasText", "getText", "collectLines",
             "collectWords"]:
    print("  Region.%-14s %s" % (name, hasattr(region, name)))

print("=== OCR 클래스 멤버 ===")
if hasattr(mod, "OCR"):
    names = sorted(n for n in dir(OCR) if not n.startswith("_"))
    print("  %s" % ", ".join(names))
    for attr in ["globalOptions", "Options", "readText", "readLines", "readWords"]:
        print("  OCR.%-14s %s" % (attr, hasattr(OCR, attr)))

print("=== 설치된 Tesseract 언어 데이터 ===")
candidates = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "legerix", "5.5.0", "tessdata"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "legerix", "tessdata"),
]
for path in candidates:
    if os.path.isdir(path):
        files = sorted(f for f in os.listdir(path) if f.endswith(".traineddata"))
        print("  %s" % path)
        for f in files:
            size = os.path.getsize(os.path.join(path, f))
            print("     %-24s %d bytes" % (f, size))
    else:
        print("  (없음) %s" % path)

print("=== 현재 OCR 설정 ===")
try:
    opts = OCR.globalOptions()
    print("  language     = %s" % opts.language())
    print("  dataPath     = %s" % opts.dataPath())
    print("  oem / psm    = %s / %s" % (opts.oem(), opts.psm()))
except Exception, e:
    print("  조회 실패: %s: %s" % (e.__class__.__name__, e))

print("PROBE_DONE")
