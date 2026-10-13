# 진입 정책의 실행본·설정 대조

2026-09-29, `C:/Users/u/nasdaq-auto-trader` 및 기존 LocalAppData 자료를 읽었다. 이번 감사에서는 GUI·EXE·예약 작업·브로커를 실행하지 않았다. 배포 EXE는 PyInstaller의 읽기 전용 archive reader로 메모리에서 분석했으며 내장 모듈을 import하거나 실행하지 않았다. 개인 거래 원장은 복사하지 않고 실행 경로·시각·정책 근거만 정리했다.

## 핵심 판정

**일일 최소 매수는 과거 로그에만 남은 기능이 아니다.** 현재 소스와 현재 배포 EXE 모두 `daily_minimum_buy_enabled`를 사용하는 경로가 있고, 설치 GUI의 저장값도 `true`다. 다만 감사 시 실제 실행 중인 트레이더는 발견되지 않았으므로 “지금 주문을 실행 중”이라는 뜻은 아니다.

`daily_forced_order_enabled`는 다른 이름의 폐기된 정책이다. 현재 제품 Python 전체 검색에서 이 필드의 사용은 `config_settings.py:55` 선언뿐이다. 저장값이 true여도 해당 옛 경로가 작동한다는 증거가 아니다. README의 “no_trade이면 주문하지 않음”은 기본값에 관한 설명이며, README 첫 부분은 일일 최소 매수 예외를 명시한다. 이번 작업에서 제거된 옛 강제매수 경로를 복구할 이유가 없다.

## 네 가지 실행 상태

| 구분 | 경로·정책 | 확인 수준 |
|---|---|---|
| ① 문제 기록 당시 | LocalAppData GUI 로그의 직전 시작 메시지가 `dist/NasdaqAutoTrader/config.kis.json`을 가리킨다. 2026-09-23~25 매수 판단에 `daily_minimum_best_affordable`가 있고 다음 약 5분 평가에 일반 기술적 매도 기록이 있다 | 정책의 실제 사용은 로그 증거. 개별 주문 이벤트에는 EXE hash가 없으므로 특정 binary의 확정 식별은 불가 |
| ② 현재 로컬 소스 | `engine_automatic_cycle` → `daily_buy_due` → 선정/진입 적격성 → `engine_cycle.daily_minimum_decision`. 설정이 true이고 due이면 HOLD를 BUY로 바꾼다 | 소스 및 해당 함수의 배포 bytecode 대조. 기본 TradingSettings 값은 false |
| ③ 현재 배포 EXE·저장 GUI | `dist/NasdaqAutoTrader/NasdaqAutoTrader.exe`, 기본 launcher는 인접 `config.kis.json`과 `%LOCALAPPDATA%/NasdaqAutoTrader/trading_config.json`을 사용. 저장값 daily_minimum=true, live=true, dry_run=false | launcher·매핑·최소매수의 bytecode를 정적으로 확인. 이번에 EXE 실행하지 않음 |
| ④ 감사 시 실행 프로그램 | 대상 EXE 또는 프로젝트 경로를 실행하는 Python/wscript 프로세스 미발견. `NasdaqAutoTrader-Unattended`, `NasdaqAutoTrader-LiveCanary` 모두 Disabled | Windows 프로세스 및 작업 스케줄러 메타데이터 조회. 실행 파일·작업 시작/종료/수정 없음 |

소스용 `run_trader_gui.ps1`은 저장소로 이동해 `python -m nasdaq_auto_trader --config config.kis.json gui`를 실행하는 구조다. 명시적인 `--trading-config`가 없어 루트 `trading_config.json`을 사용한다. 이 파일은 dry_run=true, live=false이며 daily_minimum 필드가 없어 기본 false다. `app_ui.launch_gui()`는 자동선정을 켜지만 daily_minimum을 켜지는 않는다. 따라서 **같은 소스여도 어느 설정 파일로 실행했는지가 중요하다.** 명시적 CLI 인수를 주면 기본 launcher 경로와 달라질 수 있고, 현재 실행 중인 argv는 없었다.

## 최근 세 기록의 시각과 배포 귀속

아래는 거래 원장이 아니라 실행본을 연결하기 위한 제출 이벤트 시각이다. 체결 시각·실제 보유시간으로 쓰지 않는다. 날짜 없는 trader.log는 감사 JSONL의 제출 이벤트 순서와 연결된다. 원장 수량·가격·주문번호는 재출력하지 않았다.

| 기록 날짜 | 제출 시각 UTC / KST | 근거 행 | 배포 귀속 |
|---|---|---|---|
| 2026-09-23 | 매수 13:38:56.959743 / 22:38:56.959743; 매도 13:43:59.725853 / 22:43:59.725853 | trader.log 187934/188043, audit.jsonl 26176/26183. 직전 GUI 구성 경로 메시지 trader.log 187667 | 현 EXE 파일의 작성 시각보다 앞선다. 기존 배포 기록의 F198…4E97 실행본과 부합하나 이벤트 hash는 없음 |
| 2026-09-24 | 매수 13:37:43.722216 / 22:37:43.722216; 매도 13:42:33.144615 / 22:42:33.144615 | trader.log 188418/188527, audit.jsonl 26303/26309. 직전 구성 메시지 188155 | 9/23 23:02 KST 재실행 기록 및 B344…7CEA 배포본과 부합. 직접 event-to-binary hash 연결은 없음 |
| 2026-09-25 | 매수 13:35:07.438343 / 22:35:07.438343; 매도 13:40:08.748522 / 22:40:08.748522 | trader.log 197032/197141, audit.jsonl 26722/26729. 직전 구성 메시지 188155 | 위와 같은 시작 구간. 동일한 한계 |

`trader.log`와 `audit.jsonl`의 절대 경로는 각각 `C:/Users/u/AppData/Local/NasdaqAutoTrader/logs/trader.log`, `C:/Users/u/AppData/Local/NasdaqAutoTrader/ai_quant_lab/audit.jsonl`이다. 시작 메시지 187667의 `[07:45:27]`, 188155의 `[23:02:25]`는 날짜를 포함하지 않는다. 단독으로 날짜를 단정하지 않고 아래 별도 배포 증거와 대조했다.

- `.omo/evidence/order-reconciliation-20260923/incident-report.md`의 기존 배포 hash: `F198A89817BFF1EE9F4154E6BBC056F219EEE4385E3EF5F5744E270E19F84E97`. 같은 폴더 runtime-verification.json은 설정 보존, 5분, daily_minimum=true를 기록한다. 파일 수정 시각은 2026-09-22 22:46:45 UTC다. 옛 바이너리 원본 전체를 다시 검증한 것은 아니다.
- `.omo/evidence/order-reconciliation-rebuild-20260923/report.md:3`은 2026-09-23 23:02 KST 재빌드·재실행을 기록한다. `:11`의 hash가 현재 EXE와 같다. runtime-verification.json의 process_path는 현재 dist EXE이며, settings_unchanged=true, interval_minutes=5, daily_minimum_enabled=true, source_changes_this_turn=0이다. 그 파일의 수정 시각은 2026-09-23 14:02:55 UTC다.
- 현재 EXE의 파일 수정 시각은 **2026-09-23 13:58:26.737499 UTC**다. 따라서 9/23 13:38~13:43 UTC 주문을 현재 파일 hash로 확정 귀속하는 것은 잘못이다.
- 감사 이벤트의 `strategy_version=data-b230423351524f87-catalogue-v5`는 학습 전략 버전이다. EXE, 설정 또는 당시 봉 데이터의 버전이 아니다.

정리하면 “과거 구버전에서만 강제진입했고 현재는 제거되었다”는 가설은 틀리다. 세 이벤트의 정확한 EXE hash는 미기록이지만, **현재 EXE에도 같은 최소매수 실행 분기가 남아 있다.**

## 실제 호출 경로와 충돌 지점

줄 번호는 이번 감사 시점 소스다.

1. `nasdaq_auto_trader/config_settings.py:54`의 기본 `daily_minimum_buy_enabled=False`. 설치 GUI JSON이 true로 덮어쓴다.
2. `engine_automatic_cycle.py:61`은 설정이 true인 비-dry_run 경로에서 당일 주문 이력을 조회한다. `:71`이 `daily_buy_due()`를 호출한다. 이력 미확인·미완결이면 due=false로 막는다.
3. `daily_buy_objective.py:32`의 `daily_buy_due()`는 미국 거래일 기준 확인 체결량이 1주 미만일 때 due를 허용한다. dry_run은 별도 모의 카운터 분기다(`:45`). 단순 제출 카운트를 실체결로 읽는 함수는 아니다.
4. `automatic_entry_eligibility.py:60`의 `EntryEligibilityContext.evaluate()`는 실제 TechnicalStrategy를 호출한 뒤 `:78`에서 daily_minimum_decision을 적용한다. due일 때 일반 기술적 HOLD도 매수 적격 후보가 될 수 있다. `:69`의 위험 한도도 5%로 바꾼다.
5. `automatic_selection.py:117`~`:121`은 학습 쪽 위험 한도까지 5%로 바꾼다. `quant_data/symbol_selector.py:116`~`:117`은 일반 rank/select 대신 후보 점수순 첫 종목을 고른다. 따라서 단순히 마지막 주문 단계만 확인해서는 부족하다.
6. `engine_automatic_cycle.py:160`은 due일 때 첫 선정 종목을 `daily_minimum_symbol`로 넘긴다. `engine_cycle.py:108`에서 같은 변환을 다시 적용한다.
7. `daily_buy_objective.py:96`은 due=true, 미보유, HOLD, 충분한 봉, 유효 가격·위험거리이면 `:117`에서 BUY를 반환한다. 매수 점수 미달 또는 일반 매도 점수 충족 여부를 추가로 거부하지 않는다. `engine_cycle.py:149`~`:152`는 주문 위험 계산도 5%로 바꾼다.
8. `strategy.py:53`~`:67`은 같은 데이터의 두 점수를 계산하지만 미보유면 매수 기준만 보고, 보유면 매도 기준을 본다. 두 점수가 동시에 기준을 넘을 수 있다.
9. `automatic_order_context.py:36`~`:44`는 날짜형 일봉 timestamp 뒤에 5분 실행 슬롯을 붙인다. 기존 주문 중복 방지는 같은 주문 문맥을 막지만, 다음 실행 슬롯을 새로운 완성봉으로 보증하지 않는다. 일반 진입/청산 신호의 반복 평가 문제와 주문 전송 중복은 별개의 경계다.

최소 2종목 보유·현금 소진을 위한 강제 진입/강제 교체 경로는 현재 일반 엔진 검색에서 발견하지 못했다. 이 결론은 검사한 일반 엔진과 위 호출 경로 범위다. HIVE 전용 매도 모니터 및 독립 AI quant 엔진을 일반 GUI 경로에 섞지 않았다.

이번 A/B/C 비교에서 위험 한도를 모두 동일하게 고정한다면, A는 **강제 진입 효과만 재현하는 제한된 오프라인 기준선**이다. 실제 최소매수 정책에는 5% 위험 덮어쓰기와 학습 후보 선택 우회도 있어, 그것까지 빠짐없이 재현하지 않은 결과를 당시 운영 전체와 동일하다고 부르면 안 된다.

## 저장 손절 3%의 적용과 역사적 한계

| 항목 | 저장값 / 최종값 | 출처·덮어쓰기 |
|---|---|---|
| 고정 손절 | 인접 기본 JSON 0.07 → GUI 3.0% → 최종 0.03 | `dist/NasdaqAutoTrader/config.kis.json` → LocalAppData trading_config → `config_runtime.apply_settings_to_app_config():38`의 `/100` |
| 고정 익절 | 기본 JSON 0.18 → GUI 5.0% → 0.05 | 같은 함수 `:39` |
| ATR 손절 | ATR14 × 3 | 기본 JSON 유지. GUI의 3% 변경이 ATR을 끄지 않음 |
| 최소 매수 | 기본 false → 설치 GUI true | 별도 필드. 소스 루트 trading_config는 이 필드가 없어 false |
| 실행 모드 | 기본 JSON dry_run → 설치 GUI live=true/dry_run=false → live | 같은 함수 `:19`~`:27`. 이는 저장 설정이며 현재 프로세스 실행 증거는 아님 |
| 평가 주기 / 지표 봉 | 5분 / 1Day | GUI unattended_interval_minutes / 인접 config.timeframe |

이번에는 EXE 내부 `config_runtime` 전체 code-object와 현재 소스를 대조했고, `stop_loss_rate / 100` 연산도 disassembly로 확인했다. EXE 내부 `app_controller`, `app_ui` 및 launcher 기본 인수도 대조했다. 따라서 **현재 배포 EXE의 기본 GUI 실행 경로에는 현재 저장된 3%가 적용되는 구조**라는 근거는 이전 보고서보다 강해졌다.

다만 당시 주문마다 최종 설정 snapshot/hash가 저장되지 않았다. 현재 GUI 파일의 수정 시각은 2026-09-21 22:53:58 UTC이고, 기존 두 배포 확인 자료도 settings_unchanged=true이므로 같은 3%였다는 해석과 부합한다. 파일 수정 시각과 사후 기록만으로 과거 모든 메모리 설정을 증명할 수는 없다. 세 주문의 조기매도 이유가 일반 기술적 신호였다는 사실과, 해당 시점 손절값의 완전한 역사적 증명은 구분한다.

README.md:9는 기본 no_trade와 `daily_minimum_buy_enabled=true` 예외를 같이 설명한다. README.md:863의 제거 대상은 `daily_forced`다. 문구 일부만 읽으면 모순처럼 보이지만 **현 README·소스·현재 배포본 사이에는 이 두 이름에 관해 일관된 구분**이 있다. 설치 설정이 예외를 활성화하고 있다는 점이 기본 설명과의 차이다.

## 파일 식별과 정적 대조 방법

감사 당시 브랜치는 `main`, 기존 추적 파일 변경은 76개였으며 미추적 파일도 있다. 이를 이번 작업 변경으로 오인하거나 초기화하지 않았다. 저장소 및 상위 사용자 폴더의 AGENTS.md는 발견되지 않았다.

| 파일 | SHA-256 |
|---|---|
| `dist/NasdaqAutoTrader/NasdaqAutoTrader.exe` | `b34486f790bc45d0f6e73189999f197760c77da482c20dd1a14b94d768617cea` |
| `dist/NasdaqAutoTrader/config.kis.json` | `74b5ad66c031a43473b09a8084e714278ee48eb6cac12c06e16253afaef0ed5c` |
| `C:/Users/u/AppData/Local/NasdaqAutoTrader/trading_config.json` | `a852d2ed357a368cb3e5b526adf11ce3448b61297ab4b4c80c7769c9c783c8bf` |
| 루트 `trading_config.json` | `313e4bc503aba2a84a3173fa521b974b0e9456978a50da9b94d7f3b8576e7358` |
| `nasdaq_auto_trader/daily_buy_objective.py` | `2b1bb8779dd96ef49314403b04cf54c749d9e019c136cc583c6c0af25ee1256a` |
| `nasdaq_auto_trader/engine_automatic_cycle.py` | `87fa17df58c5e16ae8b6e31d4abc0a33a9b80f89f453fbadb5edf75c1065b4ca` |
| `nasdaq_auto_trader/engine_cycle.py` | `74ea8a41bb17da76c5f0089e5a50bc3f4192d6c91569bd1b6e63bdfccbc9f7d6` |
| `nasdaq_auto_trader/config_runtime.py` | `a9f5a5a5e94687c926e7b0f5de1177a45be63560bf1a3aded3b7d29707444c09` |
| `nasdaq_auto_trader/gui_launcher.py` | `4f070277e75dda8bca5a4c2e5a683796c4f39b1fcd2654a451cde8a988d52643` |
| `README.md` | `4f0268a6b2620dfa9f2611573599a8cc52656f6dcb2682bff940505110d6e19e` |

EXE size는 15,980,146 bytes다. 사용한 Python 설치에 이미 PyInstaller가 있어 새 도구를 설치하지 않았다. `CArchiveReader(path).open_embedded_archive("PYZ.pyz")`로 명시한 정책 모듈만 읽었다. `gui_launcher`는 CArchive의 해당 항목을 `marshal.loads()`로 code-object로 읽었다. Python `compile()`은 현재 소스를 code-object로 만들기만 하고 실행하지 않는다.

전체 모듈 비교는 파일명·줄 번호·line table을 제외하고 opcode, 상수, 인수/이름/클로저 정보, exception table을 재귀 비교했다. 이 비교가 일치한 것은 `engine_automatic_cycle`, `config_runtime`, `config_settings`, `automatic_selection`, `quant_data.symbol_selector`, `app_controller`, `app_ui`다. 세부 함수 `daily_buy_due`, `daily_minimum_decision`, `EntryEligibilityContext.evaluate`, launcher `_app_dir`/`_default_argv`는 opcode·비-code 상수·이름·인수·exception table을 따로 비교해 일치했다. 내장 코드 실행 또는 전체 애플리케이션의 동등성 증명은 아니다.

`engine_cycle` 및 `strategy`는 이전 조기매도 작업으로 수정되었으므로 현재 EXE와 전체 code-object가 다르다. 따라서 **이전 소스 오류 수정도 배포 EXE에 자동 반영되지 않았다.** 이번 진입 실험 역시 배포에 자동 반영되는 변경이 아니다.

## 실행한 읽기 전용 확인과 미검증

- Git Bash: `rg --files --hidden -g AGENTS.md`, `rg -n`으로 위 호출과 README, `nl -ba`로 실제 함수·줄 확인, `git branch --show-current`, `git status --short --untracked-files=no`.
- Python 표준 라이브러리: 파일 SHA-256·size·UTC 수정 시각, JSON 허용 필드만 추출, 로그의 구성 경로 메시지 및 지정 감사 이벤트의 timestamp/schema만 추출. 계좌·자격증명 필드나 원 응답을 출력하지 않았다.
- Windows PowerShell: `Get-CimInstance Win32_Process`로 대상 프로세스의 PID/경로/생성 시각만 조회. `Get-ScheduledTask`, `Get-ScheduledTaskInfo`로 두 작업의 Disabled 상태 및 action 경로 확인. 마지막 실행 메타데이터는 2026-09-09 21:10:10 KST, result=0이다. 이것을 현재 운영 정상 확인으로 쓰지 않는다.
- PyInstaller reader 및 `dis`: 현재 EXE의 활성 최소매수 변환, 호출 이름, GUI 기본 인수, 퍼센트 매핑을 정적으로 대조했다. 디스크에 전체 내장 파일이나 자격증명 파일을 추출하지 않았다.

이 감사 하위 작업은 기능 테스트나 실제 체결 조회를 실행하지 않았으므로 테스트 통과나 실제 체결 보유시간을 주장하지 않는다. 통합 담당의 네트워크 격리 회귀·실제 자료 비교와 별도로 해석해야 한다. 현재 소스·설정·EXE를 바꾸지 않았으며, 작성한 결과물은 이 문서뿐이다.
