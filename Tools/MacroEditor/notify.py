# -*- coding: utf-8 -*-
"""Windows 시스템 알림(토스트).

매크로는 길게 돌고, 그동안 사용자는 편집기 창을 보고 있지 않다. 끝난 것을
창 안의 상태줄로만 알리면 놓친다. 그래서 Windows 알림 센터에 띄운다.

외부 패키지를 쓰지 않는다(편집기는 Python 3 + tkinter 만 쓴다).
PowerShell 로 WinRT 의 ToastNotificationManager 를 부른다.

구현에서 조심한 것 두 가지:

* **.ps1 파일을 만들지 않는다.** `-EncodedCommand` (UTF-16LE base64)로 넘긴다.
  BOM 없는 UTF-8 .ps1 을 Windows PowerShell 5.1 이 ANSI 로 읽어 한글이 깨지고,
  그러면 XML 파싱이 `HRESULT: 0xC00CE56D` 으로 실패한다. 실측으로 확인했다.
* **AppID 는 시작 메뉴에 등록된 것을 빌린다.** 등록되지 않은 임의의 문자열을
  쓰면 예외 없이 조용히 아무것도 뜨지 않는다. Windows PowerShell 의 AUMID 는
  Windows 설치에 늘 들어 있다.

알림은 부수적인 기능이다. 실패해도 예외를 밖으로 내보내지 않는다 -
알림 때문에 실행 결과 처리가 멈추면 안 된다.
"""

import base64
import os
import subprocess
import threading

# 시작 메뉴에 등록된 Windows PowerShell 의 AUMID.
APP_ID = (r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
          r"\WindowsPowerShell\v1.0\powershell.exe")

_POWERSHELL = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "System32", "WindowsPowerShell", "v1.0", "powershell.exe")

# 콘솔 창이 깜빡이지 않도록 (runner.py 와 같은 값)
_NO_WINDOW = 0x08000000

_SCRIPT = u"""$ErrorActionPreference = 'Stop'
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
[void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime]
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('%(doc)s')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%(app)s').Show($toast)
"""


def available():
    """이 환경에서 알림을 띄울 수 있는가."""
    return os.name == "nt" and os.path.exists(_POWERSHELL)


def _escape(text):
    """XML 텍스트로 안전하게 만든다.

    작은따옴표까지 `&apos;` 로 바꾸는 이유: 완성된 XML 을 PowerShell 의
    작은따옴표 문자열 안에 넣기 때문이다. 따옴표가 하나라도 살아 있으면
    스크립트가 그 자리에서 끊긴다.

    줄바꿈을 포함한 공백은 하나로 줄인다. 토스트는 어차피 한 줄로 보여 주고,
    스크립트가 여러 줄로 갈라지는 것도 막는다.
    """
    out = u"%s" % (text if text is not None else u"")
    out = out.replace(u"&", u"&amp;").replace(u"<", u"&lt;")
    out = out.replace(u">", u"&gt;").replace(u'"', u"&quot;")
    out = out.replace(u"'", u"&apos;")
    return u" ".join(out.split())


def notify(title, message, on_error=None):
    """알림 하나를 띄운다. 띄우기를 시도했으면 True.

    PowerShell 을 띄우고 기다리지 않는다 - 알림 하나에 GUI 가 멈추면 안 된다.
    끝난 프로세스는 뒷정리 스레드가 거둔다.
    """
    if not available():
        return False

    doc = (u'<toast duration="short"><visual>'
           u'<binding template="ToastGeneric">'
           u'<text>%s</text><text>%s</text>'
           u'</binding></visual></toast>'
           % (_escape(title), _escape(message)))
    script = _SCRIPT % {"doc": doc, "app": APP_ID}
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    try:
        proc = subprocess.Popen(
            [_POWERSHELL, "-NoProfile", "-NonInteractive",
             "-EncodedCommand", encoded],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    except OSError as exc:
        if on_error:
            on_error(u"Windows 알림을 띄우지 못했습니다: %s" % exc)
        return False

    threading.Thread(target=proc.wait, daemon=True).start()
    return True
