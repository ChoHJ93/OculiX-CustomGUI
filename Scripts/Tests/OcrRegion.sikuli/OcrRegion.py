# -*- coding: utf-8 -*-
from sikuli import *
import shutil, os

STATE = "D:/Programming/Oculix-Automation/Logs/target_state.txt"
OUT = os.environ.get("OCR_OUT", "C:/temp")
r = {}
for line in open(STATE, "r").read().splitlines():
    if line.startswith("rect."):
        k, v = line[5:].split("=", 1)
        r[k] = [int(x) for x in v.split(",")]

for key in ("form", "label", "button"):
    reg = Region(*r[key])
    shot = reg.getScreen().capture(reg)
    path = shot.getFile()
    dest = os.path.join(OUT, "ocr_%s.png" % key)
    shutil.copyfile(path, dest)
    print("%-7s %s -> %s" % (key, r[key], dest))

# 같은 영역을 5번 연속 읽어 흔들림을 본다
for key in ("label", "button"):
    reg = Region(*r[key])
    reads = []
    for i in range(5):
        try:
            reads.append(repr(reg.text().strip()))
        except Exception, e:
            reads.append("ERR:%s" % e)
    print("%-7s 5회 읽기: %s" % (key, reads))
