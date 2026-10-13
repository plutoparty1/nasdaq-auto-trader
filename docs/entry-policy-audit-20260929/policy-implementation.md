# 진입 정책 교정 구현과 재현

2026-09-29. 운영 코드·실거래 설정·배포 EXE는 수정하지 않았다. 이 문서는 새로운 오프라인 정책과 합성 회귀 증거를 기록한다. 실제 시장 성과는 별도 비교 결과에서만 판단한다.

## 현재 소스에서 확인한 경로

- `nasdaq_auto_trader/engine_automatic_cycle.py:_execute_automatic_symbol_cycle()`가 `daily_buy_due()`의 결과를 종목 선정의 `EntryEligibilityContext.daily_minimum_due`와 최종 `daily_minimum_symbol`에 전달한다.
- `automatic_entry_eligibility.py:EntryEligibilityContext.evaluate()`와 `engine_cycle.py:_run_rule_decision_cycle()`가 `daily_minimum_decision()`으로 일반 `hold`를 `buy`로 승격한다. 점수가 부족해도 유효한 가격·충분한 지표 이력·위험거리가 있으면 승격할 수 있다. 해당 최초 매수 경로는 거래당 위험률을 5%로 바꾼다.
- 현재 README 첫 정책 설명은 기본 `no_trade`와 별도 opt-in `daily_minimum_buy_enabled`를 구분한다. 이전의 `daily_forced_order_enabled`는 별도 폐기된 플래그다. 실험을 위해 폐기된 기능을 운영 코드에 복구하지 않았다.
- `tests/test_entry_policy_engine.py:test_current_engine_low_score_minimum_then_next_cycle_technical_sell()`는 실제 `TradingEngine.run_once()`와 실제 선정·설정·위험 검사 경로를 사용한다. 시장자료와 보유분만 메모리 자료로 제공하고 `submit_order`/`cancel_order`는 호출 즉시 실패하는 브로커로 대체한다. 실제 체결을 위장하지 않고 첫 dry-run 판단 후 다음 평가의 보유 상태를 명시적으로 주입한다.
- 이 테스트에서 매수 점수 0인 진입이 발생했고 위험거리는 일반 1% 예산보다 컸다. 5분 후 동일 지표 자료를 가진 보유 상태에서는 일반 기술적 매도가 발생했다. 고정 손절 3%와 원래 위험 설정 1%는 유지됐다. 이 증거는 현재 소스에서 해당 경로가 실행 가능함을 입증하며, 과거 EXE 내부와의 동일성을 입증하지는 않는다.

## 정책과 안전 경계

`experiments/entry_policy/profile.json`은 `dry_run: true`, `broker: offline_csv`인 별도 프로필이다. `EntryPolicyStrategy`는 기존 `TechnicalStrategy`를 감싸며 운영 엔진·GUI가 선택하지 않는다.

| 정책 | 일반 진입 | 강제 진입 | 동일 완성 봉 재평가 |
|---|---|---|---|
| A | 기존 기술적 조건 | 미국 거래일에 1주 체결 전까지 유효 `hold` 승격 | 기존대로 가능 |
| B | A와 같은 기술적 조건 | 비활성화 | 기존대로 가능 |
| C | B와 같으며 동시 매도 점수가 기준 이상이면 진입 거부 | 비활성화 | 일반 매수·매도는 더 늦은 완성 봉에서만 새 신호로 사용 |

A는 **같은 위험한도의 오프라인 부분 재현**이다. 역사적 실행본 전체가 아니다. 실제 원래 경로의 최초 5% 위험 예외를 A에만 적용하면 진입 정책 외 요인이 바뀌므로 A/B/C 모두 일반 1%를 사용한다. 종목당·총 투자 50%, 현금 여유 5%, 1주, 최대 수량 1주, 추가 매수 금지, 자동 매수액 $35 상한, 일일 손실 신규 진입 중지 2%도 동일하다. 수수료·수량·비중은 비교 러너에서 공유한다.

고정 손절 3%, 고정 익절 5%, 2% 상승 후 최고가 대비 1% 트레일링, ATR(14) 손절 3배/익절 5배, `corrected_exits=False`를 모두 동일하게 보존한다. 과거 8%·10%·진입 ATR 후보는 별도 파일에 그대로 있다. 이번 비교에는 최소 보유시간이나 손실 시 매도 금지 규칙을 넣지 않았다.

오프라인 A의 `_minimum_proxy()`는 현재 `daily_minimum_decision()`의 승격 조건과 같은 계산이다. 직접 import하면 자동 주문 타입·시장 달력 모듈로 이어져 엄격한 오프라인 CLI의 소켓 차단에 걸리는 외부 라이브러리 초기화를 일으켰다. 운영 코드를 재배치하지 않고 작은 순수 계산을 별도로 두었으며, 실제 원본 함수와 동일 출력인지를 4가지 조건에서 비교한다. A는 학습 점수에 의한 역사적 최고 후보 순위, 당시 호가·API 상태, 승인 상태를 재현하지 않는다.

주문 생성 승인 시 같은 평가 시각의 다른 강제 주문만 예약한다. 이것은 체결로 계산하지 않는다. 다음 평가에서 미체결·만료라면 A의 최소 매수 목적은 계속 미충족이다. 실제 모의 체결 콜백만 미국 거래일별 체결 수량을 증가시키며, 추가·부분 체결 통지에서 이미 반영한 잔량을 이중 집계하지 않는다. 현금·위험 거절과 대기 주문은 기존 수정 `Backtester`가 처리한다.

## 완성 봉과 보호 시세

`evaluate(symbol, bars, position, evaluation_timestamp=..., completed_bar_id=...)`는 평가 시각과 완성 봉 식별자를 분리한다. 지표 봉의 식별자는 시차가 명시된 실제 완성 시각이어야 한다. 날짜만 있는 봉은 명시적 완성 식별자 없이 신규 일반 신호로 사용하지 않는다. 미래 봉도 일반 신호를 내지 않는다. 현재 실거래 KIS 일봉 응답이 언제 완성됐는지 자동 추론하는 운영 연결을 추가한 것은 아니다.

C는 같은 봉, 그 봉의 수정본, 이전 봉으로 돌아간 응답에서 재진입하지 않는다. 해제 조건은 **직전 평가보다 늦은 완성 봉**이다. 시계상 몇 분 대기는 해제 조건이 아니다. 같은 봉에서 위험 검사로 주문이 거절돼도 해당 일반 신호를 재발급하지 않는 보수적 실험 규칙이다.

보호 판단은 일반 신호 제한보다 먼저 실행한다. 따라서 매수 직후 같은 일봉을 보고 있어도 현재 유효한 보유 평가 가격이 3% 손절을 통과하면 보호 매도가 나온다. 미래·미완성 봉은 ATR 입력에서 제거한다. 완성 봉이 하나도 없어도 유효한 현재 보유 가격이 있으면 고정 손절·익절·트레일링 판단을 유지하고, ATR을 계산한 것처럼 만들지 않는다. 가격의 신선도·출처는 호출자가 제공하는 관측자료의 계약이며 과거 실제 호가로 복원했다고 주장하지 않는다.

각 판단은 평가 시각, 완성 봉 시각, 전체 입력 SHA-256, 같은 입력의 매수·매도 점수, 원래/최종 동작, 강제 승격 여부, `no_trade`, 중복 일반 평가 여부, 보호 판단 여부, 지표 가격과 보유 평가 가격을 기록한다. `initial_stop_for()`는 백테스터 인터페이스상의 이름이며 기존 `max(고정 위험거리, ATR 위험거리)`를 유지한 **수량 산정용 보수적 가격**을 반환한다. 실제로 먼저 발동하는 독립 고정/ATR 청산선과 같다고 표시하지 않는다.

## 회귀와 직접 실행 증거

처음 기존 `TechnicalStrategy`를 그대로 상속한 얇은 틀에서 새 회귀를 실행했을 때 11 실패·4 통과였다. 실제 동시 점수 사례에서 `buy`가 발생했고, 봉 중복 제한·체결 장부 API가 없었다. 이후 미래 ATR을 잘못 사용하던 별도 경계 테스트도 1 실패·1 통과로 확인하고 완성 이력 필터로 교정했다. 실패를 삭제하거나 기대값을 낮추지 않았다.

다음은 한 번의 명령으로 실행한 새 핵심 회귀다. 재실행 수를 합산한 숫자가 아니다.

```text
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_entry_policy_strategy.py tests/test_entry_policy_engine.py tests/test_entry_policy_fills.py
31 passed in 3.39s

uvx --offline ruff check nasdaq_auto_trader/entry_policy_experiment*.py tests/test_entry_policy_strategy.py tests/test_entry_policy_engine.py tests/test_entry_policy_fills.py
All checks passed!

python -m py_compile nasdaq_auto_trader/entry_policy_experiment.py nasdaq_auto_trader/entry_policy_experiment_models.py
exit 0

uvx --offline basedpyright nasdaq_auto_trader/entry_policy_experiment.py nasdaq_auto_trader/entry_policy_experiment_models.py
0 errors, 3 warnings, 0 notes

python C:/Users/u/.codex/plugins/cache/sisyphuslabs/omo/4.16.3/skills/programming/scripts/python/check-no-excuse-rules.py nasdaq_auto_trader/entry_policy_experiment.py nasdaq_auto_trader/entry_policy_experiment_models.py
no violations in 2 file(s)
```

타입 경고 3개는 상속 메서드의 명시적 override 표기 2개와 완전한 분기 마지막 `assert_never` 패턴 1개다. LSP 설치나 프로젝트 전반의 타입 경고 정리는 하지 않았다.

검증 항목은 낮은 점수+당일 매수 0건, 폐기 플래그로 우회 불가, 보유 0/1종목에서 최소 보유 강제 진입 없음, 동시 점수 충돌, 같은/수정/과거 봉 재진입 차단, 새 봉에서 해제, 새 유효 가격의 하드 손절, 미래 ATR 차단, 수량 지정 미체결이 보유/손익으로 집계되지 않음, 부분 체결 중복 집계 방지, 실제 승격 함수와의 출력 일치, 모든 후보의 같은 위험거리다.

직접 라이브러리를 구동한 [policy-replay.json](policy-replay.json)은 생성된 하락 자료에서 A `buy(score=0)` → 5분 후 `sell(score=9)`, B/C `hold` → `hold`를 기록한다. 중간 보유는 명시적으로 모의 체결로 주입한 것이다. 이 파일은 실제 주문 원장이나 수익성 결과가 아니다.

오프라인 모듈을 빈 패키지 경로에서 소켓·자식 프로세스 audit 거부 후 import한 결과는 broker 0, engine 0, configuration 0이었다. 운영 경로 회귀에서는 계좌와 보유 상태를 메모리로 주고 실제 주문/취소 메서드는 호출 즉시 실패하도록 했다. 비교 CLI와 조회 수집기의 추가 격리는 해당 담당 검증 결과와 함께 확인한다.

## 적용과 되돌리기

이 프로필을 운영 GUI JSON이나 `.env`에 복사하지 않는다. 운영 정책은 이미 그대로이므로 실거래 복귀 조작은 필요 없다. 오프라인 비교를 중단하려면 새 진입 실험 CLI를 실행하지 않으면 된다. 향후 운영 적용을 검토할 때는 완성 일봉 식별, 신선한 보호 가격, 재시작 시 신호 장부, 실제 계좌 비용·체결 이력, 승인·중복 주문 검증과 함께 별도 검토해야 한다. 이번 작업은 운영 적용 승인이 아니며 EXE를 교체하지 않는다.
