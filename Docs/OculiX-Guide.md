# OculiX 사용 가이드

이 문서의 API 목록과 기본값은 **이 PC의 OculiX 4.0.0에서 직접 조회해 확인한 것**이다
(`Scripts\Tests\ApiSurvey.sikuli`). 다른 버전이나 다른 PC에서는 다시 확인해야 한다.

---

## 1. 지금 환경이 어떻게 구성되어 있나

```text
D:\Apps\jdk-21.0.12+8\                  Java 21 - OculiX가 도는 토대
D:\Apps\oculixide-4.0.0-windows.jar     IDE 겸 실행기. 실제로 쓰는 파일
D:\Apps\oculixapi-4.0.0-windows.jar     라이브러리용. 지금은 안 씀
```

JAR 하나에 전부 들어 있다. OpenCV(이미지 매칭), Tesseract(문자 인식),
Jython 2.7.4(스크립트 언어), Windows 네이티브 DLL까지 내장이라 추가 설치가 없다.

**OculiX가 하는 일은 결국 두 가지다.**

1. 화면을 캡처해서 이미지/색을 **읽는다**
2. 마우스·키보드 이벤트를 **주입한다**

이 PC에서 1번은 완벽히 동작하고, 2번은 현재 안티치트에 막혀 있다(9절 참조).

```text
D:\Programming\Oculix-Automation\
├─ Scripts\
│  ├─ Common\      여러 매크로가 공유하는 모듈 (pixel_util.py)
│  └─ Tests\       .sikuli 프로젝트들
├─ Assets\         공용 이미지 (번들 밖에 둘 것만)
├─ Logs\           실행 로그
└─ Docs\           이 문서들
```

---

## 2. 실행하는 두 가지 방법

### IDE로 (이미지 캡처가 필요할 때)

```powershell
java -jar D:\Apps\oculixide-4.0.0-windows.jar
```

### 명령줄로 (작성 끝난 매크로를 돌릴 때)

```powershell
java -jar D:\Apps\oculixide-4.0.0-windows.jar -r <경로>.sikuli -c
```

| 옵션 | 뜻 |
|---|---|
| `-r <path>` | IDE 없이 스크립트 실행. 여러 개 나열하면 순차 실행 |
| `-c` | 출력을 stdout으로 (이게 없으면 콘솔에 안 보인다) |
| `-d <n>` | 디버그 상세도. 3까지 권장 |
| `-f <path>` | 로그를 파일로 |
| `-q` | 출력 억제 |
| `-- arg1 arg2` | 이후 인자를 스크립트의 `sys.argv`로 전달 |

**주의:** `popup()`, `input()`, `popAsk()`는 모달 창이라 사용자가 누를 때까지
멈춘다. 명령줄 자동 실행에는 쓰지 말고 `print()`를 써라.

---

## 3. `.sikuli` 번들이란

OculiX 프로젝트는 파일이 아니라 **폴더**다.

```text
MyMacro.sikuli\
├─ MyMacro.py      폴더 이름과 같은 .py 가 진입점
├─ button.png      이 스크립트가 쓰는 이미지들
└─ icon.png
```

`Pattern("button.png")`처럼 파일명만 쓰면 OculiX가 이 폴더 안에서 찾는다.
이미지가 스크립트와 함께 붙어 다니는 것이 핵심이다 — 폴더째 옮기면 그대로 동작한다.

`getBundlePath()`로 현재 번들 경로를 얻을 수 있다.

---

## 4. 핵심 개념 네 가지

### Screen — 모니터 하나

```python
Screen(0).getBounds()          # 주 모니터 영역
Screen.getNumberScreens()      # 이 PC는 4
```

### Region — 화면의 사각형 영역

```python
r = Region(100, 200, 400, 300)   # x, y, 너비, 높이
```

**Region이 성능의 핵심이다.** 전체 화면(2048×1152)을 뒤지는 것과
400×300만 뒤지는 것은 속도가 크게 다르고, 엉뚱한 곳의 비슷한 그림을
잘못 잡을 확률도 줄어든다.

Region끼리 조합할 수 있다.

```python
r.right(200)    # 오른쪽으로 200px 뻗은 영역
r.below(100)    # 아래쪽 100px
r.grow(20)      # 사방 20px 확장
r.nearby(50)    # 주변 50px
```

### Pattern — "이 이미지를 이 정확도로 찾아라"

```python
Pattern("ok.png").similar(0.90)   # 90% 이상 일치
Pattern("ok.png").exact()         # 완전 일치
Pattern("ok.png").targetOffset(0, 30)   # 찾은 지점에서 아래 30px를 클릭점으로
```

`targetOffset`이 유용하다. 레이블은 뚜렷한데 클릭할 버튼은 그 아래 있을 때,
레이블을 찾고 오프셋으로 클릭하면 된다.

### Match — 찾은 결과

```python
m = exists(Pattern("ok.png").similar(0.90), 5)
if m:
    print(m.getScore())    # 실제 일치율. 임계값 조정의 근거
    print(m.getX(), m.getY())
    m.highlight(2)         # 2초간 빨간 테두리 - 디버깅에 매우 유용
    click(m)
```

`m.getScore()`를 찍어보는 습관이 중요하다. 매칭이 실패할 때
threshold를 감으로 낮추지 말고 **실제 점수를 보고** 결정한다.

---

## 5. 자주 쓰는 API (4.0.0에서 존재 확인 완료)

### 찾기

```python
exists(pattern, timeout)     # 찾으면 Match, 없으면 None. 예외 안 남 ← 기본으로 쓸 것
find(pattern)                # 못 찾으면 FindFailed 예외
wait(pattern, timeout)       # 나타날 때까지 대기. 실패 시 예외
waitVanish(pattern, timeout) # 사라질 때까지 대기. True/False
findAll(pattern)             # 여러 개 전부
has(pattern)                 # 있는지만 확인
```

**`exists()`를 기본으로 써라.** 실패가 예외가 아니라 `None`이라 흐름 제어가 쉽다.

### 마우스

```python
click(target)          doubleClick(target)     rightClick(target)
hover(target)          mouseMove(target)
mouseDown(Button.LEFT) mouseUp(Button.LEFT)
dragDrop(from, to)     drag(from)   dropAt(to)
wheel(target, Button.WHEEL_DOWN, 3)
```

`target`은 `Match`, `Location`, `Pattern`, 이미지 파일명 아무거나 된다.

### 키보드

```python
type("hello")                          # 문자열 입력
type("a", KeyModifier.CTRL)            # Ctrl+A
type(Key.ENTER)
keyDown("a");  wait(0.3);  keyUp("a")  # 누른 상태 유지
paste("긴 텍스트")                      # 클립보드 경유 - 한글은 이게 안전
```

한글이나 긴 문자열은 `type()`보다 `paste()`가 안정적이다.

사용 가능한 상수: `Key.ENTER/TAB/ESC/SPACE/BACKSPACE/DELETE/F1~/UP/DOWN/WIN` 등,
`KeyModifier.CTRL/SHIFT/ALT/META`, `Button.LEFT/MIDDLE/RIGHT/WHEEL_UP/WHEEL_DOWN`.

### 대기

```python
wait(1.5)              # 그냥 1.5초 쉬기 (숫자를 주면 sleep)
sleep(1.5)             # 동일
```

### 기타

```python
capture(region)        # 영역 캡처, 임시 파일 경로 반환
getBundlePath()        # 현재 .sikuli 폴더
Env.getClipboard()
App("notepad.exe").open() / .focus() / .close()
App.focusedWindow()    # 지금 포커스된 창의 Region
```

### 문자 인식 (OCR)

Tesseract가 내장이라 바로 쓸 수 있다. 다만 이번에 동작 검증은 하지 않았다.

```python
region.text()          # 영역의 텍스트
region.textLines()
region.findText("확인")
```

---

## 6. Settings — 전역 동작 조정

이 PC의 현재 기본값이다.

```python
Settings.MinSimilarity    = 0.7    # Pattern에 similar() 안 쓰면 이 값 사용
Settings.AutoWaitTimeout  = 3.0    # timeout 생략 시 기본 대기
Settings.WaitScanRate     = 3.0    # 초당 화면 검사 횟수
Settings.MoveMouseDelay   = 0.5    # 마우스 이동에 쓰는 시간(초)
Settings.ClickDelay       = 0.0
Settings.TypeDelay        = 0.0
Settings.Highlight        = False  # True면 매칭마다 자동으로 테두리 표시
```

디버깅할 때 `Settings.Highlight = True`로 두면 매칭 위치가 눈에 보인다.

느린 프로그램을 다룰 때는 `Settings.MoveMouseDelay`를 키워서
사람처럼 천천히 움직이게 하면 UI가 따라오지 못해 생기는 실패가 줄어든다.

---

## 7. 이미지 캡처 워크플로우

### IDE에서 (일반적인 방법)

1. `java -jar D:\Apps\oculixide-4.0.0-windows.jar`
2. 스크립트 편집 중 캡처 버튼 → 화면이 어두워지면 영역 드래그
3. 코드에 이미지 썸네일이 삽입된다

### 코드로 (재현 가능해서 이쪽을 권장)

```python
import shutil, os
tmp = capture(Region(100, 200, 300, 80))
shutil.copyfile(tmp, os.path.join(getBundlePath(), "target.png"))
```

### 좋은 템플릿 이미지의 조건

* 대상의 **특징적인 부분**만. 주변 배경은 최소로
* 너무 작으면 안 된다 (오탐 급증). 대략 30×30 이상
* 애니메이션되는 부분 제외
* 숫자·시간처럼 계속 바뀌는 UI 제외
* 캡처할 때와 재생할 때의 **DPI 스케일링이 같아야 한다**

### threshold 정하는 법

```text
0.90 에서 시작
→ 실패하면 m.getScore() 를 찍어서 실제 점수 확인
→ 그 점수보다 조금 낮게 조정 (0.88 → 0.85)
→ 0.7 밑으로 내려가야 한다면 템플릿 이미지가 잘못된 것이다. 다시 캡처하라
```

참고로 이 PC에서 측정한 정상 매칭 점수는 **0.9964**였다.
제대로 된 템플릿이면 이 정도가 나온다.

---

## 8. pixel_util — 픽셀 색 검사

`Scripts\Common\pixel_util.py`. 이미지 매칭이 과한 경우(색만 바뀌는 상태 표시등 등)에 쓴다.

```python
import sys
sys.path.append("D:\\Programming\\Oculix-Automation\\Scripts\\Common")
import pixel_util

rgb = pixel_util.get_pixel_rgb(500, 300)
# (200, 30, 30)

pixel_util.is_color_similar(rgb, (200, 30, 30), 10)
# channel별 ±10 이내인지. tolerance에 (10, 5, 20) 처럼 채널별 지정도 가능

got = pixel_util.wait_pixel_color(500, 300, (30, 160, 60),
                                  tolerance=12, timeout=5.0, interval=0.1)
if got is None:
    print("색이 안 바뀜")

pixel_util.wait_pixel_change(500, 300, rgb, tolerance=10, timeout=5.0)
pixel_util.euclidean_distance((0,0,0), (10,0,0))
```

`wait_pixel_color`는 **timeout이 반드시 있고 절대 무한 대기하지 않는다.**
실측으로 2.0초 설정 시 2.07초에 종료하는 것을 확인했다.

---

## 9. 이 PC에서 반드시 알아야 할 것

### 합성 입력이 현재 차단되어 있다 (미해결)

`BlackCipher64.aes`(nProtect GameGuard 계열 안티치트)가 Mabinogi Mobile과
함께 실행 중이면 **시스템 전역으로 마우스·키보드 주입이 막힌다.**
OculiX 문제가 아니다 — Win32 `SetCursorPos`, `SendInput`도 똑같이 막힌다.

**매크로를 테스트하려면 게임을 종료해야 한다.**
화면 읽기(이미지 매칭, 픽셀)는 이 상태에서도 정상 동작한다.

### 모니터가 4대고 스케일링이 섞여 있다

```text
Display0 (주) 2560x1440 @ 125%
Display1      1920x1080 @ 150%
Display2      1440x2560 @ 125%  세로
Display3      2560x1440 @ 125%
```

Java가 좌표를 일관되지 않게 보고하는 문제가 관측되었다(크기는 논리값,
원점은 물리값). **자동화는 주 모니터 `Screen(0)`으로 한정하고,
가능하면 스케일링을 100%로 통일한 상태에서 작업하라.**

### 실행 중단 단축키가 없다

`Alt+Shift+C`는 SikuliX 2.0.0에서 제거되었다. 명령줄 실행 중 중단은
콘솔 `Ctrl+C` 또는 java 프로세스 강제 종료뿐이다.

**그래서 모든 대기에 timeout을 넣는 것이 필수다.** 이것이 유일하게
신뢰할 수 있는 안전장치다.

---

## 10. 매크로 작성 패턴

### 나쁜 예

```python
click("start.png")
wait(5)
click("next.png")
wait(5)
click("done.png")
```

고정 시간 대기라 느리면 실패하고 빠르면 시간을 낭비한다.
실패해도 그냥 다음 줄로 넘어가 엉뚱한 곳을 누른다.

### 좋은 예

```python
SEARCH = Region(100, 100, 600, 400)

def wait_and_click(image, timeout=10, similarity=0.90):
    """찾으면 클릭하고 True, 못 찾으면 로그 남기고 False."""
    m = SEARCH.exists(Pattern(image).similar(similarity), timeout)
    if not m:
        print("[FAIL] %s not found in %ds" % (image, timeout))
        return False
    click(m)
    return True


def main():
    if not wait_and_click("start.png"):
        return 1
    if not wait_and_click("next.png"):
        return 1
    if not wait_and_click("done.png"):
        return 1
    print("완료")
    return 0

main()
```

원칙 네 가지:

1. **Region으로 검색 범위를 좁힌다**
2. **모든 대기에 timeout**
3. **동작을 함수로 쪼갠다** — 상위 코드가 읽히도록
4. **실패하면 즉시 빠져나온다** — 계속 진행하지 않는다

### 시작 템플릿

`Scripts\Tests\MyFirstMacro.sikuli`에 주석 달린 실행 가능한 템플릿을 만들어 뒀다.
이걸 복사해서 시작하면 된다.

---

## 11. 디버깅

```python
Settings.Highlight = True       # 매칭 위치를 눈으로 확인
m.highlight(2)                  # 특정 매치만 2초 표시
print(m.getScore())             # 실제 일치율
```

```powershell
# 디버그 로그 켜기
java -jar D:\Apps\oculixide-4.0.0-windows.jar -r <경로>.sikuli -c -d 3
```

**매칭이 안 될 때 확인 순서**

1. 템플릿 이미지를 눈으로 열어본다 — 엉뚱한 걸 캡처하지 않았나
2. `exists()`의 timeout을 늘려본다 — 아직 안 나타난 것인가
3. `similar(0.7)`로 낮춰서 찾아지는지 본다 → 찾아지면 `getScore()` 확인
4. Region이 실제로 대상을 포함하는지 `Region(...).highlight(2)`로 확인
5. DPI 스케일링이 캡처 때와 같은지 확인

**입력이 안 먹을 때**는 9절을 먼저 의심하라. 이 PC에서는 그게 원인이었다.
