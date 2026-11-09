# 프로젝트 목적

Windows PC에서 OculiX를 이용한 화면 기반 GUI 자동화 환경을 안전하고 재현 가능하게 구축하고,
OculiX 매크로를 작성·테스트·관리한다.

다루는 자동화 기능: 좌표 마우스 이동·클릭, Mouse Down/Up/Drag, Key Down/Up, Delay,
영역 안 이미지 나타남/사라짐 대기, similarity threshold, Pixel RGB 와 tolerance 판정,
함수 단위 재사용, Timeout/Retry/Error handling, 복수 매크로 모듈화.

# 작업 전에 읽을 문서

| 문서 | 내용 | 언제 |
|---|---|---|
| `Docs\Architecture.md` | **코드 지도** — 파일 책임, 실행 흐름, 노드 추가 체크리스트, 테스트 명령 | 코드를 고치기 전에 먼저. 전체 소스를 다시 훑지 않는다 |
| `Docs\Macro-Format.md` | 매크로 JSON 형식과 각 노드·기능의 의미 | 매크로 동작을 바꾸거나 새 기능을 설계할 때 |
| `Docs\Environment.md` | 설치 기록, 실측값, Known Issues, 테스트 결과 | 환경 문제를 진단할 때 |
| `Docs\OculiX-Guide.md` | OculiX API 사용법 | OculiX API 를 직접 쓸 때 |

파일 책임·실행 흐름·노드 추가 절차가 바뀌면 같은 작업 안에서 `Docs\Architecture.md` 도 고친다.

# 작업 환경

* OS: Windows / Shell: PowerShell 우선
* JDK: Eclipse Temurin 21.0.12+8 — `D:\Apps\jdk-21.0.12+8\` (User `JAVA_HOME`, User `Path` 맨 앞)
* OculiX 4.0.0 — `D:\Apps\oculixide-4.0.0-windows.jar` (실행용), `D:\Apps\oculixapi-4.0.0-windows.jar`
  (`Main-Class` 없음, 라이브러리). `C:\Tools\OculiX\` 는 쓰지 않는다.
* 설치 경위, SHA-256, 공식 출처는 `Docs\Environment.md`.
* 버전을 올릴 때는 그 시점의 최신 안정 버전을 공식 사이트와 공식 GitHub Releases 에서 다시 확인한다.
* User `Path` 를 고칠 때는 `REG_EXPAND_SZ` 를 유지해야 한다 (`[Environment]::SetEnvironmentVariable` 금지).
  방법은 `Docs\Environment.md` 의 "환경 변수 수정 시 주의".

```powershell
# IDE 실행
D:\Apps\jdk-21.0.12+8\bin\java.exe -jar D:\Apps\oculixide-4.0.0-windows.jar

# 스크립트를 IDE 없이 실행 - 자동화 검증에 사용하는 방식
D:\Apps\jdk-21.0.12+8\bin\java.exe -jar D:\Apps\oculixide-4.0.0-windows.jar -r <경로>.sikuli -c
```

`-r` 실행, `-c` stdout 출력, `-d <n>` 디버그, `-f` 로그파일, `--` 이후는 `sys.argv`로 전달.

## 검증 상태

화면 읽기(이미지 매칭, Region, similarity, Pixel RGB/tolerance, timeout), 입력 주입(`click`,
`mouseDown/Up`, `keyDown/Up`, `type`, `waitVanish`), 한국어 OCR 이 모두 검증됐다.
판정은 대상 앱이 실제 수신한 이벤트로 대조했다. 상세와 최근 테스트 결과는 `Docs\Environment.md`.

* 게임(Mabinogi Mobile)이 실행 중이면 안티치트가 합성 입력을 전역 차단한다.
  게임 프로세스만 종료하면 되고 `BlackCipher64.aes` 가 남아 있어도 무방하다.
  안티치트 우회는 "안전 범위"에 따라 시도하지 않는다.
* "다중 모니터 좌표계 불일치"는 없다 (입력 차단을 좌표 오차로 오인했던 것). `Screen(0)` 좌표 오차 0,
  JVM DPI 플래그 불필요.

## 자동화 테스트 시 지켜야 할 것

* 사용자 프로세스를 종료하지 않는다. 특히 메모장 등 미저장 문서를 가진 앱은
  `Stop-Process` 대상으로 삼지 않는다. 내가 연 창만 `WM_CLOSE`로 닫는다.
* Windows 11 메모장은 자동화 대상으로 부적합하다. 검증에는 전용 창
  `Scripts\Tests\TestTarget.ps1` (한글은 `OcrTarget.ps1`)을 쓴다.
  `Start-Process -WindowStyle Hidden` 으로 띄우면 폼까지 숨는다. 콘솔만 숨기려면
  `-WindowStyle Hidden` 을 powershell 인자로 넘긴다 (`Docs\Architecture.md` 11절).
* 창 노드(`focusWindow`/`moveWindow`) 실측은 포커스를 빼앗는다. 사용자가 게임 등을 쓰는 중이면
  먼저 묻는다.
* 실행 중인 로그는 목록에 0바이트로 보이고 `latest.log`는 지난 실행의 내용이다.
  타임스탬프 파일을 공유 모드로 직접 연다 (`Docs\Environment.md` Known Issues 10).
  Java가 살아 있어도 일시정지일 수 있으니 `Logs\pause-*.flag`도 확인한다.
* 모니터 4대, 스케일링 혼재(125% / 150%). 자동화는 주 모니터 `Screen(0)`으로 한정한다.
  **화면 인덱스 순서는 실행마다 바뀐다.** 주 모니터만 항상 `Screen(0)`이다.
* **화면보호기가 켜지면 화면이 전부 검정으로 읽히고 클릭도 전달되지 않는다.**
  프로그램적으로 해제되지 않으므로 장시간 매크로 전에는 꺼야 한다(사용자 판단 사항).
  이 PC 기본값은 **60초**다 (`HKCU\Control Panel\Desktop` 의 `ScreenSaveTimeOut`).
  증상은 화면이 아니라 **마우스 경고**로 먼저 나타난다. 이 경고를 보면 좌표계보다
  **유휴 시간과 화면보호기부터** 확인한다 (Known Issues 7).
  ```text
  RobotDesktop: checkMousePosition: should be L[444,333]@S(0) - but is L[1366,2142]@S(2)!
  Mouse: not possible to get mouse position (PointerInfo == null)
  ```
* 템플릿은 단색·무특징 영역을 피한다. 단색 템플릿은 다른 같은 색 영역과 매칭되어
  `waitVanish`가 영원히 False를 반환하게 만든다. 검색은 Region으로 제한한다.
* **엔진 코드에서 `click()` 같은 OculiX 전역 함수를 직접 부르지 않는다.**
  전역 함수는 실행 중인 `.sikuli` 네임스페이스에만 주입되어 import된 모듈에서는
  `NameError`가 난다. `Screen`/`Region` 인스턴스 메서드를 쓴다.
* **좌표를 캐시해 두고 클릭하지 않는다.** 창은 언제든 움직인다. 낡은 좌표로 사용자의
  Chrome 창을 누른 사고가 있었다. 좌표는 이미지로 찾은 결과에서 얻고, 고정 좌표를 쓴다면
  대상 창이 그 자리에 있는지 먼저 확인한다.
* `graphtest.py` 처럼 실제 입력을 보내는 테스트는 게임을 끄고 돌린다. `scaletest.py` 는
  입력을 보내지 않는다. 테스트 목록과 명령은 `Docs\Architecture.md` 9절.

# 중요 작업 원칙

## 1. 최신 정보 확인

내부 지식만으로 현재 버전을 단정하지 않는다. 설치·업그레이드 전에 공식 자료에서 최신 Stable
Release, 요구 Java 버전, Windows 설치 방법, 추가 dependency, 알려진 Windows 문제를 확인한다.

1차 출처만 쓴다: OculiX 공식 홈페이지/문서, `oculix-org/Oculix` GitHub 및 Releases,
Eclipse Adoptium, Microsoft 공식 문서, Oracle/OpenJDK 공식 Java API.
블로그, 파일 공유 사이트, 비공식 재배포 사이트의 실행 파일/JAR은 설치하지 않는다.

## 2. 보안

다운로드 파일은 공식 배포처에서만 받고 파일명, URL 또는 Release 출처, 버전, SHA-256
(`Get-FileHash <파일> -Algorithm SHA256`)을 기록한다. 공식 checksum이 있으면 대조하고,
없으면 임의의 값을 정상이라고 판단하지 않는다.

## 3. 관리자 권한

불필요한 관리자 권한을 쓰지 않는다. 꼭 필요하면 실행 전에 왜 필요한지, 무엇이 바뀌는지,
더 낮은 권한의 대안이 없는지를 먼저 알린다. 일반 사용자 권한으로 되는 방법을 우선한다.

## 4. 기존 환경 보호

기존 Java/JDK를 바로 삭제하거나 PATH를 덮어쓰지 않는다. `java -version`, `javac -version`,
`where.exe java`, `Get-Command java -All` 로 먼저 조사하고, 제거보다 추가 설치를 우선 검토한다.

## 5. 명령 실행 방식

명령 실행 권한이 있으면 설명만 하지 말고 직접 수행한다. 다만 다음은 사용자에게 알리고
신중하게 처리한다: 관리자 권한 요청, 프로그램 삭제, PATH 등 환경변수 대규모 수정, 방화벽 변경,
Defender 예외 등록, Smart App Control 비활성화, 보안 기능 비활성화, 레지스트리 변경,
미검증 실행파일 실행. 보안 기능을 OculiX 때문에 임의로 비활성화하지 않는다.

# OculiX 개발 원칙

## 화면 인식 우선 / Region 제한 / 무한 Wait 금지

* 절대 좌표보다 이미지 기반 탐색을 우선한다. UI 위치가 고정되고 좌표가 훨씬 단순할 때만 좌표를 쓴다.
* 이미지 검색은 전체 화면 대신 작은 Region 에서 한다 (부하·오탐 감소, 반응 속도 향상).
* 실사용 매크로는 무한정 기다리지 않는다. Timeout, Retry, 실패 로그, 안전한 종료를 고려한다.

```python
target = Pattern("confirm.png").similar(0.90)
match = Region(1500, 600, 900, 700).exists(target, 10)
if not match:
    print("Timeout")
    return False
```

## 함수 단위 분리

긴 스크립트 하나에 모든 동작을 쓰지 않는다. 상위 흐름이 `open_menu()` →
`if not enter_content(): exit(1)` → `claim_reward()` 처럼 읽히게 나눈다.
매크로에서는 이것이 `call` 노드와 하위 매크로다.

## 글자 찾기 (OCR)

이미지 검색보다 훨씬 까다롭다. 실측 근거는 `Docs\Environment.md` 의 "글자 인식(OCR)" 절.

* **영역 제한이 이미지 검색보다 더 중요하다.** 주 모니터 전체 검색은 2.2초가
  걸렸고 다른 창의 같은 글자를 짚었다. 좁은 영역은 0.08초다.
* **한 번에 한 언어만 된다.** OculiX 는 `kor+eng` 조합을 거부한다. 언어가 어긋나면 결과가
  조용히 망가진다 (kor 로 영문을 읽으면 `Open Settings` → `0060 56 네 ㅁ 095`). 화면마다 `ocrLanguage` 로 전환한다.
* **한글·영문이 섞인 라벨은 한쪽만 질의에 넣는다.** `Hyper-V 관리자` 는 `관리자` 로 찾는다.
* **한글은 음절마다 쪼개져 읽힌다** (`설정 열기` → `설 정 열 기`). OculiX `existsText()` 로는
  `설정` 을 못 찾지만 엔진이 조각을 이어붙여 찾으므로 매크로에서는 평범하게 `설정` 이라고 쓴다.
* **인식이 통째로 비면 `ocrPsm` 을 의심한다.** 기본값은 11 이다. Tesseract 기본값 3 은 라벨에
  여백을 조금만 둬도 빈 결과를 냈다 (5/9 → 9/9). 로그의 `Empty page!!` 가 그 신호다.
* 글자가 자주 바뀌는 자리(숫자, 시간)는 이미지든 글자든 대상으로 삼지 않는다.

## 해상도 대응

상세는 `Docs\Macro-Format.md` 의 해상도 대응 절, 실측은 `Docs\Environment.md`.

* 매크로에는 **기준 좌표만** 저장한다. 해상도별 사본을 만들지 않는다.
  다른 환경에서는 실행할 때 변환하고, 찍은 값은 저장할 때 되돌린다.
* 배율의 기준은 모니터가 아니라 **게임 창 안쪽**이다. MBM_Daily 의 기준은 논리 (1,30) 1364x1072,
  왼쪽 2/3 스냅 창이다. 2560x1440 @125% → 1920x1080 @100% 의 배율은 0.75 가 아니라 0.93 이다.
* 가로세로비가 같아야 비례한다. 16:9 전체 화면은 대응하지 않는다.
* 게임 창 밖(실행기, 작업 표시줄, UAC)은 `"space": "screen"` 이다. 이미지를 줄이면 오히려 틀린다.
* 템플릿을 줄일 때 `Pattern.resize` 를 쓰지 않는다. 소수점을 버려서 점수가 0.05 까지 떨어진다.
  `Settings.AlwaysResize` 도 같다.
* 자동 축소는 점수가 보통 0.02~0.03, 크게는 0.06 내려간다. 빠듯한 템플릿은 그 환경에서
  다시 찍는다. 편집기가 `@가로x세로` 폴더에 넣으므로 기준 이미지는 다치지 않는다.
* **Windows 배율을 바꾼 뒤에는 게임을 완전히 다시 시작한다.** 게임은 시작할 때의 DPI 로
  제목 표시줄을 그려서, 그대로 두면 창 안쪽이 기준과 최대 6px 달라진다.
* 창 차이가 8px 이하면 같은 창으로 본다 (`SAME_RECT_SLACK`). 좌표는 보정하지 않고 축소본도
  만들지 않는다. 대신 검색 영역을 그 차이만큼 넓힌다. 넓히지 않으면 빠듯한 노드의 대상이 영역 밖으로 나간다.
* `settings.scaling` 이 없는 매크로와 기준 환경의 동작은 바꾸지 않는다.
  이 조건이 깨지면 지금 도는 매크로가 망가진다.
* `moveWindow` 의 좌표는 게임 창과 무관한 화면 좌표라 **변환하지 않는다** (필드 타입 `screenpoint`).

## Pixel Color 검사

OculiX 기본 기능이 불편하면 Jython 에서 Java API(`Robot.getPixelColor(x, y)` 등)를 쓸 수 있다.
구현 전에 현재 OculiX/Jython 환경에서 동작하는지 테스트한다. Tolerance 는 이해하기 쉬운
채널별 차이를 우선하고, 필요할 때 Euclidean distance 를 쓴다 (`Scripts\Common\pixel_util.py`).

## 이미지 캡처 원칙

* 대상의 특징적인 부분을 담고 주변 배경은 최소화한다. 지나치게 작은 이미지는 피한다.
* 애니메이션, 숫자/시간처럼 계속 변하는 UI 는 제외한다. Windows DPI / 게임 UI Scale 영향을 고려한다.
* similarity 시작값은 **0.90**. 탐지 실패가 반복되면 실제 Match score 를 조사한 뒤
  0.90 → 0.88 → 0.85 처럼 조금씩 내린다. 무작정 크게 낮추지 않는다.

## DPI / 해상도 고정

이미지 매칭 안정성을 위해 Windows Display Scaling, 화면 해상도, 대상 프로그램 UI Scale,
대상 프로그램 Window Size 의 변경을 최소화하고, 설정값을 프로젝트 문서에 기록한다.

# 안전 범위

이 프로젝트의 목적은 일반적인 GUI 자동화 기술을 구축하는 것이다.

온라인 게임의 안티치트 또는 매크로 탐지 시스템이 자동화를 차단하는 경우 다음을 프로젝트 목표로
삼지 않는다: 프로세스 은닉, 드라이버 수준 입력 위장, 가상 HID를 이용한 탐지 회피, 안티치트 분석,
탐지 signature 회피, VM/원격제어를 이용한 탐지 우회 최적화, 탐지되지 않는 입력 경로 연구.

해당 문제와 일반 GUI 자동화 구현을 분리한다.

# 파일/프로젝트 관리

프로젝트 루트: `D:\Programming\Oculix-Automation\`

```text
├─ CLAUDE.md
├─ 매크로 편집기.bat   GUI 편집기 실행 (더블클릭)
├─ Scripts\
│  ├─ Common\        공용 모듈 (macro_engine, graph_model, scale_runtime, pixel_util, window_util)
│  ├─ Runner\        RunMacro.sikuli - 범용 매크로 실행기
│  └─ Tests\         검증용 .sikuli 및 테스트 대상 창
├─ Macros\           매크로 정의. 폴더 하나가 매크로 하나 (macro.json + 이미지)
│                    폴더 안의 폴더 = 하위 매크로 (부모 전용, 이미지·설정 공유)
│                    @가로x세로 = 그 화면에서 다시 찍은 이미지
│                    .scaled = 엔진이 만든 축소본 (지워도 된다)
├─ Tools\MacroEditor\  GUI 편집기 (Python 3 + tkinter, 외부 의존성 없음)
├─ Assets\
├─ Logs\Runs\        편집기 실행 로그 (실행당 파일 하나, latest.log, 최근 60개)
└─ Docs\
```

OculiX 런타임/JAR 은 프로젝트 밖(`D:\Apps\`)에 둔다. `.sikuli` bundle 구조를 존중하고
필요한 이미지가 script 와 함께 관리되게 한다. 테스트 코드와 실제 매크로 코드를 구분한다.

## 매크로 시스템의 불변 조건

구현 위치는 `Docs\Architecture.md`, 형식은 `Docs\Macro-Format.md`.

* 매크로는 코드가 아니라 **JSON 데이터**다. `RunMacro.sikuli` 가 해석해 실행한다.
  편집기가 다시 열어 고쳐야 하는데, 생성된 파이썬 코드를 되파싱하는 방식은 깨지기 쉽기 때문이다.
* 형식은 **그래프**(`nodes` + `links`, 새 매크로의 기본)와 **트리**(`steps`, 초기 형식)이고 실행기가 자동 구분한다.
* `call` 노드는 다른 매크로를 함수처럼 부른다. 호출된 매크로는 **자기 폴더의 이미지와 자기 설정**을 쓴다.
  순환 호출은 작성·실행 양쪽에서 막고, 호출 깊이는 16단계까지다.
* **하위 매크로**(`Macros\부모\하위\macro.json`)는 UE 블루프린트의 *함수*다.
  * 라이브러리에 뜨지 않고 **부모와 형제만** 호출한다. 참조는 `"./이름"`.
  * 이미지는 **부모 폴더** 것을 쓰고 `settings` 도 **부모 것을 상속**한다 (자기 settings 없음).
  * 중첩은 1단계까지. 판정 기준은 참조 표기가 아니라 **파일 위치**다 (`graph_model.family_root`).
* 순환으로부터 막는 것은 `settings.maxSteps` / `maxSeconds` 실행 예산이며 **끌 수 없다.**
  최상위 매크로의 예산 하나를 **호출 사슬 전체가 공유한다.**
* **감시 매크로**(`watch` 조건)는 예상하지 못한 팝업 등을 처리한다. 최상위 `handlers` 에 걸고
  호출 단계마다 쌓였다 걷힌다. **별도 스레드가 아니다** — 입력 장치가 하나라 메인이 노드 사이·대기 중에
  `WatchManager.tick()` 으로 확인하고, 처리 시간은 대기 노드의 제한시간에서 빼 준다.
* `graph_model.py` 는 편집기와 엔진이 함께 import 한다 — **Python 2/3 양쪽 호환 문법**만 쓴다.
  해상도 계산(`Transform`)도 같은 이유로 여기 있고, JVM 안에서만 되는 일은 `scale_runtime.py` 다.
* **Jython 주의:** `macro_engine.py` 에서 한글이 든 서식 문자열은 반드시 `u"..."` 로 쓴다.
  바이트 문자열에 unicode 인자를 넣으면 latin-1로 디코딩되어 글자가 깨진다.

## 버전 관리

**2026-08-24부터 git 을 사용한다.**

```text
저장소 루트 : D:\Programming\Oculix-Automation
origin    : https://github.com/ChoHJ93/OculiX-CustomGUI.git
기본 브랜치 : main
```

### 추적 범위

`.gitignore` 로 다음을 제외한다.

* **`Macros\`** — 매크로 정의와 템플릿 이미지. **사용자 결정으로 외부 공개하지 않는다.**
  → clone 한 환경에는 매크로가 없다. 이 폴더는 여전히 백업 대상이다.
* `Backups\`, `*.bak-*` — 수동 백업
* `Logs\` 내용물 — 폴더 자체는 `.gitkeep` 으로 유지한다
  (테스트 스크립트가 절대경로로 `Logs\target_state.txt` 를 쓴다)
* `tesseract-lastseen.json` — 이 PC 해상도에 묶인 OCR 좌표 캐시
* `__pycache__\`, `*.pyc`, `*$py.class` — 컴파일 산출물

### 지킬 것

* 작업 전에 `git status` 와 `git branch` 로 현재 상태를 먼저 확인한다.
* 기록이 남지 않는 파일(`Macros\` 등 제외 대상)은 여전히 되돌릴 수 없다.
  덮어쓰기 전에 내용을 먼저 확인하고, 큰 변경 전에는 사본을 남긴다.
* 삭제는 추적 여부와 무관하게 사용자에게 알리고 진행한다.
* 커밋과 push 는 사용자가 요청할 때만 한다. 먼저 제안하지 않는다.
* 원격에 올리기 전에 새로 추가된 파일에 공개하면 안 되는 것이 섞였는지 확인한다
  (화면 캡처, 계정 정보, 로컬 경로).

# Agent 응답 방식

작업을 수행할 때 중요한 단계마다 다음을 간결하게 알려준다.

```text
[현재 상태]
[확인 결과]
[수행한 변경]
[다음 작업]
```

문제가 발생하면 추측으로 넘기지 말고 다음을 구분한다.

```text
확인된 사실
가능성이 높은 원인
아직 확인되지 않은 부분
다음 진단 방법
```

오류 메시지는 가능한 한 원문을 보존한다.

# 목표

OculiX 를 실행하고 실제 테스트 스크립트가 정상 작동하는 상태까지 검증하는 1차 목표는 달성했다
("검증 상태" 참조). 지금 목표는 다음처럼 읽히는 매크로를 안정적으로 작성·실행·관리하는 것이다.

```python
open_menu()
if not wait_for_target():
    log_error("Target timeout"); exit(1)
perform_action()
if not wait_complete():
    log_error("Complete timeout"); exit(1)
claim_result()
```
