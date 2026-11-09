# 코드 구조

새 세션이 코드를 처음부터 다시 읽지 않도록 **어느 코드가 어디에 있는지**를 적은 지도다.
매크로 JSON 형식과 각 노드의 의미는 `Docs\Macro-Format.md`, 환경과 실측 기록은
`Docs\Environment.md` 에 있다. 이 문서는 그 내용을 되풀이하지 않는다.

* 위치는 줄 번호가 아니라 **파일·클래스·함수 이름**으로 적는다. 줄 번호는 금방 틀린다.
* 파일 책임, 실행 흐름, 노드 추가 절차가 바뀌면 같은 작업 안에서 이 문서도 고친다.
* 기준 시점: 2026-11-09, `feature/resolution-scaling` 의 `2ea96b9`.
  작성 당시 다른 세션이 `focusWindow` / `moveWindow` 노드와 `window_util.py` 를
  추가하는 중이었다. 그 작업이 합쳐지면 아래 표에 반영한다.

---

## 1. 한눈에 보기

```text
 ┌──────────────── 편집기 (CPython 3 + tkinter) ────────────────┐
 │ macro_editor.MacroEditorApp                                  │
 │   ├ node_canvas.NodeCanvas   그래프 편집                     │
 │   ├ 속성 패널                schema 표를 읽어 폼을 자동 생성 │
 │   └ runner.Job              java 프로세스 실행 / stdout 수신 │
 └──────┬──────────────────────────────────────────▲────────────┘
        │ 저장                                     │ stdout 줄 (로그)
        ▼                                          │
   Macros\<이름>\macro.json + *.png                │   Logs\pause-<pid>.flag  (일시정지)
        │                                          │   Logs\resume.json       (이어서 실행)
        ▼                                          │
 ┌──────────────── 실행 (Jython 2.7, OculiX JVM 안) ────────────┐
 │ Scripts\Runner\RunMacro.sikuli\RunMacro.py   인자 해석       │
 │   └ macro_engine.make_engine() → GraphEngine.run()           │
 │        ├ graph_model   검증, 핀, 참조 해석, 좌표 변환 계산   │
 │        ├ scale_runtime 창 측정, 템플릿 축소본 (해상도 대응)  │
 │        ├ pixel_util    픽셀 색                               │
 │        └ OculiX Screen / Region / Pattern                    │
 └──────────────────────────────────────────────────────────────┘
```

* **`graph_model.py` 는 양쪽이 함께 import 한다.** 그래서 Python 2.7 / 3 양쪽에서 도는
  문법만 쓴다 (f-string 금지, `except X as e`). 핀 정의, 검증, 참조 해석, 좌표 변환처럼
  편집기와 엔진이 같은 답을 내야 하는 것은 전부 여기 둔다.
* 편집기와 엔진은 **별도 프로세스**다. 둘을 잇는 것은 macro.json, stdout 줄,
  `Logs\` 아래 파일 두 개뿐이다.
* OculiX API 를 부르는 것은 엔진(`macro_engine`, `scale_runtime`, `pixel_util`)뿐이다.
  편집기의 화면 집기·캡처는 tkinter / GDI 로 직접 하거나 `Scripts\Tests\` 의
  보조 `.sikuli` 를 별도 프로세스로 돌린다 (`runner.capture_region`, `read_pixel_via_oculix`).

---

## 2. 파일 지도

### Scripts\Common — 엔진 (Jython). `graph_model` 만 Python 3 에서도 import 된다

| 파일 | 책임 |
|---|---|
| `macro_engine.py` | 실행기 전체. `Engine`(트리 실행 + 모든 말단 동작), `GraphEngine`(그래프 흐름, 호출, 반복, 예산, 재개), `WatchManager`(감시 매크로), `PauseGate`(일시정지), `make_engine()` |
| `graph_model.py` | 형식 정의와 검증. 매개변수, 핀, `Graph` 클래스와 `validate()`, 매크로 참조 해석, 감시 선언 검사, 해상도 변환 `Transform`, 이미지 위치 규칙, 트리→그래프 변환 |
| `scale_runtime.py` | 해상도 대응 중 JVM 안에서만 되는 일. 게임 창 측정, DPI, 템플릿 축소본 생성. 싱글턴 `SCALE`. `settings.scaling` 이 없으면 아무 코드도 돌지 않는다 |
| `pixel_util.py` | AWT Robot 으로 픽셀 읽기, 채널별 tolerance 비교, 색 대기 |
| `window_util.py` | `focusWindow` / `moveWindow` 의 Win32 작업 (JNA). 창 찾기(제목·클래스·프로세스), 상태 판정(보통/최소화/최대화/전체 화면), 포커스, 보이는 테두리 기준 이동. 창 노드를 만났을 때만 import 된다 |

### Scripts\Runner

| 파일 | 책임 |
|---|---|
| `RunMacro.sikuli\RunMacro.py` | 범용 실행기. `--from=`, `--resume`, `--pause-file=`, `--simulate-client=`, `--simulate-screen=` 를 해석하고 `make_engine()` → `run()`. 종료 코드 0 성공 / 1 실패 / 2 정의 오류 |

### Tools\MacroEditor — 편집기 (Python 3 + tkinter, 외부 패키지 없음)

| 파일 | 책임 |
|---|---|
| `macro_editor.py` | `MacroEditorApp`: 메뉴, 도킹 패널, 라이브러리·하위 매크로 관리, 속성 패널, 설정·감시 대화상자, 실행·일시정지·로그. `ConditionEditor`: 조건 편집 위젯 |
| `node_canvas.py` | `NodeCanvas`: 노드 그리기, 선택, 연결, 이동, 복사/붙여넣기, 우클릭 메뉴 |
| `schema.py` | 노드·조건의 **편집기용 정의표** (`STEP_TYPES`, `CONDITION_TYPES`, `COMMON_FIELDS`). 폼 생성과 노드 요약 글(`summarize`)이 이 표를 쓴다 |
| `model.py` | `Macro`: 파일 로드/저장, 트리 형식 경로 조작, 이미지 누락·위험 검사. tkinter 비의존 |
| `runner.py` | java 실행 (`Job`), 일시정지 신호 파일, `resume.json` 읽기, 영역 캡처·픽셀 읽기 보조 실행 |
| `nodeclip.py` | 노드 복사 꾸러미: id 재발급, 이미지 따라 복사, 이름 충돌 처리 |
| `docking.py` | 4영역 패널 도킹. 레이아웃이 바뀌면 패널을 **다시 짓는다** (`save_state`/`restore_state`) |
| `project_panel.py` | Macros 폴더 트리와 이미지 미리보기 |
| `imagepicker.py` / `keypicker.py` / `pickers.py` | 이미지 고르기 / 키 조합 고르기 / 화면에서 좌표·색·영역 집기 오버레이 |
| `imagecache.py` | PNG 썸네일 캐시 (`zoom`/`subsample` 조합) |
| `pnginfo.py` | PNG 의 투명 픽셀·DPI 검사 (OculiX 마스크 크기 버그 예방) |
| `screenutil.py` | 논리 ↔ 물리 좌표 변환, GDI 픽셀 읽기, 지점의 창 정보(`window_at`: 제목·클래스·안쪽 사각형·프로세스) |
| `runlog.py` | `Logs\Runs\` 실행 로그 파일 (최근 60개) |
| `hotkey.py` | 실행 중에만 등록하는 전역 단축키 (F6 일시정지). 등록 스레드를 띄우기 전에 메인에서 `gc.collect()` 한다 (11절) |
| `notify.py` | Windows 토스트 알림 (PowerShell `-EncodedCommand`) |
| `settings.py` / `theme.py` | `layout.json` 개인 설정 / 다크 테마 |
| `selftest.py` `guitest.py` `graphtest.py` `scaletest.py` | 테스트. 9절 참조 |

### Scripts\Tests — 검증용 `.sikuli` 와 테스트 대상 창

* `TestTarget.ps1`, `OcrTarget.ps1`: 클릭·키 입력을 상태 파일에 기록하는 전용 창. 입력 검증의 기준이다.
* `GuiAutomationTest.sikuli`: OculiX 기본 기능 20항목 (엔진을 거치지 않음).
* `CaptureRegion.sikuli`, `ReadPixel.sikuli`: 편집기가 실제로 부르는 보조 스크립트.
* 나머지 `*Probe.sikuli`, `*Survey.sikuli`: 일회성 진단. 결과는 `Docs\Environment.md` 에 있다.

---

## 3. 실행 한 번의 흐름

```text
편집기 F5
  MacroEditorApp.run_macro()
    → runner.run_macro(path, start_node, resume)
        java -jar oculixide.jar -r RunMacro.sikuli -c -- <macro.json> [--from=] [--resume] --pause-file=Logs\pause-<pid>.flag
RunMacro.main()
  → resume 이면 load_resume() 로 Logs\resume.json 확인 (같은 매크로인지 대조)
  → macro_engine.make_engine(macro, base_dir, start_node, resume_path, macro_path)
       1. _adopt_parent_context  하위 매크로면 부모 settings 와 부모 폴더(base_dir)로 바꿈
       2. validate_scaling → SCALE.configure(settings.scaling)
       3. params 미지정이면 _standalone_params (선언 기본값)
       4. 그래프면 GraphEngine, 트리면 Engine
       5. 하위 매크로 단독 실행이면 부모 감시를 inherited_handlers 로 넘김
  → engine.run()
       GraphEngine.run
         1. self.graph.validate()  오류면 실행 안 함
         2. 루트면 _start_watch() (전역 감시) + 예산 시작 (deadline)
         3. resume 경로가 있으면 그 머리 노드에서 시작
         4. _run_chain(start, 0, resume)
         5. 실패 → _save_resume() / 성공 → _clear_resume()
편집기
  stdout 줄을 실행 로그 패널 + Logs\Runs\*.log 에 기록
  [일시정지] / [재개] 표식(graph_model.PAUSED_MARK)을 보고 버튼 상태를 바꿈
  종료 코드로 성공·실패 알림, resume.json 유무로 [이어서 실행] 버튼 갱신
```

---

## 4. 엔진 — `macro_engine.py`

### 클래스와 전역 상태

| 이름 | 역할 |
|---|---|
| `Engine` | 트리 형식 실행기이자 **모든 말단 동작의 구현**. `_dispatch()` 가 노드 종류별 분기. 조건 평가 `evaluate()`, 대상 찾기 `_target()`, OCR, settle |
| `GraphEngine(Engine)` | 그래프 흐름. `_run_chain`, `_run_call`, `_run_loop`, `_run_foreach`, 예산 `_spend`, 실패 `_on_failure`, 재개 프레임 |
| `WatchManager` / `_Handler` | 감시 매크로 목록(호출 단계마다 한 겹 `scopes`)과 확인 `tick()`. 루트 엔진 하나가 소유 |
| `PAUSE` (`PauseGate`) | 일시정지 신호 파일 확인. **프로세스 전역** |
| `SCALE` (`scale_runtime.ScaleState`) | 해상도 대응 상태. **프로세스 전역**, 실행 하나에 기준 하나 |
| OCR 언어 / psm | OculiX 전역 설정이라 감시 매크로가 바꾸면 `_reapply_ocr()` 로 되돌린다 |

### 노드 하나가 처리되는 순서 (`GraphEngine._run_chain`)

```text
_consume_resume      재개 경로의 머리면 안쪽 경로를 꺼냄
_pause_point         일시정지 요청이 있으면 노드 실행 전 여기서 멈춤
_spend               루트 예산 차감 (maxSteps / maxSeconds, 멈춘 시간 제외) → 초과 시 BudgetExceeded
_watch_node_start    progress += 1, 감시 tick
enabled == False     skip_pin(type) 으로 건너뜀
break                → BREAK 반환
if                   evaluate(condition) → true / false 핀
repeat               _run_loop (times / while / forEach) → completed 핀
call                 _run_call → next 핀
그 외                 _attempt → Engine._dispatch → next 핀
실패                  _on_failure: ① fail 핀 연결 → ② onFail=continue → ③ 중단(_note_failure)
```

* 반환 상태: `NORMAL`, `BREAK`, `ABORT`, `END_OF_CHAIN`(이어갈 노드 없이 정상 종료).
* 예외의 의미:
  * `MacroError` — 정의 오류. 단계 실패로 삼키지 않고 위로 올라간다.
  * `BudgetExceeded`, `WatchStuck` — 실행 전체 중단. 호출된 엔진은 다시 던지고 루트가 처리한다.
  * 그 밖의 예외(`Exception`, Java `Throwable`) — `_attempt` 가 잡아서 **그 단계의 실패**로 만든다.
* 말단 노드는 `_dispatch` 에서 `True`(성공) / `False`(실패)를 돌려준다.

### 대기와 끼어들기

* 기다리는 동작은 모두 `_watched(timeout, attempt)` 를 거친다. `_sliced()` 가 참이면
  (`PAUSE`/`SCALE`/감시 중 하나라도 켜짐) `WATCH_SLICE`(0.5초) 단위로 잘라 기다리고,
  조각 사이에 `_wait_tick()` 으로 일시정지·감시를 처리한다. 처리에 쓴 시간은 제한시간에 더한다.
* 끼어들 것이 없는 명령줄 실행은 예전처럼 한 번에 기다린다.
* 감시는 **별도 스레드가 아니다.** `WatchManager.tick()` 은 노드 시작 전과 대기 조각 사이에만
  돈다. 마우스 버튼이 눌린 동안(`held`)과 감시 처리 중(`busy`)에는 돌지 않는다.

### 대상 찾기 (`Engine._target`)

`image` → `text`(OCR) → `point` → (허용된 노드만) 현재 커서 위치 순서로 첫 번째로 지정된 것을 쓴다.

* 이미지: `_find` → `_pattern`(similarity, targetOffset, 해상도 변환, DPI 보정) → `_settled`(settleFor).
* 글자: `_find_text` → `_scan_text` → `_match_span`(한글 음절 조각을 이어 붙여 찾음) → `TextHit`.
* 좌표: `_map_point`(해상도 대응이면 `Transform.point`).
* 검색 영역: `_make_region` (노드 region → settings.searchRegion → 화면 전체).

### 호출 (`GraphEngine._run_call`)

```text
resolve_macro_ref → 하위 매크로 소유 검사(family_root, 파일 위치 기준)
→ 순환(call_stack) / 깊이(MAX_CALL_DEPTH=16) 검사 → JSON 읽기
→ 하위 매크로면 settings 를 호출한 쪽 것으로, base_dir 를 부모 폴더로
→ resolve_args({"$param"} 를 현재 값으로) → bind_params(선언과 대조)
→ 호출된 매크로에 handlers 가 있으면 watch.push
→ root.frames 에 call 프레임 → 새 GraphEngine(root=루트, call_stack=공유).run()
→ finally: 프레임·호출 사슬·감시 겹 제거
```

* **예산은 루트 하나를 호출 사슬 전체가 공유**한다 (`self.root`).
* 감시 매크로 실행은 자기 `call_stack=[자기 경로]` 로 시작한다. 메인이 지나는 매크로를 감시가 불러도 순환이 아니다.

### 재개 (이어서 실행)

* `root.frames` 에 반복(`enter="loop"`, `done`)과 호출(`enter="call"`) 프레임이 쌓인다.
* 실패하면 `_note_failure` 가 **가장 안쪽** 위치 하나를 `failed_at` 에 남기고, 루트가 `Logs\resume.json` 에 쓴다.
* `--resume` 실행은 그 경로를 `_consume_resume` 으로 한 칸씩 따라 내려가 실패한 노드부터 다시 돈다.
* 실패 핀이나 onFail=continue 로 넘어가면 `_forget_failure` 가 기록을 지운다.

---

## 5. `graph_model.py` 구역 지도

| 구역 | 주요 이름 |
|---|---|
| 매개변수 | `PARAM_TYPES`, `declared_params`, `coerce_param`, `validate_params`, `bind_params`, `resolve_args`, `PARAM_REF`(`{"$param": 이름}`) |
| forEach | `foreach_spec`, `loop_params`, `validate_foreach`, `foreach_values` |
| 조건 | `CONDITION_TYPES`, `_all_conditions`, `compare_params` |
| 핀 | `EXEC_PINS`, `DEFAULT_PINS`, `FAIL_PIN`, `NO_FAIL_PIN`, `SKIP_PINS`, `LOOP_TYPES`, `exec_pins()`, `skip_pin()` |
| 상한 | `DEFAULT_MAX_STEPS`, `DEFAULT_MAX_SECONDS`, `MAX_CALL_DEPTH` (엔진의 `HARD_ITERATION_CAP` 은 `macro_engine`) |
| 그래프 | `Graph` (노드·링크 조작, `reachable`, `find_cycles`, `unbounded_cycles`, `validate`) |
| 매크로 참조 | `find_macros_root`, `family_root`, `is_sub_macro`, `list_sub_macros`, `resolve_macro_ref`, `list_macros`, `find_call_cycle` |
| 감시 | `watch_condition`, `handler_refs`, `handler_interval`, `validate_handler_decl`, `validate_watch`, `check_handler_refs`, `HANDLER_REPEAT_LIMIT`, `PAUSED_MARK` |
| 해상도 대응 | `SPACE_*`, `SAME_RECT_SLACK`, `REGION_PAD`, `Transform`, `scaling_of`, `validate_scaling`, `locate_image`, `capture_folders`, `scaled_image_path` |
| 노드 파라미터 검사 | `validate_node_params` (트리·그래프 공통, 오류와 경고 `cautions`) |
| 생성 / 변환 | `blank`, `from_tree` |

`Graph.validate()` 가 실행 전 검사의 입구다. 엔진(`GraphEngine.run`)과 편집기(`validate_macro`) 가 같은 함수를 쓴다.

---

## 6. 편집기 — `macro_editor.py`

### `MacroEditorApp` 구역 (파일 안의 `# ----` 머리줄 순서)

| 구역 | 대표 메서드 |
|---|---|
| 레이아웃·패널 | `_build_menu`, `_build_toolbar`, `_build_body`, `_panel_*`, `_save_*_state` / `_restore_*_state` |
| 매크로 라이브러리 | `refresh_library`, `insert_call_node`, 끌어다 놓기, `rename_macro`(호출 참조 갱신 `_rewrite_call_refs`), `duplicate_macro`, `delete_macro` |
| 하위 매크로 | `refresh_submacros`, `new_submacro`, `rename_submacro`, `delete_submacro` |
| 프로젝트 패널 연동 | `open_macro_path`, `assign_image_to_selected`, `find_image_users`, `rename_image_references`, `check_call_targets`, `check_handler_targets` |
| 모드 | `apply_mode`(트리/그래프 전환), `on_node_selected`, `convert_to_graph` |
| 트리·단계 편집 | `refresh_tree`, `add_step`, `delete_step`, `move_step` (트리 형식 전용) |
| 속성 패널 | `build_properties` → `schema.fields_for(type)` 를 돌며 `build_field`; `condition` 은 `ConditionEditor`, `target` 은 image/point/offset 묶음 |
| 피커·해상도 | `_pick_point`, `_pick_region`, `_capture_image`, `_stored_point`/`_stored_region`(현재 화면 값을 기준 좌표로 되돌림), `_pick_screen_point`(변환 없이 저장), `_pick_window`(창 조건 세 칸 채움) |
| 파일 | `new_macro`, `open_macro`, `save_macro`, `save_macro_as` |
| 도구 | `edit_settings`, `edit_watch`, `_build_param_editor`, `validate_macro` |
| 실행 | `run_macro`, `run_from_selected_node`, `resume_macro`, `toggle_pause`, `_drain_log`, `_on_run_done`, `_notify_run_done` |

### 필드 타입과 위젯

`schema` 의 필드 `type` 은 `build_field` 의 분기로 위젯이 된다.

* 입력: `bool`, `choice`, `keycombo`, `macro_ref`, `param_name`, `foreach`, `call_args`, `text`, 그 밖(`str`/`int`/`float` 등 한 줄 입력)
* 집기 버튼 (`_add_field_buttons`): `image`, `point`, `points`, `rgb`, `region`,
  `screenpoint`(해상도 변환·화면 밖 경고 없이 찍은 그대로), `window`(창을 눌러 `title`/`windowClass`/`process` 채움)
* 글자 ↔ 값 변환: `_value_to_text`, `_text_to_value` (`int`, `float`, `points`, `tolerance` …)
* 특수: `condition` → `ConditionEditor`, `target` → `build_properties` 안에서 image/point/targetOffset 으로 펼침
* `space` 필드는 `field_visible()` 이 해상도 대응 매크로에서만 보여 준다.

### 캔버스 — `node_canvas.NodeCanvas`

* 노드 색은 `schema.STEP_TYPES[type]["group"]` → `GROUP_COLORS`. 없는 그룹이면 `DEFAULT_COLOR`.
* 노드 아래 요약 줄은 `schema.summarize()` 의 `—` 뒤 부분 (`_detail`).
* 핀 목록은 `graph_model.exec_pins(type)`. 썸네일은 `schema.image_params()` 로 이미지 필드를 찾는다.
* 노드 추가: `add_node(stype)` → `schema.new_step(stype)` + `Graph.add_node`.

---

## 7. 새 노드 종류 추가 체크리스트

말단 노드(흐름을 바꾸지 않는 동작)를 추가할 때 고칠 곳이다.

1. **`schema.STEP_TYPES`** 에 항목 추가 — `label`, `group`, `fields`.
   새 그룹이면 `node_canvas.GROUP_COLORS` 에도 색을 넣는다.
2. **`schema.summarize`** — 노드 요약 줄이 필요하면 분기 추가.
   이미지 필드 이름이 `image` 가 아니면 `schema.image_params` / `rewrite_images` 도 본다
   (썸네일, 이미지 이름 변경, 복사/붙여넣기가 이것을 쓴다).
3. **`macro_engine.Engine._dispatch`** — 실행 분기 추가. 성공 `True` / 실패 `False`.
   정의가 잘못됐으면 `MacroError`. 기다리는 동작이면 `_watched()` 를 거친다.
   한글 서식 문자열은 `u"..."`. 전역 함수(`click()` 등) 대신 `self.screen` / `Region` 메서드.
4. **`graph_model.validate_node_params`** — 필수 필드 검사 (오류) / 주의할 점 (cautions).
5. 핀이 `next` + `fail` 이 아니면 `graph_model.EXEC_PINS`, `SKIP_PINS`, `NO_FAIL_PIN`.
6. 새 필드 `type` 이 필요하면 `MacroEditorApp.build_field`(와 필요하면 `_add_field_buttons`, `_text_to_value`).
7. 좌표를 갖는 노드면 해상도 대응: 엔진은 `_map_point`/`_make_region`, 편집기는 `_stored_point`/`_stored_region`.
   게임 창과 무관한 화면 좌표(예: `moveWindow.point`)는 변환하지 않는다 — 필드 타입을 `screenpoint` 로 둔다.
8. **테스트** — `selftest.py` 의 `engine_steps` 목록에 이름 추가 (스키마와 대조한다).
   `guitest.py` 는 `STEP_TYPES` 전체의 폼 생성을 자동으로 돈다. 실행 확인은 `graphtest.py` 에 사례 추가.
9. **문서** — `Docs\Macro-Format.md` 의 "단계 종류" 절.

**흐름 노드**(`if`/`repeat`/`call`/`break` 같은 것)는 `_dispatch` 가 아니라
`GraphEngine._run_chain` 에서 가로채야 하고, 재개 프레임(`root.frames`)과
`_on_failure` 처리를 함께 맞춰야 한다. 트리 형식 지원 여부(`Engine._dispatch`, `model.CONTAINER_KEYS`)도 정한다.

### 새 조건 종류

`graph_model.CONDITION_TYPES` + `Engine.evaluate` + `schema.CONDITION_TYPES` + `schema.describe_condition`.
감시 조건으로 쓸 수 있는 화면 조건이면 `macro_engine._SCREEN_CONDITIONS` 에도 넣는다
(감시는 기다리지 않고 한 번만 본다 — `_instant`).
`selftest.py` / `guitest.py` 가 두 `CONDITION_TYPES` 가 같은지 대조한다.

---

## 8. 편집기 ↔ 엔진 사이의 약속

어느 한쪽만 바꾸면 깨지는 것들이다.

| 약속 | 엔진 쪽 | 편집기 쪽 |
|---|---|---|
| 실행 인자 | `RunMacro.main` | `runner.run_macro` |
| 일시정지 신호 | `PauseGate` (`--pause-file`) | `runner.Job.pause` / `unpause`, `PAUSE_FILE` |
| 일시정지 로그 표식 | `graph_model.PAUSED_MARK` / `RESUMED_MARK` 를 찍음 | 같은 상수로 줄을 읽음 (`_note_pause_line`) |
| 재개 파일 | `macro_engine.RESUME_FILE` 쓰기·지우기 | `runner.RESUME_FILE` 읽기 (`read_resume`) |
| 노드 id 로그 | `_log_entry` 가 `(n12)` 를 붙임 | 캔버스 머리줄의 id 와 대조 |
| 노드·조건 목록 | `_dispatch`, `evaluate`, `graph_model.CONDITION_TYPES` | `schema.STEP_TYPES`, `CONDITION_TYPES` |
| 좌표 변환 | `graph_model.Transform` (공유) | 같은 클래스 |
| 창 노드 좌표계 | `window_util` 이 창을 다룰 때만 스레드를 DPI 비인식 문맥으로 바꿈 | 편집기가 DPI 비인식 프로세스라 [찍기] 값이 같은 좌표계 |
| 프로세스 이름 | `window_util.window_process` | `screenutil.window_process` — 둘 다 실행 파일 이름(`QueryFullProcessImageName` 의 마지막 조각) |

---

## 9. 테스트

모두 `python Tools\MacroEditor\<파일>` 로 돌린다 (작업 폴더 무관). 결과는 `PASS`/`FAIL` 줄과 끝의 합계.

| 파일 | 대상 | 필요한 것 | 입력을 보내나 |
|---|---|---|---|
| `selftest.py` | 스키마·데이터 모델·검증 규칙·변환 계산 (GUI 없음) | 없음 | 아니오 |
| `guitest.py` | 편집기 코드 경로. 위젯 생성 함수를 직접 부름 (창은 띄우지 않음) | tkinter. `Macros\Example` 을 읽는다 | 아니오 |
| `scaletest.py` | 해상도 대응. RunMacro 를 `--simulate-*` 로 실제 실행 | Java + OculiX | **아니오** (게임 켜 둬도 됨) |
| `graphtest.py` | 그래프 실행 전체를 실제 OculiX 로 | Java + OculiX, 화면보호기 꺼짐 | **예** — 게임을 끄고 돌린다 |
| `Scripts\Tests\GuiAutomationTest.sikuli` | OculiX 기본 기능 20항목 | `TestTarget.ps1` 창 | 예 |

* `graphtest.py` 의 글자 인식 실측은 `Scripts\Tests\TestTarget.ps1` / `OcrTarget.ps1` 창이 떠 있을 때만
  돌고, 없으면 **건너뛴 채 통과**로 끝난다. 결과의 건너뜀 수를 확인한다.
* 무엇을 고쳤을 때 무엇을 돌리는지:

| 고친 곳 | 돌릴 것 |
|---|---|
| `graph_model.py` | `selftest` → `guitest` → `graphtest` |
| `macro_engine.py`, `RunMacro.py` | `graphtest` (해상도 관련이면 `scaletest` 도) |
| `scale_runtime.py`, `Transform` | `selftest` → `scaletest` |
| `schema.py`, `model.py` | `selftest` → `guitest` |
| 편집기 UI 파일 | `guitest` |

최근 결과 기록은 `Docs\Environment.md` 의 "테스트 결과" 절.

---

## 10. 하드코딩된 경로

프로젝트나 런타임을 옮기면 고칠 곳이다.

| 값 | 위치 |
|---|---|
| 프로젝트 루트 `D:\Programming\Oculix-Automation` | `runner.PROJECT`, `macro_editor.PROJECT`, `RunMacro.py` 의 `sys.path.append` |
| JDK `D:\Apps\jdk-21.0.12+8\bin\java.exe` | `runner.JAVA`, `graphtest.JAVA`, `scaletest.JAVA` |
| OculiX IDE JAR `D:\Apps\oculixide-4.0.0-windows.jar` | `runner.IDE_JAR`, `graphtest.JAR`, `scaletest.JAR` |
| 재개 파일 `Logs\resume.json` | `macro_engine.RESUME_FILE`, `runner.RESUME_FILE` |

---

## 11. 자주 밟는 함정

규칙 자체는 `CLAUDE.md` 에 있다. 코드에서 마주치는 위치만 적는다.

* Jython 에서 한글 서식은 `u"..."` — `macro_engine` 전체, `RunMacro.say`.
* 엔진은 OculiX 전역 함수를 못 부른다 — `macro_engine` 머리 주석, `Environment.md` Known Issues 8.
* Java 예외는 `Exception` 으로 안 잡힌다 — `except (Exception, Throwable)`.
* Python 3 `round()` 는 2.7 과 다르다 — `graph_model._rounded` 를 쓴다.
* tkinter 는 위젯 부모를 못 바꾼다 — 도킹이 패널을 다시 짓는다. 콜백 안에서 패널을 다시 지으면
  호출 중인 위젯이 사라지므로 `after_idle` 로 미룬다 (`_repeat_mode_condition`).
* `.bak-*` 파일이 소스 옆에 많다 (git 제외). 검색 결과에 섞이므로 무시한다.
* Jython 에서 Java `char[]` 는 `jarray.zeros(n, Character.TYPE)` 로 만든다. 타입 코드 `"c"` 는
  JNA 인자로 넘어가지 않는다 (`GetWindowText(): 2nd arg can't be coerced to char[]`) — `window_util`.
* JVM 은 DPI 인식, 편집기는 DPI 비인식이라 Win32 창 좌표가 다르다. 창 노드는
  `SetThreadDpiAwarenessContext` 로 맞추고, 문맥과 무관하게 물리값을 주는 `DwmGetWindowAttribute`
  만 따로 환산한다 — `window_util` 머리 주석.
* tkinter 객체를 버린 뒤 **다른 스레드에서 GC 가 돌면** `Variable.__del__` 이 메인 루프를 기다린다.
  메인이 그 스레드를 기다리는 중이면 둘 다 멈춘다. 그래서 `hotkey.start()` 가 스레드를 띄우기 전에
  메인에서 `gc.collect()` 한다. 증상은 속성 폼을 많이 만든 뒤 F6 등록이 "응답이 없습니다".
* `TestTarget.ps1` 을 `Start-Process -WindowStyle Hidden` 으로 띄우면 **폼도 숨는다**
  (`IsWindowVisible` 0, 사각형은 있음). 콘솔만 숨기려면 `-WindowStyle Hidden` 을 powershell 인자로 넘긴다.
