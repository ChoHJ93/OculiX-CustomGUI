# -*- coding: utf-8 -*-
# KeyResolve.sikuli - 편집기 선택 창이 내놓는 키 이름을 엔진이 전부 해석하는지 확인.
# macro_engine 의 key 단계와 같은 방식으로 해석해 본다. 입력은 주입하지 않는다.

from sikuli import *

KEYS = """ADD ALT ALTGR BACKSPACE CAPS_LOCK CMD CONTEXT CTRL DECIMAL DELETE
DIVIDE DOWN END ENTER ESC F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11 F12 F13 F14 F15
HOME INSERT LEFT META MINUS MULTIPLY NEXT NUM0 NUM1 NUM2 NUM3 NUM4 NUM5 NUM6
NUM7 NUM8 NUM9 NUM_LOCK PAGE_DOWN PAGE_UP PAUSE PRINTSCREEN RIGHT SCROLL_LOCK
SEPARATOR SHIFT SPACE TAB UP WIN""".split()

MODS = ["CTRL", "SHIFT", "ALT", "META"]

_MODIFIERS = {
    "CTRL": KeyModifier.CTRL,
    "SHIFT": KeyModifier.SHIFT,
    "ALT": KeyModifier.ALT,
    "META": KeyModifier.META,
    "WIN": KeyModifier.META,
    "ALTGR": KeyModifier.ALTGR,
}

print("=== 키 이름 해석 (엔진과 같은 방식) ===")
missing = []
for name in KEYS:
    resolved = getattr(Key, name.upper(), None)
    if resolved is None:
        missing.append(name)
        print("  [FAIL] %-14s Key 상수 없음" % name)
print("  검사한 키 %d개, 해석 실패 %d개" % (len(KEYS), len(missing)))

print("=== 일반 문자 폴백 ===")
for ch in ["a", "s", "1", "/"]:
    resolved = getattr(Key, ch.upper(), ch)
    ok = resolved == ch
    print("  %-3s -> %r  %s" % (ch, resolved, "OK" if ok else "다른 상수로 잡힘"))

print("=== 조합키 값 ===")
for name in MODS:
    print("  %-6s = %d" % (name, _MODIFIERS[name]))
combined = None
for name in ["CTRL", "SHIFT"]:
    value = _MODIFIERS[name]
    combined = value if combined is None else (combined | value)
print("  CTRL|SHIFT = %d (기대 3)" % combined)

print("=== 실제 조합 만들기 (입력 주입 없음) ===")
try:
    sample = getattr(Key, "ENTER")
    mods = _MODIFIERS["CTRL"] | _MODIFIERS["SHIFT"]
    print("  Ctrl+Shift+Enter -> key=%r mods=%d" % (sample, mods))
    print("  screen.type 시그니처 확인: %s" % hasattr(Screen(0), "type"))
except Exception, e:
    print("  실패: %s: %s" % (e.__class__.__name__, e))

if missing:
    print("RESOLVE_FAILED=%s" % ",".join(missing))
else:
    print("ALL_KEYS_RESOLVE")
