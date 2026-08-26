# -*- coding: utf-8 -*-
"""편집기 설정 저장 - 레이아웃, 창 크기, 프로젝트 트리 펼침 상태.

`Tools\\MacroEditor\\layout.json` 에 저장한다. 매크로 데이터와 무관한
편집기 개인 설정이므로 Macros 폴더에는 넣지 않는다.
지우면 기본 레이아웃으로 돌아간다.
"""

import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "layout.json")

DEFAULTS = {
    "geometry": "1320x860",
    "layout": None,          # docking.DockManager.get_layout() 결과
    "expanded": [],          # 프로젝트 트리에서 펼쳐 둔 폴더 경로
    "last_macro": None,
    "notify_on_done": True,  # 실행이 끝나면 Windows 알림
}


def load():
    """설정을 읽는다. 읽지 못하면 조용히 기본값을 쓴다.

    utf-8-sig 로 디코딩하는 이유: 이 파일을 메모장이나 PowerShell
    `Out-File -Encoding utf8` 로 손대면 BOM 이 붙어 json 파싱이 깨진다.
    그러면 레이아웃이 말없이 초기화되므로 BOM 을 허용한다.
    """
    data = dict(DEFAULTS)
    try:
        handle = open(PATH, "rb")
        try:
            raw = handle.read()
        finally:
            handle.close()
        stored = json.loads(raw.decode("utf-8-sig"))
        if isinstance(stored, dict):
            data.update(stored)
    except Exception:
        pass
    return data


def save(data):
    try:
        handle = open(PATH, "wb")
        try:
            handle.write(json.dumps(data, ensure_ascii=False,
                                    indent=2).encode("utf-8"))
        finally:
            handle.close()
        return True
    except Exception:
        return False
