# -*- coding: utf-8 -*-
# MethodProbe.sikuli - 엔진이 쓸 입력 메서드가 Screen/Region에 있는지 확인.
# 전역 함수(click 등)는 import된 모듈에서 안 보이므로 메서드로 대체해야 한다.

from sikuli import *
import sys

mod = sys.modules["sikuli"]
screen = Screen(0)

print("=== 전역 함수가 모듈 속성으로 보이는가 (import된 모듈 기준) ===")
for name in ["click", "doubleClick", "rightClick", "hover", "mouseDown",
             "mouseUp", "dragDrop", "wheel", "type", "paste", "keyDown", "keyUp"]:
    print("  sikuli.%-12s : %s" % (name, hasattr(mod, name)))

print("=== Screen 인스턴스 메서드 ===")
missing = []
for name in ["click", "doubleClick", "rightClick", "hover", "mouseDown",
             "mouseUp", "dragDrop", "drag", "dropAt", "wheel", "type", "paste",
             "keyDown", "keyUp", "exists", "waitVanish", "findAll"]:
    ok = hasattr(screen, name)
    print("  Screen.%-12s : %s" % (name, ok))
    if not ok:
        missing.append(name)

print("=== 클래스는 모듈 속성으로 보이는가 ===")
for name in ["Region", "Screen", "Pattern", "Location", "Button", "Key",
             "KeyModifier", "Settings", "Mouse"]:
    print("  sikuli.%-12s : %s" % (name, hasattr(mod, name)))

if missing:
    print("MISSING=%s" % ",".join(missing))
else:
    print("ALL_METHODS_PRESENT")
