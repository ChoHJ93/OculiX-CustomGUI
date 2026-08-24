# -*- coding: utf-8 -*-
# ApiSurvey.sikuli - confirm which APIs actually exist in OculiX 4.0.0
# before documenting them. Existence/attribute checks only - injects no input.

from sikuli import *
import sys

mod = sys.modules["sikuli"]


def has(name):
    return hasattr(mod, name) or name in globals()


print("=== global functions ===")
for n in ["click", "doubleClick", "rightClick", "hover", "dragDrop", "drag", "dropAt",
          "mouseMove", "mouseDown", "mouseUp", "wheel",
          "type", "paste", "keyDown", "keyUp",
          "find", "findAll", "exists", "wait", "waitVanish", "has",
          "capture", "popup", "input", "popAsk", "sleep",
          "openApp", "switchApp", "closeApp", "run", "getBundlePath", "setBundlePath",
          "addImagePath", "getLastMatch", "highlight", "onAppear", "onVanish",
          "onChange", "observe", "stopObserver", "setROI", "selectRegion",
          "setAutoWaitTimeout", "setThrowException", "setShowActions", "unzip"]:
    print("  %-18s %s" % (n, has(n)))

print("=== classes ===")
for n in ["Region", "Screen", "Pattern", "Match", "Location", "App", "Key",
          "KeyModifier", "Button", "Settings", "Env", "Mouse", "Keys",
          "Finder", "Image", "OCR", "Debug", "ImagePath"]:
    print("  %-18s %s" % (n, has(n)))

print("=== Region methods ===")
r = Region(0, 0, 200, 200)
for n in ["find", "findAll", "exists", "wait", "waitVanish", "has",
          "click", "doubleClick", "rightClick", "hover", "type", "paste",
          "dragDrop", "mouseDown", "mouseUp", "keyDown", "keyUp",
          "highlight", "getLastMatch", "getLastMatches",
          "above", "below", "left", "right", "nearby", "grow", "offset", "union",
          "setAutoWaitTimeout", "getCenter", "getTopLeft", "getW", "getH",
          "setROI", "onAppear", "observe", "text", "textLines", "findText"]:
    print("  Region.%-16s %s" % (n, hasattr(r, n)))

print("=== Pattern methods ===")
p = Pattern("x.png")
for n in ["similar", "exact", "targetOffset", "getFilename", "getSimilar",
          "getTargetOffset", "mask", "resize"]:
    print("  Pattern.%-15s %s" % (n, hasattr(p, n)))

print("=== Settings fields (current values) ===")
for n in ["MinSimilarity", "MoveMouseDelay", "DelayBeforeDrop", "DelayAfterDrag",
          "ClickDelay", "TypeDelay", "WaitScanRate", "ObserveScanRate",
          "AutoWaitTimeout", "ActionLogs", "InfoLogs", "DebugLogs",
          "ShowActions", "Highlight", "AlwaysResize", "OcrTextSearch"]:
    if hasattr(Settings, n):
        print("  Settings.%-18s = %s" % (n, getattr(Settings, n)))
    else:
        print("  Settings.%-18s MISSING" % n)

print("=== Key / Button constants ===")
for n in ["ENTER", "TAB", "ESC", "SPACE", "BACKSPACE", "DELETE", "F1", "UP", "WIN"]:
    print("  Key.%-12s %s" % (n, hasattr(Key, n)))
for n in ["LEFT", "MIDDLE", "RIGHT", "WHEEL_UP", "WHEEL_DOWN"]:
    print("  Button.%-9s %s" % (n, hasattr(Button, n)))
for n in ["CTRL", "SHIFT", "ALT", "META"]:
    print("  KeyModifier.%-6s %s" % (n, hasattr(KeyModifier, n)))

print("=== Env / App ===")
for n in ["getOS", "getOSVersion", "isWindows", "getSikuliVersion", "getClipboard"]:
    print("  Env.%-16s %s" % (n, hasattr(Env, n)))
for n in ["open", "focus", "close", "window", "focusedWindow", "isRunning", "getPID"]:
    print("  App.%-16s %s" % (n, hasattr(App, n)))

print("SURVEY_DONE")
