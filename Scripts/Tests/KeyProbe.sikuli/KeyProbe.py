# -*- coding: utf-8 -*-
# KeyProbe.sikuli - OculiX 4.0.0의 Key / KeyModifier 상수를 전부 뽑아낸다.
# 편집기의 특수키 선택 목록을 이 결과로 만든다.

from sikuli import *

# 주의: sikuli의 전역 type()이 내장 type()을 가린다. value.__class__ 를 쓴다.
print("=== Key 상수 ===")
names = [n for n in dir(Key) if not n.startswith("_")]
names.sort()
usable = []
aliases = []
for name in names:
    try:
        value = getattr(Key, name)
    except Exception:
        continue
    if callable(value):
        continue
    if isinstance(value, basestring):
        if name.startswith("C_"):
            aliases.append(name)
        else:
            usable.append(name)
    else:
        print("  Key.%-16s (비문자열: %s)" % (name, value.__class__.__name__))

print("KEY_COUNT=%d" % len(usable))
print("KEY_LIST=%s" % ",".join(usable))
print("ALIAS_COUNT=%d (C_ 접두 별칭)" % len(aliases))

print("=== KeyModifier 상수 ===")
mods = [n for n in dir(KeyModifier) if not n.startswith("_")]
mods.sort()
for name in mods:
    try:
        value = getattr(KeyModifier, name)
    except Exception:
        continue
    if callable(value):
        continue
    print("  KeyModifier.%-10s = %r" % (name, value))

print("=== Button 상수 ===")
for name in sorted(n for n in dir(Button) if not n.startswith("_")):
    try:
        value = getattr(Button, name)
    except Exception:
        continue
    if not callable(value):
        print("  Button.%-12s = %r" % (name, value))

print("PROBE_DONE")
