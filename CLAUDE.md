# 프로젝트 목적

이 프로젝트는 Windows PC에서 OculiX를 이용한 화면 기반 GUI 자동화 환경을 안전하고 재현 가능하게 구축하고, 이후 OculiX 매크로를 작성·테스트·관리하는 것을 목적으로 한다.

주요 자동화 기능은 다음과 같다.

1. 화면 특정 좌표의 마우스 이동/좌클릭/우클릭
2. Mouse Down / Mouse Up / Drag
3. 키보드 Key Down / Key Up
4. 동작 사이 Delay
5. 특정 화면 영역에서 지정 이미지가 나타날 때까지 대기
6. 이미지 유사도 threshold 지정
7. 특정 이미지가 사라질 때까지 대기
8. 지정 좌표의 Pixel RGB 값 검사
9. RGB tolerance를 사용한 유사 색상 판정
10. 동작을 함수 단위로 분리하여 재사용
11. Timeout, Retry, Error handling
12. 향후 복수 매크로를 모듈화하여 관리

# 작업 환경

* OS: Windows
* Shell: PowerShell 우선 사용
* 자동화 도구: OculiX
* Java Runtime/JDK: OculiX 공식 요구사항을 만족하는 LTS JDK
* 우선 후보: Eclipse Temurin JDK 21 x64
* OculiX 설치 위치 (실제 경로):

```text
D:\Apps\oculixapi-4.0.0-windows.jar     ← 배포 JAR 원본
D:\Apps\oculixapi-4.0.0-windows\        ← 위 JAR을 풀어놓은 디렉터리
```

`C:\Tools\OculiX\`는 사용하지 않는다.

버전을 올릴 때는 실제 작업 시점의 최신 안정 버전을 공식 사이트와 공식 GitHub에서 다시 확인하고 버전 번호를 결정한다.

## 확인된 사실 (2026-08-15 공식 출처 조회 결과)

아래는 공식 사이트/GitHub에서 직접 확인한 내용이다. 시간이 지나면 다시 확인한다.

**프로젝트 계보**

* Sikuli (MIT, 2009) → SikuliX (Raimund Hocke "RaiMan", 2010–2025) → OculiX (Julien Mer, 2026~)
* RaiMan이 개발을 중단한 뒤 Julien Mer가 원저자 동의 하에 인수하여 OculiX로 개명했다.
* 구 저장소 `oculix-org/SikuliX1`은 2026-03-03 archive 되었다. 개발/릴리스/문서/커뮤니티는 모두 OculiX로 이동했다.
* Java 패키지 namespace는 하위 호환을 위해 `org.sikuli.*`를 그대로 유지한다.
* 기존 SikuliX Jython 스크립트와 `.sikuli` bundle은 drop-in 호환이라고 명시되어 있다.

**최신 릴리스**

* v4.0.0 (2026-07-09 published)
* Windows 배포 파일: `oculixide-4.0.0-windows.jar` (약 130MB, IDE), `oculixapi-4.0.0-windows.jar` (약 69MB, API only)
* GitHub Release asset의 `digest` 필드로 SHA-256 확인 가능 → 다운로드 후 반드시 대조한다.
* 참고: 공식 설치 문서 본문의 예시 명령은 아직 3.0.3 기준으로 적혀 있다. 버전 번호는 Releases 페이지를 기준으로 한다.

**요구 사항**

* Java(JDK): 최소 11, 권장 17 또는 21 LTS. Eclipse Temurin / Azul Zulu 등 인증 OpenJDK 빌드.
  → 본 프로젝트의 Temurin JDK 21 x64 선택은 권장 범위 안에 있다.
* Windows 10 이상, x86-64, RAM 최소 1GB(권장 4GB)
* `WinUtil.dll`, OpenCV JNA binaries, Tesseract, OCR data가 모두 JAR 내부에 포함되어 있다.
  → MSVC runtime 별도 설치나 PATH 설정이 필요 없다. 불필요한 시스템 변경을 하지 않는다.

**실행 방법 (공식 안내)**

```powershell
java -jar oculixide-4.0.0-windows.jar
```

## 로컬 환경 실측 상태 (2026-08-15 확인)

**보유 파일**

```text
D:\Apps\oculixapi-4.0.0-windows.jar     69,511,191 bytes
D:\Apps\oculixapi-4.0.0-windows\        위 JAR의 압축 해제본
```

**무결성 검증 완료**

```text
로컬 SHA-256 : 98df67c7253bd79fde69f4045340d1a8fc8cef300734d71f69a66b9ca09e03c9
공식 digest  : 98df67c7253bd79fde69f4045340d1a8fc8cef300734d71f69a66b9ca09e03c9
크기         : 69,511,191 bytes (공식 asset과 일치)
→ 일치. 공식 배포본이 맞다.
```

**미해결 사항 3건 — 2026-08-15 처리 결과**

1. ~~보유한 것은 `oculixapi`뿐이고 IDE가 없다.~~ → **해결됨.**
   `oculixide-4.0.0-windows.jar`를 `D:\Apps\`에 추가 설치하고 공식 digest와 대조 완료.

2. `oculixapi` JAR에는 `Main-Class`가 없다 (`java -jar`로 실행 불가, classpath 라이브러리).
   → **스크립트 실행에는 `oculixide-4.0.0-windows.jar`를 사용한다.** 아래 "실행 방법" 참조.

3. ~~이 PC에 Java가 설치되어 있지 않다.~~ → **해결됨. 아래 "JDK 설치 기록" 참조.**

## 실행 방법 (검증된 방식)

```powershell
# IDE 실행
D:\Apps\jdk-21.0.12+8\bin\java.exe -jar D:\Apps\oculixide-4.0.0-windows.jar

# 스크립트를 IDE 없이 실행 - 자동화 검증에 사용하는 방식
D:\Apps\jdk-21.0.12+8\bin\java.exe -jar D:\Apps\oculixide-4.0.0-windows.jar -r <경로>.sikuli -c
```

`-r` 실행, `-c` stdout 출력, `-d <n>` 디버그, `-f` 로그파일, `--` 이후는 `sys.argv`로 전달.

## 검증 상태 (2026-08-21)

상세는 `Docs\Environment.md` 참조. 요약: **`GuiAutomationTest` 20/20 전부 통과.**
화면 읽기(이미지 매칭 score 0.9964, Region 제한, similarity, Pixel RGB/tolerance,
모든 timeout)와 입력 주입(`click`, `mouseDown/Up`, `keyDown/Up`, `type`, `waitVanish`)
모두 정상이다. 판정은 대상 앱이 실제 수신한 이벤트로 대조했다.

글자 인식(OCR)도 검증했다. 한국어 데이터를 설치해 `graphtest.py` 79/79 통과이고,
한글을 찾아 클릭했을 때 대상 창이 실제로 그 라벨의 클릭을 받는 것까지 대조했다.

게임(Mabinogi Mobile)이 실행 중이면 안티치트가 합성 입력을 전역 차단한다.
게임 프로세스만 종료하면 되고 `BlackCipher64.aes`가 남아 있어도 무방하다.
안티치트 우회는 지침의 "안전 범위"에 따라 시도하지 않는다.

**2026-08-15에 기록했던 "다중 모니터 좌표계 불일치"는 잘못된 진단이었다.**
입력이 차단되어 마우스가 안 움직인 것을 좌표 오차로 오인한 것이다.
재측정 결과 `Screen(0)` 좌표 오차는 0이고 JVM DPI 플래그도 불필요하다.

## 자동화 테스트 시 지켜야 할 것

* 사용자 프로세스를 종료하지 않는다. 특히 메모장 등 미저장 문서를 가진 앱은
  `Stop-Process` 대상으로 삼지 않는다. 내가 연 창만 `WM_CLOSE`로 닫는다.
* Windows 11 메모장은 패키지 앱이라 자동화 대상으로 부적합하다
  (`MainWindowHandle`이 0, 세션 복원으로 사용자 문서가 함께 열림).
  검증에는 전용 창 `Scripts\Tests\TestTarget.ps1`을 사용한다.
* 이 PC는 모니터 4대에 스케일링이 혼재(125% / 150%)한다.
  자동화는 주 모니터 `Screen(0)`으로 한정한다.
  **화면 인덱스 순서는 실행마다 바뀐다.** 주 모니터만 항상 `Screen(0)`이다.
* **화면보호기가 켜지면 화면이 전부 검정으로 읽히고 클릭도 전달되지 않는다.**
  프로그램적으로 해제되지 않으므로 장시간 매크로 전에는 꺼야 한다(사용자 판단 사항).
  이 PC 기본값은 **60초**라 조금만 손을 떼면 바로 켜진다
  (`HKCU\Control Panel\Desktop` 의 `ScreenSaveTimeOut`).
  증상은 화면이 아니라 **마우스 경고**로 먼저 나타난다.
  ```text
  RobotDesktop: checkMousePosition: should be L[444,333]@S(0) - but is L[1366,2142]@S(2)!
  Mouse: not possible to get mouse position (PointerInfo == null)
  ```
  화면보호기가 도는 동안 `MouseInfo.getPointerInfo()` 가 null 을 돌려서,
  OculiX 가 **마지막으로 알던 좌표**를 그대로 쓴다. 그래서 "옮긴 곳이 아니라
  이전 자리에 있다" 는 경고가 나온다. 좌표계 문제로 오인하기 쉬우니
  이 경고를 보면 **먼저 유휴 시간과 화면보호기부터** 확인한다.
* 템플릿은 단색·무특징 영역을 피한다. 단색 템플릿은 화면의 다른 같은 색 영역과
  매칭되어 `waitVanish`가 영원히 False를 반환하게 만든다. 검색은 Region으로 제한한다.
* **엔진 코드에서 `click()` 같은 OculiX 전역 함수를 직접 부르지 않는다.**
  전역 함수는 실행 중인 `.sikuli` 네임스페이스에만 주입되어 import된 모듈에서는
  `NameError`가 난다. `Screen`/`Region` 인스턴스 메서드를 쓴다.
* **좌표를 캐시해 두고 클릭하지 않는다.** 창은 언제든 움직인다.
  검증 중 낡은 좌표를 믿고 클릭해 사용자의 Chrome 창을 누른 사고가 있었다.
  좌표는 이미지로 찾은 결과에서 얻고, 고정 좌표를 쓴다면 대상 창이 그 자리에
  있는지 먼저 확인한다. 이것이 "이미지 기반 탐색 우선" 원칙의 실질적 이유다.

## JDK 설치 기록 (2026-08-15 완료)

**설치 내역**

```text
버전     : Eclipse Temurin jdk-21.0.12+8 (LTS, 2026-07-24 릴리스)
경로     : D:\Apps\jdk-21.0.12+8\
방식     : zip 배포판 수동 전개 (installer/MSI 미사용, 관리자 권한 미사용)
파일     : OpenJDK21U-jdk_x64_windows_hotspot_21.0.12_8.zip
크기     : 205,069,442 bytes
출처     : https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12_8.zip
SHA-256  : 9ba963ee2371874a74185d18bc7bb2ab9407df7683300855ed7606e0662321d0
검증     : Adoptium 공식 API 제공 checksum과 대조하여 일치 확인
동작확인 : java -version / javac -version 모두 21.0.12 정상 출력
```

**환경 변수 (User 스코프)**

```text
JAVA_HOME = D:\Apps\jdk-21.0.12+8
Path      = D:\Apps\jdk-21.0.12+8\bin  을 맨 앞에 추가
```

주의사항:

* User `Path`는 레지스트리 타입이 `REG_EXPAND_SZ`(ExpandString)이고 `%USERPROFILE%` 참조를 포함한다.
  `[Environment]::SetEnvironmentVariable(...,'User')`를 쓰면 `REG_SZ`로 바뀌어 기존 `%USERPROFILE%` 항목이 깨진다.
  반드시 다음 방식으로 수정한다.

```powershell
Set-ItemProperty -Path 'HKCU:\Environment' -Name 'Path' -Type ExpandString -Value $new
```

* Path 항목은 `%JAVA_HOME%\bin`이 아니라 절대 경로를 쓴다.
  변수 전개 동작을 이 환경에서 확실히 검증할 수단이 없었기 때문이다.
  JDK 버전을 올릴 때는 `JAVA_HOME`과 `Path` **두 값을 모두** 수정해야 한다.
* Machine 스코프는 건드리지 않았다. 현재 세션에 관리자 권한이 없다.
  User 스코프만으로 이 사용자의 모든 프로세스에 적용되므로 실사용상 차이는 없다.
* 변경 전 원본 환경 변수 백업: `Docs\env-backup-2026-08-15.txt`
* 기존 `%USERPROFILE%\.dotnet\tools` 항목은 실제 디렉터리가 없다. 이 작업 이전부터의 상태이며 건드리지 않았다.

**압축 해제본 관련**

`D:\Apps\oculixapi-4.0.0-windows\`는 설치 결과물이 아니라 JAR을 그대로 푼 내용이다
(`org\`, `com\`, `META-INF\` 등 패키지 구조). OculiX 실행에는 원본 `.jar` 파일을 사용한다.
해제본은 내부 구조 확인 용도로만 참조하고, 삭제 여부는 사용자가 판단한다.

**Windows 관련 공식 언급**

* 다중 모니터는 `Screen(n)`으로 구분된다.
* High DPI 환경에서 캡처 시점과 재생 시점의 scaling 비율이 다르면 매칭이 실패할 수 있고, 이 경우 `Pattern("foo.png").similar(...)` 값을 낮추라고 안내한다.
  → 본 문서의 "DPI / 해상도" 원칙(스케일링 고정)을 우선 적용하고, threshold 하향은 그 다음 수단으로 둔다.

**공식 출처**

* 홈페이지: <https://oculix.org/>
* 문서: <https://docs.oculix.org/>
* 저장소: <https://github.com/oculix-org/Oculix>
* Releases: <https://github.com/oculix-org/Oculix/releases>

# 중요 작업 원칙

## 1. 최신 정보 확인

내부 지식만으로 현재 버전을 단정하지 않는다.

설치 전에 반드시 공식 자료에서 다음을 확인한다.

* OculiX 최신 Stable Release
* 요구 Java/JDK 버전
* Windows 설치 방법
* 필요한 추가 dependency 존재 여부
* 알려진 Windows 관련 설치 문제

가능하면 다음과 같은 1차 출처만 사용한다.

* OculiX 공식 홈페이지/문서
* `oculix-org/Oculix` 공식 GitHub 저장소 및 Releases
* Eclipse Adoptium 공식 사이트
* Microsoft 공식 문서
* Oracle/OpenJDK 공식 Java API

블로그, 파일 공유 사이트, 비공식 재배포 사이트의 실행 파일/JAR은 설치하지 않는다.

## 2. 보안

다운로드 파일은 반드시 공식 배포처에서 받는다.

가능하면 다운로드 후 다음을 기록한다.

* 파일명
* 다운로드 URL 또는 Release 출처
* 버전
* SHA-256

PowerShell 예:

```powershell
Get-FileHash <파일경로> -Algorithm SHA256
```

공식 Release에 checksum이 제공된다면 비교한다.
공식 checksum이 제공되지 않는 경우 임의의 값을 정상 값이라고 판단하지 않는다.

## 3. 관리자 권한

불필요한 관리자 권한을 사용하지 않는다.

관리자 권한이 반드시 필요한 작업이 발생하면 바로 실행하지 말고:

1. 왜 필요한지
2. 어떤 변경이 이루어지는지
3. 더 낮은 권한으로 가능한 대안이 없는지

를 먼저 알려준다.

일반 사용자 권한으로 수행 가능한 설치와 설정을 우선한다.

## 4. 기존 환경 보호

기존 Java/JDK가 설치되어 있다면 바로 삭제하거나 PATH를 덮어쓰지 않는다.

먼저 다음을 조사한다.

```powershell
java -version
javac -version
where.exe java
Get-Command java -All
```

기존 개발 환경과 충돌 가능성을 평가한다.
기존 JDK를 제거하지 않고 OculiX용 JDK를 추가 설치하는 것을 우선 검토한다.

## 5. 명령 실행 방식

단순히 사용자가 직접 할 명령을 설명하는 것보다, Agent가 실제 명령 실행 권한을 가지고 있다면 직접 수행한다.

다만 다음 작업은 사용자에게 알리고 신중하게 처리한다.

* 관리자 권한 요청
* 기존 프로그램 삭제
* PATH 등의 시스템 환경변수 대규모 수정
* 방화벽 변경
* Defender 예외 등록
* Smart App Control 비활성화
* 보안 기능 비활성화
* 레지스트리 변경
* 외부에서 받은 미검증 실행파일 실행

보안 기능을 OculiX 때문에 임의로 비활성화하지 않는다.

# OculiX 개발 원칙

## 화면 인식 우선

가능하면 절대 좌표만 사용하는 것보다 이미지 기반 탐색을 우선한다.

예:

```python
target = Pattern("confirm.png").similar(0.90)

match = exists(target, 10)

if match:
    click(match)
```

단, UI 위치가 고정되고 좌표 방식이 훨씬 단순한 경우 좌표 방식도 사용할 수 있다.

## Region 제한

이미지 검색은 가능한 한 전체 화면 대신 작은 Region에서 실행한다.

예:

```python
searchRegion = Region(1500, 600, 900, 700)

target = Pattern("confirm.png").similar(0.90)

match = searchRegion.exists(target, 10)
```

목적:

* 화면 캡처/검색 부하 감소
* false positive 감소
* 반응 속도 향상

## 무한 Wait 금지

실사용 매크로에서는 가능하면 무한정 기다리지 않는다.

좋은 예:

```python
match = region.exists(target, 30)

if not match:
    print("Timeout")
    return False
```

다음 요소를 고려한다.

* Timeout
* Retry
* 실패 로그
* 안전한 종료

## 함수 단위 분리

긴 스크립트 하나에 모든 동작을 작성하지 않는다.

예:

```python
def open_menu():
    pass


def enter_content():
    pass


def wait_complete():
    pass


def claim_reward():
    pass
```

상위 실행 코드는 가능하면 다음처럼 읽히게 한다.

```python
open_menu()

if not enter_content():
    exit(1)

if not wait_complete():
    exit(1)

claim_reward()
```

## 글자 찾기 (OCR)

이미지 대신 화면 글자로 찾을 수 있다. 다만 이미지 검색보다 훨씬 까다롭다.
실측 근거는 `Docs\Environment.md` 의 "글자 인식(OCR)" 절에 있다.

* **영역 제한이 이미지 검색보다 더 중요하다.** 주 모니터 전체 검색은 2.2초가
  걸렸고, 의도한 라벨이 아니라 다른 창의 같은 글자를 짚었다. 좁은 영역은 0.08초다.
* **한 번에 한 언어만 된다.** OculiX 는 `kor+eng` 조합을 거부한다.
  언어가 어긋나면 결과가 조용히 망가진다 (kor 로 영문을 읽으면 `Open Settings`
  가 `0060 56 네 ㅁ 095` 가 된다). 화면마다 `ocrLanguage` 로 전환한다.
* **한글·영문이 섞인 라벨은 한쪽만 질의에 넣는다.** `Hyper-V 관리자` 는
  `관리자` 로 찾는다.
* **한글은 음절마다 쪼개져 읽힌다** (`설정 열기` → `설 정 열 기`). 그래서
  OculiX 의 `existsText()` 로는 `설정` 을 못 찾는다. 엔진이 조각을 이어붙여
  찾으므로 매크로에서는 평범하게 `설정` 이라고 쓰면 된다.
* **인식이 통째로 비면 `ocrPsm` 을 의심한다.** 기본값은 11 이다.
  Tesseract 기본값 3 은 라벨에 여백을 조금만 둬도 빈 결과를 냈다 (5/9 → 9/9).
  로그의 `Empty page!!` 가 그 신호다.
* 글자가 자주 바뀌는 자리(숫자, 시간)는 이미지든 글자든 대상으로 삼지 않는다.

## Pixel Color 검사

OculiX 기본 기능만으로 원하는 기능이 불편한 경우 Jython에서 Java API를 사용할 수 있다.

예를 들어 Java AWT Robot의:

```text
Robot.getPixelColor(x, y)
```

를 이용할 수 있다.

단, 실제 구현 전 현재 OculiX/Jython 환경에서 정상 사용 가능한지 테스트한다.

Tolerance는 RGB 각 channel의 차이 또는 필요시 Euclidean distance 방식 중 적합한 것을 선택한다.
초기에는 이해하기 쉬운 channel별 tolerance를 우선한다.

## 이미지 캡처 원칙

템플릿 이미지는 다음 기준으로 만든다.

* 검색 대상의 특징적인 부분 포함
* 불필요한 주변 배경 최소화
* 지나치게 작은 이미지 피하기
* 애니메이션되는 부분 가능하면 제외
* 숫자/시간처럼 지속적으로 변하는 UI 제외
* Windows DPI/게임 UI Scale 영향을 고려

기본 similarity 시작값:

```text
0.90
```

탐지 실패가 반복된다면 실제 Match score를 조사한 뒤:

```text
0.90
→ 0.88
→ 0.85
```

등으로 조절한다.
무작정 threshold를 크게 낮추지 않는다.

## DPI / 해상도

이미지 매칭 안정성을 위해 테스트 환경에서는 다음 값의 변경을 최소화한다.

* Windows Display Scaling
* 화면 해상도
* 대상 프로그램 UI Scale
* 대상 프로그램 Window Size

설정값을 프로젝트 문서에 기록한다.

# 테스트 정책

처음에는 게임을 대상으로 테스트하지 않는다.

Windows의 일반 애플리케이션 또는 브라우저 등에서 다음 순서로 기능 검증을 한다.

1. OculiX 실행
2. Mouse Move
3. 좌클릭
4. Mouse Down/Up
5. Key Down/Up
6. Delay
7. Screenshot template capture
8. `find()` / `exists()`
9. `Pattern.similar()`
10. `Region`
11. `waitVanish()`
12. 함수 호출
13. Pixel color 검사
14. Timeout 처리

각 단계가 정상임을 확인한 후 다음 단계로 진행한다.

# 안전 범위

이 프로젝트의 목적은 일반적인 GUI 자동화 기술을 구축하는 것이다.

온라인 게임의 안티치트 또는 매크로 탐지 시스템이 자동화를 차단하는 경우:

* 프로세스 은닉
* 드라이버 수준 입력 위장
* 가상 HID를 이용한 탐지 회피
* 안티치트 분석
* 탐지 signature 회피
* VM/원격제어를 이용한 탐지 우회 최적화
* 탐지되지 않는 입력 경로 연구

등을 프로젝트 목표로 삼지 않는다.

해당 문제와 일반 GUI 자동화 구현을 분리한다.

# 파일/프로젝트 관리

프로젝트 루트는 다음과 같다.

```text
D:\Programming\Oculix-Automation\
```

이 루트 아래에 다음처럼 구성한다.

```text
D:\Programming\Oculix-Automation\
├─ CLAUDE.md
├─ 매크로 편집기.bat   GUI 편집기 실행 (더블클릭)
│
├─ Scripts\
│  ├─ Common\        공용 모듈 (pixel_util, macro_engine)
│  ├─ Runner\        RunMacro.sikuli - 범용 매크로 실행기
│  └─ Tests\         검증용 .sikuli 및 테스트 대상 창
│
├─ Macros\           매크로 정의. 폴더 하나가 매크로 하나 (macro.json + 이미지)
│                    폴더 안의 폴더 = 하위 매크로 (부모 전용, 이미지·설정 공유)
│
├─ Tools\
│  └─ MacroEditor\   GUI 편집기 (Python 3 + tkinter, 외부 의존성 없음)
│
├─ Assets\
│
├─ Logs\
│  └─ Runs\          편집기에서 돌린 실행 로그 (실행 하나당 파일 하나,
│                    가장 최근 것은 latest.log. 최근 60개만 남는다)
│
└─ Docs\
```

매크로는 코드가 아니라 **JSON 데이터**로 정의하고 `Scripts\Runner\RunMacro.sikuli`가
해석해서 실행한다. 형식은 `Docs\Macro-Format.md` 참조.
이유: GUI 편집기가 매크로를 다시 열어 수정할 수 있어야 하는데,
생성된 파이썬 코드를 되파싱하는 방식은 깨지기 쉽다.

형식은 두 가지이고 실행기가 자동으로 구분한다.

* **그래프** (`nodes` + `links`) — UE 블루프린트식 노드 연결. 새 매크로의 기본
* **트리** (`steps`) — 초기 형식. 그대로 실행되며 편집기에서 그래프로 변환 가능

매크로는 `call` 노드로 다른 매크로를 함수처럼 호출할 수 있다.
호출된 매크로는 **자기 폴더의 이미지와 자기 설정**을 쓰고, 흐름이 끝나면 호출 노드로 돌아온다.
순환 호출은 작성·실행 양쪽에서 막고, 호출 깊이는 16단계까지다.

**하위 매크로**는 예외다. 매크로 폴더 안에 중첩된 매크로(`Macros\부모\하위\macro.json`)로,
UE 블루프린트의 *함수*에 해당한다 — 라이브러리 매크로가 *다른 BP*라면 이쪽은 *그 BP의 함수*다.

* 라이브러리 목록에 뜨지 않는다. **부모와 형제만** 호출할 수 있고 참조는 `"./이름"`이다.
* 이미지는 **부모 폴더**의 것을 이름만으로 함께 쓴다. `settings`도 **부모 것을 상속**하며
  자기 `settings`는 두지 않는다 (같은 이미지가 부모/하위에서 다르게 잡히면 안 되기 때문).
* 중첩은 1단계까지. 편집기의 `하위 매크로` 패널에서 관리한다.
* 판정 기준은 참조 표기가 아니라 **파일 위치**다 (`graph_model.family_root`).
  경로로 남의 하위를 집어도 검사와 실행 양쪽에서 거부된다.

그래프는 연결이 자유로워 순환을 만들 수 있다. 이를 무한 루프로부터 막는 것은
`settings.maxSteps` / `maxSeconds` 실행 예산이며, **끌 수 없다.**
이 예산은 최상위 매크로 것 하나를 **호출 사슬 전체가 공유한다** —
호출된 매크로가 예산을 새로 시작하면 상한이 무의미해지기 때문이다.
**감시 매크로**(`watch` 조건을 가진 매크로)는 예상하지 못한 팝업 등을 처리한다.
매크로 최상위 `handlers` 에 걸면 그 매크로가 도는 동안 확인되고, 호출 단계마다
쌓였다가 걷힌다 (최상위 것 = 전역). **별도 스레드가 아니다** — 입력 장치가 하나라
동시에 돌면 입력이 섞인다. 메인이 노드 사이·대기 중에 `WatchManager.tick()` 으로
확인하고, 처리한 시간은 대기 노드의 제한시간에서 뺀다. 감시가 없는 명령줄 실행은
대기를 예전처럼 한 번에 기다린다 (편집기 실행은 일시정지를 받으려고 늘 잘라서
기다린다). 상세는 `Docs\Macro-Format.md` 의 감시 매크로 절.

`Scripts\Common\graph_model.py`가 핀 정의와 검증 규칙을 갖고 있고
편집기와 엔진이 이 파일을 함께 import 한다 (Python 2/3 양쪽 호환 문법으로 작성).

**Jython 주의:** `macro_engine.py`에서 한글이 든 서식 문자열은 반드시 `u"..."` 로
쓴다. 바이트 문자열에 unicode 인자를 넣으면 latin-1로 디코딩되어 글자가 깨진다.

OculiX 자체(런타임/JAR)는 프로젝트 루트가 아니라 별도 경로에 둔다.

```text
D:\Apps\oculixapi-4.0.0-windows.jar
D:\Apps\oculixapi-4.0.0-windows\
```

OculiX `.sikuli` bundle 구조를 존중하고 필요한 이미지가 script와 함께 관리되도록 한다.

테스트 코드와 실제 매크로 코드를 구분한다.

## 버전 관리

**2026-08-24부터 git 을 사용한다.** 그 전까지는 버전 관리가 없었다.

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
* 기록이 남지 않는 파일(`Macros\` 등 제외 대상)는 여전히 되돌릴 수 없다.
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

문제가 발생하면 추측으로 넘기지 말고:

```text
확인된 사실
가능성이 높은 원인
아직 확인되지 않은 부분
다음 진단 방법
```

을 구분한다.

오류 메시지는 가능한 한 원문을 보존한다.

# 최종 목표

최종적으로 다음과 같은 OculiX 자동화 코드 작성이 가능한 상태를 만든다.

```python
open_menu()

if not wait_for_target():
    log_error("Target timeout")
    exit(1)

perform_action()

if not wait_complete():
    log_error("Complete timeout")
    exit(1)

claim_result()
```

설치 완료 자체가 목표가 아니라, OculiX를 실행하고 실제 테스트 스크립트가 정상 작동하는 상태까지 검증하는 것이 1차 완료 조건이다.
