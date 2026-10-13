# Generic CSV backtester execution audit

Scope: `nasdaq_auto_trader/backtest.py`; no broker construction, live state, account configuration or learning-engine edits.

## Hypotheses before changes

1. Quantity-specified buys vanish because the executor handles only notional buys. Distinguishing run: one-share signal yields zero fills despite a next bar within the limit.
2. Additional buys overwrite holdings and partial sales therefore lose inventory/cost basis. Distinguishing run: buy $20 at $10 then $20 at $20, sell 1 at $30; residual must be 2 shares at $13.333333.
3. Trailing behavior diverges because held close high-water is not maintained. Distinguishing run: pre-entry 100 followed by entry 10, held close 12 then 11 must report peaks 10, 12, 12.

## Artifacts

All test data are inline synthetic bars; socket connect/connect_ex/create_connection are denied in the new test module. No debug server, network connection, broker instance, account credential or external fixture is needed. Changes retained: execution fixes, regression tests and this audit note. The parent maintains the session debug journal.

## 확인 결과와 실제 사용 경로

- `cli_commands_basic.py:28`의 `_run_backtest()`가 CSV → `TechnicalStrategy` → `RiskManager` → 수정한 `Backtester`를 사용한다.
- `learning_runner.py:157`과 `ai_quant_lab/holdout_validation.py:101`은 별도 `ai_quant_lab.backtest_engine.BacktestEngine`를 사용한다. 이번 변경은 학습 엔진의 성과표를 고치지 않는다.
- 수정 전 직접 재현 결과: qty=1 매수 거래 `[]`; 추가 매수 후 잔량 1주(정상 2주); 보유 최고가 `[None, None, None]`(정상 `[10,12,12]`). 고정금액 매수만 처리한 분기, 보유 객체 덮어쓰기, 최고가 미갱신이 각각 원인이다.
- 지정가 10달러 주문도 다음 시가 12달러에 체결되어 한도를 위반했다. 동시 두 주문에서 두 번째가 첫 주문의 현금 예약을 보지 못해 기대 16달러 대신 남은 현금 20달러로 임의 축소 체결됐다.

## 수정 파일 및 계약

| 파일 | 변경 목적 |
|---|---|
| `nasdaq_auto_trader/backtest.py` | 시간순 이벤트, 입력봉 중복/가격 검증, 이전 신호만 다음 봉 체결, 체결 후 종가 최고가 갱신. 결과 모델은 이전 import 경로로 재노출 |
| `nasdaq_auto_trader/backtest_costs.py` | 수수료·최소 수수료·스프레드·슬리피지, 정수/소수점 수량 단위, 지정가 접촉과 시가 갭, 비용 포함 매수 가능 수량 |
| `nasdaq_auto_trader/backtest_execution.py` | 미체결 현금/위험 예약, 실제 체결 시 재검사, 추가 매수 평균단가, 부분 매도 잔량/진입수수료 배분, 체결 상태 통지 |
| `nasdaq_auto_trader/backtest_types.py` | 이전 결과 객체와 호환되는 비용·거절 사유·잔여 포지션 필드 및 선택적 체결 관찰자 계약 |
| `tests/test_early_exit_backtest*.py` | 네트워크 차단 상태의 실행·비용·위험·체결 상태 회귀 사례 |

`Backtester(strategy, risk_manager, *, costs=None, max_portfolio_risk_pct=None, max_trade_risk_pct=None, fill_observer=None, risk_includes_costs=False)`.

`BacktestCosts(commission_pct=0, minimum_commission=0, spread_bps=0, slippage_bps=0, quantity_step=1e-8)`는 호환 기본값이다. 실제 수수료가 0이라는 주장이 아니다. KIS 정수주 실험에서는 반드시 `quantity_step=1`과 확인된 수수료 또는 명시적인 가정을 전달한다. `commission_pct=0.0025`는 0.25%이다. `spread_bps`는 전체 bid/ask 폭이고 편도에 절반을 적용한다. 슬리피지는 편도 bps다. 매수/매도 각각 `max(체결금액 × commission_pct, minimum_commission)`을 차감한다.

일반 `TradeDecision.risk_per_share`는 가격 손절 거리이므로 기본적으로 왕복 비용을 위험예산에 더한다. 실험 위험관리자가 이미 왕복 비용을 포함했다면 `risk_includes_costs=True`로 정확히 한 번만 반영한다. 체결 시 불리한 갭은 보수적으로 추가 반영한다. 관찰자가 실제 초기 손절 가격을 제공하면 실제 거리와 수수료·매도 예상 체결비용을 따로 계산하여 더 큰 위험 추정치로 한도를 재검사한다.

관찰자 `initial_stop_for(symbol, fill_price)`가 None/비정상/매수가 이상이면 체결 전 거절한다. `register_entry_fill(symbol, price, qty, timestamp)`는 **체결 후 전체 평균단가와 전체 수량**을 받는다. `register_exit_fill(symbol, remaining_qty)`는 실제 잔여 수량을 받는다. 체결 없는 제출이나 미체결에 대해서는 통지하지 않는다.

`BacktestTrade.fee`는 해당 체결 수수료, `allocated_entry_fee`는 매도 수량에 배분된 진입 수수료, `gross_pnl`은 실제 체결가격 간 차익, `pnl`은 진입·청산 수수료 차감 실현손익, `execution_cost`는 기준 체결가격 대비 스프레드/슬리피지 비용이다. 스프레드/슬리피지는 이미 체결가격과 pnl에 반영되어 있으므로 재차 손익에서 차감하면 안 된다. `ending_positions`와 종가 평가 `equity_curve`가 미실현 손익을 포함한다. 최종봉 강제 매도는 하지 않는다.

## 체결 가정과 남은 한계

- 일반 신호는 완료봉 종가로 평가하고 다음 해당 종목 봉에서 체결한다. 시장가는 다음 시가와 불리한 비용, 지정가는 다음 봉 저가/고가의 접촉 여부 및 시가 갭으로 결정한다. 매수 지정가보다 비싸거나 매도 지정가보다 싸게 체결하지 않는다.
- 하루봉 실험의 day 주문은 **다음 관측 봉 한 개**에서만 체결 기회를 갖고 미접촉이면 만료한다. GTC는 해당 종목 하나의 미체결 주문으로 보존한다. 이 단순 day 수명은 분봉의 실제 장 마감 만료 모델이 아니다.
- 지정가 접촉은 전량 체결을 가정한다. 호가 큐/체결량/시장충격/실제 부분 체결 확률은 복원하지 않는다. 여러 실제 체결 이벤트에 상당하는 추가 매수와 부분 매도의 원가·잔량 계산은 지원한다.
- 높은 가격은 진입 체결가격과 보유 후 **관측 종가**만 반영한다. 보유 전 고가와 하루봉 장중 최고가를 넣지 않는다. 일봉 손절·익절을 동시에 통과해도 어느 쪽이 먼저인지 선택하지 않는다. 종료 종가에서 전략의 조건 우선순위를 평가하여 다음 봉으로 주문을 넘기므로 실시간 하드 손절 감시를 재현한 결과로 해석할 수 없다.
- 같은 시점의 종목 순서는 심볼 오름차순으로 고정한다. 현금과 위험은 앞선 주문이 예약한 값을 제외하고 다음 주문을 심사하며 체결 시 갭으로 한도를 넘으면 거절한다. 유동성 경쟁의 실제 순서를 추정한 것은 아니다.
- 외부 입출금, 배당, 분할, 환율, 운영비는 이 엔진이 생성하지 않는다. 실험 보고자가 명시적인 데이터로 별도 반영해야 한다. 입력 시각은 동일 형식/시간대의 정렬 가능한 문자열이어야 한다.
- 기존 `win_rate`는 매도 체결별 비율이다. 부분 청산을 합친 완결 거래 지표는 별도 집계해야 한다. 기존 Sharpe는 일봉 연 252 기준이며 분봉 지표로 해석하지 않는다.
- 별도 학습 엔진은 이미 정수주·시가 체결·비례 비용·보유 최고가를 구현하지만 최소 수수료/호가 스프레드/지정가/실제 부분 체결은 없다. 마지막 종가에 강제 전량 청산한다(`ai_quant_lab/backtest_engine.py:168`). 이번 CSV 엔진 변경을 학습 엔진 개선이라고 주장하지 않는다.

## 실행한 검증

1. `python -m pytest tests/test_early_exit_backtest.py -q` 최초: **3 failed** (수량매수/추가매수/최고가). 최소 수정 뒤 같은 사례와 기존 결과 객체 테스트: **5 passed, 4 subtests passed**.
2. 지정가·비용·현금/위험 예약 사례 추가 후 같은 파일: **5 failed, 3 passed**. 기능 구현 후 결과 객체 테스트 포함: **10 passed, 4 subtests passed**.
3. 비용 없는 손절 거리의 위험예산 누락과 비용 중복 방지 추가: **2 failed, 10 passed**. `risk_includes_costs` 계약 구현 후 전체 신규 실행 회귀: **28 passed, 4 subtests passed**.
4. 최종 실행 명령: 아래의 소켓 차단 하네스에서 `pytest.main(['tests/test_early_exit_backtest.py','tests/test_early_exit_backtest_edges.py','tests/test_early_exit_backtest_safety.py','tests/test_backtest_result.py','tests/test_config_engine.py','-k','backtest or early_exit','-q'])` → **28 passed, 4 subtests passed**. `test_config_engine.py`의 unittest `load_tests`는 pytest가 수집하지 않으므로 별도 실행했다.
5. 동일 소켓 차단 후 `unittest.TestLoader().loadTestsFromModule(tests.config_engine_gui_backtest_cases)`를 `unittest.TextTestRunner(verbosity=2)`로 실제 실행 → **6 tests OK** (기존 CSV/CLI 2개, GUI 보호/시간 청산/시장시간 4개; GUI 창 실행 아님).
6. `uvx ruff check nasdaq_auto_trader/backtest*.py tests/test_early_exit_backtest*.py` → **All checks passed!**
7. `python -m compileall -q nasdaq_auto_trader/backtest.py nasdaq_auto_trader/backtest_costs.py nasdaq_auto_trader/backtest_execution.py nasdaq_auto_trader/backtest_types.py` → exit 0.
8. LSP diagnostics 실제 호출: basedpyright 미설치이며 사용자가 이전 설치를 거절했다는 도구 응답. 따라서 타입 검사 통과를 주장하지 않으며 새로 설치하지 않았다.

소켓 차단 공통 하네스(프로세스 종료 시 사라짐):

```python
import socket

def denied(*args, **kwargs):
    raise AssertionError('network disabled for offline backtest')

socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
```

실제 CSV CLI 수동 QA도 위 차단을 적용한 프로세스에서 수행했다. `TemporaryDirectory` 안에 합성 OHLCV CSV와 `mode=dry_run, order_qty=1` 설정을 만들고 `cli.main(['--config', config, 'backtest', '--csv', csv, '--cash', '10000'])` 호출. 결과 **exit 0, 7 fills**, 첫 체결은 signal `2026-01-02T05:00:00+00:00` → fill `2026-01-02T06:00:00+00:00`, qty=1, price=129. 임시 파일은 context 종료 때 제거했다. 합성 자료의 종료잔고 10038.5는 실행 경로 확인용이며 실제 투자 성과/전략 비교 근거가 아니다. 브로커 생성·실제 주문·예약 작업을 실행하지 않았다.
