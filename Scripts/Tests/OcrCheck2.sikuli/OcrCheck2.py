# -*- coding: utf-8 -*-
# OcrCheck2.sikuli - 어떤 텍스트 검색 방식이 실제로 통하는지 가려낸다.

from sikuli import *
import time

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
label = Region(*r["label"])

print("=== 라벨 영역만 읽기 ===")
print("  text()      = %r" % label.text().strip())
print("  textLines() = %r" % [str(l).strip() for l in label.textLines()])
print("  textWords() = %r" % [str(w).strip() for w in label.textWords()])

print("=== 여러 검색 방식 (창 전체 기준) ===")
for query in ["OCULIX", "TARGET", "OCULIX- TARGET", "CLICK", "ME"]:
    row = ["%-14s" % query]
    for name in ["existsText", "hasText"]:
        try:
            fn = getattr(form, name)
            result = fn(query, 2) if name == "existsText" else fn(query)
            row.append("%s=%s" % (name, "찾음" if result else "못찾음"))
        except Exception, e:
            row.append("%s=오류(%s)" % (name, e.__class__.__name__))
    for name in ["findWord", "findLine"]:
        try:
            m = getattr(form, name)(query)
            row.append("%s=(%d,%d)" % (name, m.getX(), m.getY()))
        except Exception, e:
            row.append("%s=X" % name)
    print("  " + "  ".join(row))

print("=== findAllText / findWords ===")
for query in ["OCULIX", "TARGET"]:
    try:
        hits = list(form.findAllText(query))
        print("  findAllText(%-8s) %d곳 %s" % (query, len(hits),
              [(h.getX(), h.getY()) for h in hits[:3]]))
    except Exception, e:
        print("  findAllText(%-8s) 오류 %s" % (query, e.__class__.__name__))
    try:
        hits = list(form.findWords(query))
        print("  findWords  (%-8s) %d곳 %s" % (query, len(hits),
              [(h.getX(), h.getY()) for h in hits[:3]]))
    except Exception, e:
        print("  findWords  (%-8s) 오류 %s" % (query, e.__class__.__name__))

print("=== 버튼/파란패널 영역 개별 확인 ===")
for key in ["button", "vanish", "status"]:
    if key not in r:
        continue
    reg = Region(*r[key])
    try:
        print("  %-7s text=%r" % (key, reg.text().strip()[:60]))
    except Exception, e:
        print("  %-7s 오류 %s" % (key, e.__class__.__name__))

print("CHECK2_DONE")
