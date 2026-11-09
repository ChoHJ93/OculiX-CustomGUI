# OculiX 자동화 환경 기록

작성: 2026-08-15
작성 방식: 아래 값은 모두 이 PC에서 실제 명령을 실행해 확인한 것이다.
확인하지 못한 항목은 추측하지 않고 `Unknown`으로 둔다.

---

## 시스템

```text
OS                : Windows 11 Pro 24H2
                    (레지스트리 ProductName은 "Windows 10 Pro"로 표시된다.
                     Windows 11에서 의도된 동작이며 build 26100 = Windows 11 24H2)
OS Build          : 26100.2894
OS Architecture   : 64-bit (AMD64)
Windows Session   : Session 1 / console / Active / UserInteractive=True
Agent 권한        : 일반 사용자 (IsAdmin=False)
```

## Java

```text
Java Vendor       : Eclipse Adoptium (Eclipse Temurin)
Java Version      : 21.0.12+8 LTS
                    OpenJDK Runtime Environment Temurin-21.0.12+8 (build 21.0.12+8-LTS)
                    OpenJDK 64-Bit Server VM (mixed mode, sharing)
Java Path         : D:\Apps\jdk-21.0.12+8\bin\java.exe
JAVA_HOME         : D:\Apps\jdk-21.0.12+8   (User 스코프)
PATH 등록         : D:\Apps\jdk-21.0.12+8\bin  (User PATH 맨 앞, 절대 경로)
설치 방식         : zip 배포판 수동 전개 (installer 미사용, 관리자 권한 미사용)
설치 전 상태      : 이 PC에 Java 없음. 기존 JDK 충돌 없음. 삭제한 것 없음.
다운로드 출처     : https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12%2B8/
                    OpenJDK21U-jdk_x64_windows_hotspot_21.0.12_8.zip
zip 크기          : 205,069,442 bytes
zip SHA-256       : 9ba963ee2371874a74185d18bc7bb2ab9407df7683300855ed7606e0662321d0
checksum 검증     : Adoptium 공식 API 제공 checksum과 대조 → 일치
OculiX 요구사항   : 최소 Java 11, 권장 17 또는 21 LTS → 충족
```

## OculiX

```text
OculiX Version      : 4.0.0
Release 날짜        : 2026-07-09
Stable 여부         : 최신 Stable. 전체 릴리스(v4.0.0 / v3.0.4 / v3.0.4-rc1 / v3.0.3) 중
                      prerelease/draft가 아닌 것 가운데 가장 최신이며, 더 최신 prerelease도 없음
OculiX IDE JAR      : oculixide-4.0.0-windows.jar
IDE Install Path    : D:\Apps\oculixide-4.0.0-windows.jar
IDE JAR 크기        : 130,253,370 bytes
IDE JAR SHA-256     : 07cd907da8c4264bdfbc97f87e253ff2a5875331c4205d598ac479385f77a5c5
IDE checksum 검증   : GitHub Release asset digest와 대조 → 일치
IDE Main-Class      : org.sikuli.ide.Sikulix

OculiX API JAR      : oculixapi-4.0.0-windows.jar
API Install Path    : D:\Apps\oculixapi-4.0.0-windows.jar
API JAR 크기        : 69,511,191 bytes
API JAR SHA-256     : 98df67c7253bd79fde69f4045340d1a8fc8cef300734d71f69a66b9ca09e03c9
API checksum 검증   : GitHub Release asset digest와 대조 → 일치
API Main-Class      : 없음 (MANIFEST에 Main-Class 미포함 → java -jar로 실행 불가, classpath 라이브러리)

Release Source      : https://github.com/oculix-org/Oculix/releases/tag/v4.0.0
공식 홈페이지       : https://oculix.org/
공식 문서           : https://docs.oculix.org/

번들 런타임         : Jython 2.7.4, OpenCV (nu.pattern), Tesseract 5.5.0
                      네이티브(WinUtil.dll, OpenCV JNA)가 JAR에 내장되어
                      MSVC runtime 별도 설치나 PATH 설정 불필요
프로젝트 계보       : Sikuli(MIT 2009) → SikuliX(RaiMan 2010-2025) → OculiX(Julien Mer 2026-)
                      Java 패키지 namespace는 org.sikuli.* 유지
                      구 저장소 oculix-org/SikuliX1은 2026-03-03 archive
```

## 실행 방법

```powershell
# IDE 실행
D:\Apps\jdk-21.0.12+8\bin\java.exe -jar D:\Apps\oculixide-4.0.0-windows.jar

# 스크립트를 IDE 없이 실행 (검증에 사용한 방식)
D:\Apps\jdk-21.0.12+8\bin\java.exe -jar D:\Apps\oculixide-4.0.0-windows.jar -r <경로>.sikuli -c
```

주요 CLI 옵션 (공식 문서 확인):

```text
-r, --run <path>   IDE 없이 스크립트 실행. 여러 개 순차 실행 가능
-c, --console      출력을 stdout으로
-d, --debug <n>    디버그 상세도 (3까지 권장)
-f, --logfile      로그 파일 경로
-q                 출력 억제
--  <args>         이후 인자는 스크립트의 sys.argv로 전달
```

## 디스플레이

모니터 4대 구성이며 **스케일링이 모니터마다 다르다**.

```text
Display0 (주)  : 2560 x 1440 물리 / 논리 2048 x 1152 / 스케일 125% / 원점 (0,0)
Display1       : 1920 x 1080 물리 / 논리 1280 x  720 / 스케일 150% / 원점 (195,1440)
Display2       : 1440 x 2560 물리 / 논리 1152 x 2048 / 스케일 125% / 원점 (2560,-262)  세로 배치
Display3       : 2560 x 1440 물리 / 논리 2048 x 1152 / 스케일 125% / 원점 (-2560,0)

Windows Display Resolution : 주 모니터 2560 x 1440
Windows Display Scaling    : 주 모니터 125% (Display1만 150%)
Virtual Screen (논리)      : X=-2048 Y=-210 W=5248 H=2082
```

### 게임 창 (2026-11-04 실측)

MBM_Daily 의 좌표와 이미지는 전체 화면이 아니라 이 창 기준이다.
스냅은 매크로가 직접 한다 (`Run_Nexon_Luncher_MBM` 의 `Win+Z -> 5 -> 1`).

```text
창          UnityWndClass / "마비노기 모바일" / 관리자 권한으로 실행
창 사각형   물리 (-8,0) 1723x1388
창 안쪽     물리 (1,38) 1705x1341  =  논리 (1,30) 1364x1072
가로세로비  1.2714 (왼쪽 2/3 스냅, 16:9 가 아니다)
```

게임이 관리자 권한이라 일반 권한의 `SetWindowPos` 는 `err=5` 로 막힌다.
크기와 위치를 읽는 것은 막히지 않는다.

**Windows 배율을 바꾼 뒤에는 게임을 완전히 다시 시작해야 한다.** 게임은 시작할 때의
DPI 를 유지한다. 100% 로 바꾼 뒤에도 프로세스를 새로 띄우기 전에는 창 값이 예상과
맞지 않았다. 제목 표시줄 두께가 시작할 때의 DPI 로 고정되기 때문이다.

```text
시작 DPI   지금 화면   창 안쪽 (물리)            논리
96         125%        (1,31)  1705x1348         (0.8,24.8) 1364x1078
120        125%        (1,38)  1705x1341         (0.8,30.4) 1364x1072  기준
144        125%        (2,45)  1703x1333         (1.6,36)   1362x1066
```

이 정도 차이(8px 이내)는 같은 창으로 본다. 좌표와 이미지는 그대로 쓰고 검색 영역만
넓힌다 (`Docs\Macro-Format.md`). 넓히지 않으면 실제 로그의 찾은 위치 기준으로
`Check_DD_VeryHard_Selected` 가 영역 밖으로 4.1px, `Check_reward_done` 이 1.2px 나간다.

### 해상도 대응 실측 (2026-11-04)

게임 창을 1080p@100% 에서 예상되는 크기로 줄여, 게임이 직접 그린 화면을 쟀다.

```text
결과 화면 1278x1000   패치 5개   비례 계산과 오차 최대 0.7px
결과 화면 1279x1006   패치 5개   오차 최대 0.4px
전투 HUD  1278x1000   패치 13개  가로 0.3px 이내, 세로 최대 1.8px
UI 배율 실측 0.7475 = sqrt(가로 x 세로) 0.7476
```

| 템플릿 | 원본 | 소수 버림 | 반올림 |
|---|---|---|---|
| `Check_reward_done3`, 1278x1000 | 0.9917 | 0.9104 | 0.9653 |
| `Check_reward_done3`, 1279x1006 | 0.9917 | 0.9339 | 0.9745 |

위 측정에 쓴 템플릿은 2개뿐이다. 실제 모니터 결과는 아래 "실제 1080p 실행" 절에 있다.
OculiX 의 재시도 단계와 투명 템플릿 예외는 `Docs\Macro-Format.md` 의 해상도 대응 절.

## 생성한 파일

```text
D:\Programming\Oculix-Automation\
├─ CLAUDE.md                                        프로젝트 지침
├─ Scripts\
│  ├─ Common\pixel_util.py                          픽셀 색상 헬퍼
│  └─ Tests\
│     ├─ TestTarget.ps1                             전용 WinForms 테스트 대상 창
│     ├─ BasicTest.sikuli\BasicTest.py              런타임 smoke test
│     ├─ ApiProbe.sikuli\ApiProbe.py                API 존재 여부 및 timeout 검증
│     ├─ GuiAutomationTest.sikuli\GuiAutomationTest.py  기능 검증 스위트
│     ├─ CoordProbe.sikuli\CoordProbe.py            좌표계 진단
│     └─ InputProbe.sikuli\InputProbe.py            입력 차단 진단
├─ Assets\                                          (비어 있음)
├─ Logs\                                            실행 로그, 캡처 이미지
└─ Docs\
   ├─ Environment.md                                이 문서
   └─ env-backup-2026-08-15.txt                     환경변수 변경 전 백업
```

## 테스트 결과

`Test Script` : `Scripts\Tests\GuiAutomationTest.sikuli`
`Test Result` : **2026-08-16 재검증 결과 20개 전부 PASS** (`ALL_TESTS_PASSED`)

2026-08-15에는 입력 주입 7개가 차단되어 13개만 통과했다.
게임(Mabinogi Mobile)을 종료한 뒤 재실행하니 전부 통과했다. 아래는 최종 결과다.

```text
PASS A  delay wait(1.0)              1.00s
PASS E1 template capture             target.png 7,235 bytes
PASS E2 exists() full screen         score 0.9964, 좌표 오차 (0,0), 0.15s
PASS E3 match.highlight(1)
PASS F1 Pattern.similar()            0.99 / 0.70 모두 매칭
PASS F2 Region 제한 검색 (양성)
PASS F3 Region 검색 (음성+timeout)   None, 3.00s
PASS P1 Pixel RGB 읽기               (200,30,30) 정확
PASS P2 wait_pixel_color 적중
PASS P3 wait_pixel_color timeout     None, 2.03s (설정 2.0s)
PASS P4 channel별 tolerance 경계
PASS G1 vanish 대상 사전 매칭
PASS G2 waitVanish() (Region 제한)   True, 0.04s
PASS P5 픽셀 red -> green            (30,160,60), 0.01s
PASS G3 앱 상태 확인                 vanish_visible=False, status_rgb=30,160,60
PASS B  click()                      clicks 1 -> 2 (앱이 실제로 수신)
PASS C  mouseDown / mouseUp          downs 0->1, ups 0->1 (앱이 실제로 수신)
PASS D1 keyDown / keyUp              key_downs=[A], key_ups=[A]
PASS D2 type() 문자 입력             textbox='aOCULIX42' (앱이 실제로 수신)
PASS H  exists() 시간 상한           3.53s에 종료
```

판정 기준은 화면 모양이 아니라 **대상 앱이 실제로 수신한 이벤트**다.
대상 앱이 클릭/키 이벤트를 상태 파일에 기록하고 그것과 대조했다.

### 끝단 검증 — 매크로 엔진까지 포함한 전체 사슬

JSON 매크로 → 노드 그래프 실행기 → OculiX → 실제 입력까지 한 번에 확인했다.

```text
--> 버튼 클릭          CLICK on L[358,521]@S(0)
--> 초록으로 바뀔 때까지  colour matched: (30, 160, 60)
--> 입력란 클릭         CLICK on L[500,599]@S(0)
--> 문자 입력          TYPE "MACRO-E2E"
=== 노드 6회 실행, 실패 0 -> OK ===

대상 앱이 받은 것
  clicks     : 0 -> 1
  status_rgb : 200,30,30 -> 30,160,60
  textbox    : '' -> 'MACRO-E2E'
  exit code  : 0
```

### 회귀 검증 (2026-08-16 최종)

```text
selftest.py    49/49    데이터 모델·스키마
guitest.py     85/85    GUI 코드 경로 (트리·노드·라이브러리)
graphtest.py   33/33    OculiX로 그래프 실행 (호출 11개 포함)
Example        exit 0   트리 형식 하위 호환
CallDemo       exit 0   매크로 호출
GuiAutomationTest 20/20 실제 입력
E2E            OK       엔진 전체 사슬
```

### 해상도 대응 검증 (2026-11-04)

```text
selftest.py    114/114  변환 계산, 이미지 선택, 설정 검사 포함
guitest.py     624/625  실패 1건은 없어진 CallDemo 매크로를 찾는 기존 항목
scaletest.py   45/45    입력 없이 OculiX 로 변환, 축소본, DPI 경로 확인
graphtest.py   212/212  실제 입력. 전용 창이 있어야 도는 글자 인식 22건 포함
```

기준 환경의 실제 실행 (2026-11-04 13:02): 실행기부터 출석까지 노드 65회가 돌았고
과거 기록이 있는 템플릿의 점수와 위치는 과거 범위 안이었다. 스냅이 끝나면 변환이
꺼진다. 상점, 숙제, 던전 구간은 새 코드로 아직 돌지 않았다.

### 1080p 흉내 실행 (2026-11-04)

모니터를 바꾸지 않고 1080p@100% 와 같은 픽셀 조건을 만들어 실제 입력을 보냈다.

```text
게임 창 안쪽  물리 1278x1000 (관리자 권한 SetWindowPos)
JVM          -Dsun.java2d.uiScale=1.0   시스템 DPI 96, 캡처와 좌표가 물리 픽셀
RunMacro     --simulate-screen=1920,1080
```

게임에 입력을 보내기 전에, 이 JVM 조건의 클릭이 전용 창 버튼에 들어가는 것을
확인했다 (`clicks 0 -> 1`). 게임은 관리자 권한이라 입력도 같은 권한으로 보낸다.

| 매크로 | 결과 | 좌표 변환 예 |
|---|---|---|
| `MBM_Go_MyHouse` | 성공 | (347,336) -> (325,323) |
| `MBM_Out_MyHouse` | 성공 | (1276,131) -> (1196,132), (653,573) -> (612,545) |

| 템플릿 | 기준 | 1080p 흉내 |
|---|---|---|
| `MoveToPoint_Btn` | 1.0000 | 0.9852 |
| `Check_Is_In_House` 진짜 위치 | 0.9880 | 0.9871 |
| `Map_Check_in_HG` | 0.9874 | 0.9585 |
| `Check_CharInfo` | 0.9764 | 0.9566 |
| `out_myhouse_popup` | 0.9667 | 0.9650 |
| `Check_Loading_Done2` | 0.9590 | 0.9443 |
| `icon_exit_area` 33x33 | 0.9818 | 0.9077 (저장 화면으로 측정) |

찾은 위치는 비례 계산값과 3px 이내였다.

**드래그는 비례한다.** 같은 자리에서 세계 지도를 같은 좌표(변환 적용)로 끌어 두
해상도의 결과를 비교했다. 지도 위 패치 6개의 최종 위치가 가로 0.3px, 세로 5px
이내로 같았다.

휠, 상점·숙제·던전 화면은 아직 확인하지 않았다. 실행기 단계는 아래 실제 실행에서 확인했다.

`scaletest.py` 는 입력을 보내지 않으므로 게임을 켜 둔 채 돌려도 된다.
`graphtest.py` 는 실제 입력을 쓰므로 게임을 끄고 돌린다. 글자 인식 실측은
`Scripts\Tests\TestTarget.ps1` 과 `OcrTarget.ps1` 창이 떠 있을 때만 돌고,
없으면 건너뛴다. 건너뛰어도 전체는 통과로 끝나므로 결과의 건너뜀 수를 본다.

### 실제 1080p 실행 (2026-11-04 18:05)

주 모니터를 1920x1080 @100% 로 바꾸고 `MBM_Daily` 를 실행기부터 돌렸다. 이미지는
다시 찍지 않고 자동 축소만 썼다. 사용자가 `Daily_Attendance` 에서 일시정지할 때까지
3분 34초, 노드 63회, 클릭 9회, 키 입력 7회가 실패 없이 지나갔다.
스텔라픽, 상점, 숙제, 던전, 휠은 이 실행에서 닿지 않았다.

```text
화면 / DPI     1920x1080, 96
게임 창 안쪽   (1,31) 1278x1000, 가로세로비 1.2780, 배율 0.9370 / 0.9328 / 0.9349
좌표 변환      6곳 모두 계산값과 0.5px 이내
찾은 위치      기준 실행의 비례 계산값과 가로 0.6px, 세로 2.7px 이내 (5개 대조)
```

| 템플릿 | 공간 | 기준 중앙값 | 1080p | 비고 |
|---|---|---|---|---|
| `GameStartBtn` | window | 0.9081 | 0.9029 | 기준에서도 빠듯하다 (최저 0.9000) |
| `ESC_Menu` | window | 0.9764 | 0.9059 | 표본 1개. 기준 최저 0.9012 |
| `SelectCharBtn` | window | 0.9768 | 0.9172 | 기준 최저 0.9719. 손실 0.06 |
| `TaskBar_GameLogo` | screen | 0.9057 | 0.9383 | 아래 참조 |
| `Wait_Luncher_Open` | screen | 0.9899 | 0.9561 | 축소 없음 |
| `Check_CharInfo` | window | 0.9768 | 0.9567 | |
| `Map_Check_in_HG` | window | 0.9836 | 0.9585 | |
| `Check_Loading_Done2` | window | 0.9590 | 0.9598 | 기준 표본 1개 |
| `out_myhouse_popup` | window | 0.9736 | 0.9665 | |
| `MoveToPoint_Btn` | window | 1.0000 | 0.9852 | |
| `MBM_PlayBtn` | screen | 0.9827 | 0.9856 | 축소 없음 |
| `WebPopupCheck` | window | 0.9860 | 0.9903 | |

실행기 이미지는 Windows 배율이 달라도 재캡처 없이 통과했다.

`Check_Is_In_House` 는 0.9190, 0.9318 로 두 번 다 가짜 위치에서 끝났다. 기준에서도
있는 현상이고 사용자 결정으로 그대로 둔다.

`Check_Loading_Done` 은 못 잡혔지만 축소 때문이 아니다. 13:04 기준 실행의 같은
자리에서도 못 잡혔고 둘 다 `Check_Loading_Done2` 로 통과했다. 대신 이 이미지가
1080p 에서 잡힌 표본은 아직 없다. 기준 중앙값이 0.9608 인데 임계값 0.95 노드가
6개라 뒤쪽 구간에서 먼저 실패할 후보다.

**`TaskBar_GameLogo` 는 52초 뒤에 잡혔다.** 18:05:41 부터 찾았고 18:06:33 에 0.9383 으로
통과했다. 기준 실행은 즉시 통과했다. 15:42 점검은 게임이 타이틀 화면인데 0.8728 이었다.
같은 18:06:33 에 창 크기도 바뀌기 시작했으므로 게임 로딩 완료와 관련됐을 가능성이
높지만 확인하지 못했다. 아이콘의 활성 상태에 따라 점수가 달라지는 것으로 보인다
(기준 화면에서 게임이 비활성일 때 0.9915, 실행 중 0.9057). 제한시간은 300초다.

**창이 로딩 끝에 4초 동안 다른 크기를 거친다.**

```text
18:05:32  1278x1000            프로세스 시작 3초 뒤. 지난번 크기
18:06:33  Win+Z, 5, 1 입력
18:06:34  958x1000  x=약 957   오른쪽 절반
18:06:37  958x954
18:06:38  958x962 -> 1278x1000
```

시작 전에도 창이 1278x1000 이어서, 스냅 키가 옮긴 것인지 원래 자리로 돌아온 것인지는
구분하지 못했다. 다른 크기로 시작해야 구분된다.

이 사이에 `GameStartBtn` 찾기와 감시가 돌아 `.scaled\958x*` 에 쓸모없는 축소본 7개가
생겼다. 결과에는 영향이 없었고 지워도 되는 파일이라 코드는 고치지 않았다.

`GameStartBtn` 클릭에서 `checkMousePosition` 경고가 한 번 나왔다 (기대 (638,914), 실제
(641,919) 뒤 (665,955)). 다른 클릭 8번에는 없었고 다음 화면으로 넘어갔으므로 클릭은
들어갔다. 그 순간 마우스가 움직인 것으로 보이지만 확인하지 못했다.

### 창 노드 검증 (2026-11-09)

`focusWindow` / `moveWindow` 를 RunMacro 로 실제 창에 돌렸다. 주 모니터 하나, 2560x1440 @125%
(논리 2048x1152). 대상은 `TestTarget.ps1`(DPI 비인식 WinForms)과 시험용 tkinter 창(DPI 비인식 /
`SetProcessDpiAwareness(2)` 인식 두 종류). 판정은 별도 Python 프로세스의 `GetForegroundWindow` 와
`DwmGetWindowAttribute`(물리 좌표)로 대조했다.

```text
포커스: 다른 창이 앞     -> 포커스를 옮겼습니다      (독립 확인: foreground = 대상)
포커스: 이미 앞          -> 이미 포커스를 가진 창입니다
포커스: 최소화된 창      -> 복원 후 포커스          (독립 확인: 복원됨, foreground = 대상)
포커스: 없는 창 (1s)     -> 실패 핀으로 진행
이동 (100,120) 비인식 창 -> 물리 테두리 (125,150) = 논리 (100,120) x 1.25
이동 (0,0) 인식 창       -> 물리 테두리 (0,0). 보이지 않는 테두리 6~7px 를 빼고 옮김
이동 (5000,5000) / (-50,300) -> 어느 모니터에도 없어 옮기지 않음 (성공)
이동: 같은 자리          -> 이미 (100, 120) 에 있습니다
이동: 최대화 / 전체 화면 / 최소화 -> 상태를 로그로 남기고 옮기지 않음 (성공)
selftest 139/139, guitest 657/658 (실패 1건은 기존 CallDemo 항목)
```

확인하지 못한 것: 게임 창 자체(사용자 결정으로 건드리지 않음), 배율이 다른 보조 모니터로
옮기기(측정 당시 모니터 하나), 관리자 권한 창(거부 시 오류 5 로 실패 처리하도록만 작성),
`graphtest.py`(창 노드 사례 없음, 이번에 돌리지 않음).

### 2026-08-15 시점 기록 (아래는 이제 해소된 상태다)

당시에는 화면 읽기 13개만 통과하고 입력 주입 7개가 차단되어 있었다.
원인과 해소 경과는 "Known Issues" 1번 참조.

#### 당시 통과 — 화면 읽기 계열

| 항목 | 결과 | 근거 |
|---|---|---|
| A. Delay `wait(1.0)` | PASS | 실측 1.01s |
| E1. 템플릿 캡처 | PASS | target.png 7,236 bytes 생성 |
| E2. `exists()` 전체화면 | PASS | score **0.9964**, 좌표 오차 (0,0), 0.19s |
| E3. `match.highlight(1)` | PASS | 오버레이 정상 |
| F1. `Pattern.similar()` | PASS | 0.99 / 0.70 모두 매칭, strict score 0.9964 |
| F2. Region 제한 검색 (양성) | PASS | 창 영역 내 매칭 |
| F3. Region 검색 (음성+timeout) | PASS | None 반환, 3.01s에 정확히 종료 |
| P1. Pixel RGB 읽기 | PASS | (200,30,30) 정확히 일치 |
| P2. `wait_pixel_color` 적중 | PASS | 즉시 반환 |
| P3. `wait_pixel_color` timeout | PASS | None, 2.07s (설정 2.0s) |
| P4. channel별 tolerance 경계 | PASS | 경계 판정 정확 |
| G1. vanish 대상 사전 매칭 | PASS | 클릭 전 파란 패널 매칭 |
| H. `exists()` 시간 상한 | PASS | 3.50s에 종료, 무한 대기 없음 |

#### 당시 차단 — 입력 주입 계열 전부

`click`, `mouseDown/Up`, `keyDown/Up`, `type`, 그리고 이에 의존하는
`waitVanish`·픽셀 변화 테스트 7개. 2026-08-16 전부 해소됨.

## Known Issues

### 1. 안티치트 동작 중 합성 입력 차단 — 해소됨 (2026-08-16)

**2026-08-15 증상**

```text
java.awt.Robot.mouseMove  : 10회 시도 중 0회 반영
SetCursorPos(700,500)     : False 반환
SendInput                 : 1 반환(성공 주장)하나 포인터 미이동
포인터 유휴 시            : 10회 샘플 완전 동일 (외부 간섭 아님)
```

Java 고유 문제가 아니었다. Win32 경로도 동일하게 막혔다.
`BlackCipher64.aes`(nProtect GameGuard 계열, Mabinogi Mobile이 로드)가 원인.

**2026-08-16 게임 종료 후 재측정**

```text
SetCursorPos(700,500)     : True, 커서 실제 이동
java.awt.Robot.mouseMove  : 10/10 정확히 도달
GuiAutomationTest         : 20/20 ALL_TESTS_PASSED
```

주의할 점: **게임 프로세스만 종료하면 되고 `BlackCipher64.aes` 자체는 남아 있어도 된다.**
재측정 시점에 `BlackCipher64.aes`와 `NexonPlug` 6개가 여전히 실행 중이었으나
입력은 정상 동작했다. 차단은 프로세스 존재가 아니라 게임 활성 상태에 걸려 있었다.

프로젝트 지침의 "안전 범위"대로 안티치트 우회는 시도하지 않았다.
게임을 실행하지 않고 일반 애플리케이션에서 검증하는 것이 원래 테스트 정책이다.

### 2. ~~다중 모니터 좌표계 불일치~~ — 그런 문제는 없었다 (2026-08-16 정정)

2026-08-15에 "Java가 크기는 논리 좌표, 원점은 물리 좌표로 보고해
좌표계가 어긋난다"고 기록했으나 **이는 잘못된 진단이었다.**

당시 근거는 다음 오류였다.

```text
RobotDesktop: checkMousePosition: should be L[358,521]@S(0) - but is L[3270,1333]@S(2)!
```

실제로는 마우스가 **아예 움직이지 않고** 있던 자리(마침 Screen(2))에 머물렀을 뿐이다.
입력이 차단되어 생긴 증상을 좌표계 문제로 오인했다.

입력이 통하는 상태에서 재측정한 결과:

```text
requested ( 100, 100) -> actual ( 100, 100)  delta=(0,0)
requested ( 358, 521) -> actual ( 358, 521)  delta=(0,0)
requested (1000, 600) -> actual (1000, 600)  delta=(0,0)
requested (1500, 900) -> actual (1500, 900)  delta=(0,0)
worst_delta=0  COORD_OK
```

**Screen(0) 좌표는 정확하다.** JVM DPI 플래그도 불필요하다.

다만 다음 두 가지는 실재하므로 여전히 주의한다.

* Java가 보고하는 화면 **경계값**은 크기(논리)와 원점(물리)이 섞여 있다.
  Screen(0) 사용에는 영향이 없으나 다른 모니터를 쓸 때는 확인이 필요하다.
* **화면 인덱스 순서가 실행마다 바뀐다.** 두 번의 측정에서 Screen(1)과 Screen(2)가
  서로 바뀌었다. 주 모니터는 항상 Screen(0)이었다.
  인덱스를 하드코딩하지 말고 `Screen(0)`으로 한정하라.

### 3. 실행 중단 shortcut을 신뢰할 수 없음

구 SikuliX의 `Alt+Shift+C`는 2.0.0 이후 제거되었다.
CLI 실행 중 중단은 콘솔 `Ctrl+C` 또는 java 프로세스 종료에 의존한다.
따라서 **스크립트 자체에 timeout을 두는 것이 유일하게 신뢰할 수 있는 중단 수단**이다.
본 프로젝트의 모든 대기에 timeout을 강제하는 이유가 이것이다.

### 4. `oculixapi` JAR은 단독 실행 불가

`META-INF/MANIFEST.MF`에 `Main-Class`가 없다.
`java -jar oculixapi-4.0.0-windows.jar` → "no main manifest attribute"로 실패한다.
스크립트 실행에는 `oculixide-4.0.0-windows.jar`를 사용한다.

### 5. Windows 11 메모장은 자동화 대상으로 부적합

패키지 앱이라 `Start-Process notepad.exe`가 반환하는 PID가 스텁이고
`MainWindowHandle`이 0이다. 실제 창은 별도 프로세스가 소유한다.
또한 세션 복원으로 사용자의 미저장 문서가 함께 열려 있어 오입력 위험이 있다.
검증에는 전용 창(`Scripts\Tests\TestTarget.ps1`)을 사용했다.

### 6. 단색 템플릿은 `waitVanish`를 오판하게 만든다 (2026-08-16 발견)

사라짐 검증용으로 단색 파란 패널(170×120)을 템플릿으로 썼더니
패널이 실제로 사라진 뒤에도 `waitVanish()`가 계속 False를 반환했다.

진단 결과, 그 템플릿이 **화면 우측 상단의 다른 파란 영역과 score 0.986으로 매칭**되고 있었다.
PNG 크기가 379 bytes에 불과할 만큼 균일한 이미지라 변별력이 없었다.

```text
similar(0.99) -> no match
similar(0.95) -> MATCH score=0.9866 at (1749,41)   ← 대상이 아닌 곳
similar(0.90) -> MATCH score=0.9861 at (1761,41)
```

OculiX 버그가 아니라 템플릿 문제다. 두 가지로 고쳤고 둘 다 일반 원칙이다.

1. **검색을 대상 Region으로 제한한다.** 전체 화면 검색이 원인이었다.
   `region.waitVanish(...)`로 바꾸자 0.04초에 True를 반환했다.
2. **템플릿에 변별력 있는 내용을 넣는다.** 패널에 텍스트를 추가했다.

지침의 "이미지 캡처 원칙"이 말하는 그대로다 — 단색이나 특징 없는 영역은 템플릿으로 쓰지 않는다.

### 7. 화면보호기가 켜지면 자동화가 전부 실패한다 (2026-08-16 발견)

검증 도중 화면보호기가 동작하자 다음이 모두 깨졌다.

```text
화면 캡처            : 전 영역 (0,0,0) 검정
Robot.getPixelColor  : (0,0,0)
클릭                 : 대상 앱이 수신하지 못함
CopyFromScreen       : "The handle is invalid" 예외
SystemParametersInfo : SCREENSAVERRUNNING = 1
```

세션이 잠긴 것은 아니었다(`OpenInputDesktop` 성공). 화면보호기 창이 화면을 덮은 상태다.

`SendInput`으로 마우스를 흔들거나 `SC_MONITORPOWER`로 디스플레이를 깨우는 방법으로는
해제되지 않았다. **실제 키보드/마우스 입력이 필요하다.**

대응: 장시간 도는 매크로를 돌릴 때는 화면보호기와 디스플레이 절전을 꺼야 한다.
이는 시스템 설정 변경이므로 사용자가 판단할 사항이며, 임의로 변경하지 않았다.

### 8. 엔진에서 OculiX 전역 함수를 호출할 수 없다 (2026-08-16 발견·수정)

`macro_engine.py`에서 `click()`을 호출하니 실행 시점에 다음이 났다.

```text
NameError: global name 'click' is not defined
```

OculiX는 **클래스**(`Region`, `Pattern`, `Screen` 등)는 모듈 속성으로 노출하지만,
**전역 동작 함수**(`click`, `type`, `mouseDown`, `paste`, `wheel` …)는
실행 중인 `.sikuli` 스크립트 네임스페이스에만 주입한다.
import된 모듈에서는 보이지 않는다.

`Scripts\Tests\MethodProbe.sikuli`로 확인한 결과:

```text
sikuli.click, sikuli.type, sikuli.mouseDown ... 12개 전부 False
Screen.click, Screen.type, Screen.mouseDown ... 17개 전부 True
```

수정: 엔진의 모든 동작을 `Screen`/`Region` **인스턴스 메서드**로 바꿨다.
입력이 차단돼 있던 동안에는 이 경로가 실행되지 않아 드러나지 않았던 잠복 결함이다.

### 9. 좌표를 캐시해 두고 클릭하면 엉뚱한 창을 누른다 (2026-08-16 발견)

끝단 검증 중 매크로가 대상 창이 아니라 **Chrome 창을 클릭**했다.

원인: 대상 창이 이동했는데 좌표를 담은 상태 파일이 갱신되지 않아,
매크로가 낡은 좌표를 믿고 그 자리에 있던 다른 창을 눌렀다.

```text
상태 파일 rect.form : 208,231,800,560   (낡음)
실제 창 위치        : (1052,134)-(1868,733)
(358,401)에 있던 창 : Chrome_RenderWidgetHostHWND
```

일반화하면 **좌표 기반 클릭의 근본 위험**이다. 창은 언제든 움직인다.
지침이 "절대 좌표보다 이미지 기반 탐색을 우선한다"고 하는 이유가 이것이다.

대응으로 두 가지를 넣었다.

* `TestTarget.ps1`에 `LocationChanged` / `SizeChanged` 핸들러를 추가해
  창이 움직이면 좌표를 즉시 다시 쓰게 했다
* 검증 스크립트가 실행 전에 상태 파일 좌표와 실제 `GetWindowRect`를 대조하고,
  어긋나면 클릭하지 않고 중단하게 했다

실사용 매크로에서도 같은 원칙을 지킨다 — 좌표는 이미지로 찾은 결과에서 얻고,
고정 좌표를 쓴다면 대상 창이 그 자리에 있는지 먼저 확인한다.

### 10. 실행 중인 로그가 0바이트로 보인다 (2026-11-04 발견)

편집기는 로그를 줄마다 파일에 쓴다 (`runlog.py`, 매번 `flush`). 그런데 파일이 열려
있는 동안에는 디렉터리 정보가 갱신되지 않아 `Get-ChildItem` 과 탐색기에 0바이트로
나온다. `latest.log` 는 실행이 끝날 때 복사되므로 실행 중에는 지난 실행의 내용이다.

실행 중인 로그는 타임스탬프가 붙은 파일을 공유 모드로 직접 연다.

```powershell
$fs = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite,Delete')
```

일시정지 여부는 로그 끝의 `[일시정지]` 줄이나 `Logs\pause-<편집기PID>.flag` 로 안다.
Java 프로세스가 살아 있어도 멈춰 있을 수 있다.

### 11. 전역 단축키 등록이 "응답이 없습니다" 로 멈춘다 (2026-11-09 발견·수정)

창 노드를 추가한 뒤 `guitest.py` 의 "해제한 키는 다시 등록할 수 있다" 가 매번 실패하고
이어서 `hotkey.stop()` 이 `ctypes.ArgumentError` 로 죽었다. 원래 코드에 있던 문제가 GC 시점이
바뀌면서 드러난 것이다.

원인: 등록 스레드에서 GC 가 돌면 메인 스레드가 버린 tkinter `Variable` 의 `__del__` 이 그
스레드에서 불리고, 그 Tcl 호출은 메인 루프를 기다린다. 메인은 `_ready.wait(2.0)` 으로 그
스레드를 기다리는 중이라 2초 뒤 시간 초과가 난다. tkinter 변수를 순환 참조로 버린 뒤 새 스레드에서
`gc.collect()` 를 부르는 6줄짜리 스크립트로 같은 증상(2.01초, 같은 예외)을 재현했다.

수정 (`hotkey.py`): 스레드를 띄우기 전에 메인에서 `gc.collect()`, 시작할 때 `_thread_id`
초기화, `stop()` 은 스레드 id 를 모르면 잠시 기다리고 그래도 모르면 보내지 않는다.
실제 편집기에서는 속성 폼을 많이 만든 뒤 실행할 때 F6 등록 실패로 드물게 나타날 수 있었다.

## 글자 인식 (OCR) — 2026-08-21 실측

번들된 Tesseract 5.5.0 으로 화면의 글자를 읽어 찾는 기능을 검증했다.
`Tools\MacroEditor\graphtest.py` 의 25·26절이 이 결과를 회귀 검사로 지킨다.

### 한국어 데이터 설치 기록

```text
파일     : kor.traineddata
크기     : 15,317,715 bytes
SHA-256  : 9520bfe9e3cfc38d4a808e036b0287c88a1d37fb80b9a0a23928ddccdd20595b
출처     : https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/kor.traineddata
           (tesseract-ocr 공식 저장소)
설치 위치: C:\Users\CHJ-PC\AppData\Local\legerix\5.5.0\tessdata\
```

`OCR.availableLanguages()` 결과: `[chi_sim, eng, fra, hin, kor, spa]`
(`eng` 외 나머지는 OculiX 배포본에 함께 들어 있다.)

공식 checksum 이 제공되지 않는 파일이라 위 SHA-256 은 **받은 파일의 값**이지
공식 발표값과 대조한 것이 아니다. JAR 과 JDK 처럼 검증된 것이 아님을 구분해 둔다.

### 확정된 제약 세 가지

**1. 한 번에 한 언어만 된다.**

OculiX 는 Tesseract 의 `kor+eng` 다중 언어 표기를 거부한다. 설치된
`<언어>.traineddata` 파일 이름과 그대로 대조하기 때문이다.

```text
OCR.globalOptions().language("kor+eng")  -> SikuliXception: no kor+eng.traineddata
Settings.OcrLanguage = "kor+eng"          -> 같은 예외
```

게다가 **실패한 값이 남으면 이후 인식이 전부 죽는다.** `Settings` 와
`globalOptions` 두 곳을 함께 맞춰야 하고, 실패 시 되돌려야 한다
(엔진 `_set_language()` 가 이 처리를 한다).

언어가 어긋나면 결과가 조용히 망가진다.

```text
kor 로 영문 읽기 : "Open Settings" -> "0060 56 네 ㅁ 095"
eng 로 한글 읽기 : "설정 열기"      -> "a4 F7|"
kor 로 혼용 읽기 : "Hyper-V 관리자" -> "1/00-\/ 관 리 자"  (한글만 맞음)
```

→ 화면마다 `ocrLanguage` 로 전환한다. 한글·영문이 섞인 라벨은 **한글 부분만**
질의에 넣는다.

**2. 한글은 음절마다 쪼개져 나온다.**

```text
화면의 "설정 열기"  -> 읽힌 값 "설 정 열 기"
findWords() 결과    -> "설", "정", "열", "기"  (네 조각)
```

그래서 조각을 하나씩 검사하면 두 글자짜리 질의도 못 찾는다. OculiX 의
`existsText()` 도 마찬가지다.

```text
existsText("설정")        -> 못 찾음
existsText("설 정 열 기") -> 찾음     (OCR 의 공백까지 흉내내야 걸린다)
```

→ 엔진은 `existsText()` 를 쓰지 않는다. 조각을 모두 이어붙인 뒤 공백과
대소문자를 무시하고 부분 일치로 찾고, 걸친 조각들만 합쳐 사각형을 만든다
(`_match_span()`). 그래야 "설 정 열 기" 줄 전체가 아니라 "설정" 두 글자를
가리킨다. `findWords`/`findLines` 는 화면 절대 좌표를 준다
(`OCR.readWords(region)` 은 region 상대 좌표다 — 섞어 쓰면 엉뚱한 곳을 누른다).

**3. 페이지 분할 모드(psm) 기본값이 UI 화면에 맞지 않는다.**

한글 창에서 9가지 조합(라벨 딱 맞게 / 여백 30px / 창 전체)을 재봤다.

```text
psm=3  (기본, 자동)   정확 5/9   1.58s   ← 여백을 조금만 둬도 결과가 통째로 빈다
psm=4  (세로 글줄)    정확 9/9   1.02s
psm=11 (성긴 글자)    정확 9/9   0.99s
```

영문 창(8가지)에서는 3/4/11 이 모두 7/8 로 같았고 4·11 이 더 빨랐다.
→ **엔진 기본값을 psm 11 로 정했다.** 매크로 설정 `ocrPsm` 으로 바꿀 수 있다.

psm 3 에서 인식이 비면 Tesseract 가 `Empty page!!` 를 stdout 에 뱉는다.
로그에 이 줄이 보이면 psm 이나 영역 크기를 의심한다.

### 정확도와 속도

영역을 좁혔을 때, 언어를 맞췄을 때 기준이다.

```text
좁은 라벨 영역 읽기      0.07 ~ 0.09s
창 하나(560x340) 검색    0.15 ~ 0.16s
주 모니터 전체 검색       2.2s        ← 게다가 다른 창의 같은 글자를 짚었다
```

실제로 주 모니터 전체에서 "설정" 을 찾자 의도한 라벨(328,301)이 아니라
(346,155) 의 다른 글자를 짚었다. **영역 제한은 이미지 검색보다 더 중요하다.**

같은 화면인데도 `findWords()` 와 `findLines()` 는 실행마다 결과가 흔들린다.
한 번은 `확인` 을 단어 목록이 놓치고 줄 목록이 잡았고, 다음 실행에서는 반대였다.
그래서 엔진은 단어 → 줄 순으로 둘 다 시도하고, 위치가 필요 없는 판정
(`textExists` / `textMissing`)이면 마지막으로 영역 전체를 통짜로 읽어본다.

### 끝에서 끝까지 확인

`Scripts\Tests\OcrTarget.ps1` 은 한글 라벨 다섯 개를 띄우고 **어느 라벨이
눌렸는지 기록한다.** 매크로가 "확인" 을 찾아 클릭했을 때 로그가 아니라 그 창이
받은 값으로 판정했다.

```text
글자 "확인" 발견 (읽은 값 "확 인")  영역 (1273,364) 53x41  ->  클릭 지점 (1299,384)
창이 받은 값: lastClick=kr2, hits.kr2 1 증가
```

## 미확인 항목

```text
PaddleOCR 동작       : Unknown (IDE 상태 패널에 offline 표시. 이번 범위에서 검증하지 않음)
VNC remote screen    : Unknown (이번 범위 밖)
Mabinogi 종료 후 동작: Unknown (아직 시도하지 못함)
시작 메뉴 아이콘 클릭 : Unknown (OculiX 로 눌리지 않았다. 포커스가 옮겨가며
                       메뉴가 닫히는 것으로 의심되나 확인하지 못했다)
```

## 설치 이력과 주의사항 (2026-11-09 CLAUDE.md 에서 옮김)

설치 직후 `CLAUDE.md` 에 적어 두었던 내용이다. 매 세션 읽을 필요가 없어서 옮겼다.
버전·해시·경로는 위의 "Java", "OculiX" 절에 있다.

### 공식 출처 조회 결과 (2026-08-15)

* 구 저장소 `oculix-org/SikuliX1` 이 archive 되면서 개발·릴리스·문서·커뮤니티는 모두
  OculiX 로 옮겼다. 원저자 RaiMan 이 개발을 중단한 뒤 Julien Mer 가 동의를 받아 인수했다.
* 기존 SikuliX Jython 스크립트와 `.sikuli` bundle 은 drop-in 호환이라고 명시되어 있다.
* Windows 배포 파일: `oculixide-4.0.0-windows.jar` (약 130MB, IDE),
  `oculixapi-4.0.0-windows.jar` (약 69MB, API only). GitHub Release asset 의 `digest`
  필드로 SHA-256 을 확인할 수 있다.
* 공식 설치 문서 본문의 예시 명령은 3.0.3 기준으로 적혀 있었다. 버전 번호는 Releases 페이지를 기준으로 한다.
* 요구 사항: Windows 10 이상, x86-64, RAM 최소 1GB (권장 4GB).
* Windows 관련 공식 언급: 다중 모니터는 `Screen(n)` 으로 구분한다. 캡처 시점과 재생 시점의
  scaling 비율이 다르면 매칭이 실패할 수 있고, 이 경우 `Pattern("foo.png").similar(...)` 를
  낮추라고 안내한다. 이 프로젝트는 스케일링 고정을 먼저 적용하고 threshold 하향은 그 다음 수단으로 둔다.
* 공식 출처: <https://oculix.org/>, <https://docs.oculix.org/>,
  <https://github.com/oculix-org/Oculix>, <https://github.com/oculix-org/Oculix/releases>

### 초기 미해결 사항의 처리 (2026-08-15)

1. 처음에는 `oculixapi` 만 있고 IDE 가 없었다 → `oculixide-4.0.0-windows.jar` 를 추가로 받아 digest 대조.
2. `oculixapi` JAR 에는 `Main-Class` 가 없다 → 스크립트 실행에는 IDE JAR 을 쓴다 (Known Issues 4).
3. PC 에 Java 가 없었다 → Temurin JDK 21 을 zip 으로 설치 (위 "Java" 절).

### 환경 변수 수정 시 주의

* User `Path` 는 레지스트리 타입이 `REG_EXPAND_SZ`(ExpandString)이고 `%USERPROFILE%` 참조를 포함한다.
  `[Environment]::SetEnvironmentVariable(...,'User')` 를 쓰면 `REG_SZ` 로 바뀌어 기존
  `%USERPROFILE%` 항목이 깨진다. 반드시 다음 방식으로 수정한다.

  ```powershell
  Set-ItemProperty -Path 'HKCU:\Environment' -Name 'Path' -Type ExpandString -Value $new
  ```

* Path 항목은 `%JAVA_HOME%\bin` 이 아니라 절대 경로를 쓴다. 변수 전개 동작을 이 환경에서
  확실히 검증할 수단이 없었기 때문이다. JDK 버전을 올릴 때는 `JAVA_HOME` 과 `Path` **두 값을 모두** 고친다.
* Machine 스코프는 건드리지 않았다 (관리자 권한 없음). User 스코프만으로 이 사용자의 모든 프로세스에 적용된다.
* 변경 전 원본 환경 변수 백업: `Docs\env-backup-2026-08-15.txt`
* 기존 `%USERPROFILE%\.dotnet\tools` 항목은 실제 디렉터리가 없다. 이 작업 이전부터의 상태이며 건드리지 않았다.

### 압축 해제본

`D:\Apps\oculixapi-4.0.0-windows\` 는 설치 결과물이 아니라 JAR 을 그대로 푼 내용이다
(`org\`, `com\`, `META-INF\` 등). 실행에는 원본 `.jar` 을 쓰고, 해제본은 내부 구조 확인용으로만
참조한다. 삭제 여부는 사용자가 판단한다.
