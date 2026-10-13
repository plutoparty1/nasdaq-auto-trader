# 실제 5분 자료의 보조 A/B/C 실험

2026-09-29 실행. **4개 거래일에서 C의 신호 충돌·반복 청산 감소는 관측됐지만 수익 전략의 근거는 아니다.** 모든 정책이 손실이었고, 비용 스트레스에서는 모두 체결이 없었다. 일일 최소매수만 제거한 B는 이 표본의 A와 같았다. 월 수익률을 추정하지 않았다.

이 파일의 체결·손익은 실제 KIS 가격을 이용한 **모의 체결**이다. 개인 거래 원장을 출력하거나 저장한 결과가 아니다. 당시 실제 체결 시각을 복원한 것으로 해석하면 안 된다.

## 자료와 동결 조건

- 사건을 포함한 2026-09-23, 24, 25, 28의 미국 정규장 네 세션만 사용했다. CMCSA/KDP/HIVE 각 312개 정규장 5분 관측 슬롯이며 수집기 기준 누락 0개다. 장외, 9/22의 불완전 시작 구간, 9/29 수집 당일 자료를 제외했다.
- 5분 OHLCV는 KIS OpenAPI다. 미국 날짜/시각과 한국 날짜/시각의 교차 검증에 불일치가 없었다. `evol`을 volume으로 사용했다. 시작/종료 봉 라벨 의미는 확정되지 않아 **공급자 라벨 +5분 뒤에 이용 가능하다는 보수적 가정**을 적용했다. 실제 체결 시각과 같다고 주장하지 않는다.
- 기술지표는 5분봉이 아니라 **직전 미국 거래일까지만 완성된 일봉**으로 계산한다. 당일의 완성 전 일봉과 미래 날짜를 전달하지 않는다. 일반 신호의 동일 봉 식별자는 마지막 이전 일봉 close 시각이며, 보호 판단의 보유 평가 가격은 매 5분 현재 관측 종가다.
- 일봉은 주 비교와 같은 공개 Yahoo Finance 자료의 2026-01-06 이후 부분이며 종목별 183봉이다. CMCSA의 1/5 기업행위 이전 조정가격 영향은 제외했다. 9/23 이전 기술지표 준비 기간은 충족한다. KIS 5분과 공개 일봉의 공급자가 다르고 과거 시점의 미수정 snapshot은 없다는 한계가 남는다.
- 기존 3% 고정 손절, 5% 익절, 2% 활성/1% 트레일링, 일봉 ATR14×3/×5, 점수 및 지표 설정을 A/B/C 모두 동일하게 유지했다. 기존 legacy 청산 동작을 쓰며 8%·10%·진입 ATR 실험과 섞지 않는다.
- 모든 정책은 같은 수정 `Backtester`, `BacktestCosts`, `MatchedEntryRisk`를 쓴다. 시작 80,000원 상당, 거래당 1%, 수량 1주, 최대 매수 $35, 종목당/총 노출 50%, 현금 5%, 일일 손실 2% 시 신규 매수 중단이다. 당시 최소매수의 별도 5% 위험 덮어쓰기는 포함하지 않는다.
- 초기 FX는 ECB의 2026-09-22 16:00 UTC 이용 가능 관측값 **1 USD = 1,356.1458605949576 KRW**다. ECB의 KRW/EUR ÷ USD/EUR로 계산한다. 9/23 오전에는 아직 그날 16:00 UTC 관측을 쓰지 않으며 이후 평가에는 시점 이전 FX만 반영한다.
- 기본 비용은 앞선 고정 시나리오 편도 0.25%, 최소 $0, spread 10bp, slippage 10bp다. 스트레스는 편도 0.30%, 최소 $0.10, spread 30bp, slippage 30bp다. 실제 계좌 청구 요율이 아니다.
- 설정·세션·자료 hash·환율·비용·타임스탬프 가정을 결과 계산 전에 [protocol.json](intraday-actual-comparison/protocol.json)에 기록했다. 결과를 보고 정책 수치를 다시 선택하지 않았다.

실제 데이터 위치와 품질 근거: [공개 자료](public-data.md), [KIS 수집 요약](kis-acquisition-final.json). CSV 원본은 `C:/Users/u/AppData/Local/NasdaqAutoTrader/research/entry-policy-20260929/` 아래 `public/` 및 `20260929T123807850034Z/`에 있다. 원본 시장 데이터·실제 계좌 원장을 Git에 추가하지 않았다.

## 비교 결과

기본 비용 결과. USD 순수익에는 미실현 보유손익과 비용이 포함된다. 평균 보유시간은 모의 완전 청산의 체결 라벨 간 시간이며 밤·주말을 포함한 경과시간이다.

| 항목 | A: 최소매수 포함 제한 기준선 | B: 최소매수 제거 | C: B + 충돌·반복 신호 차단 |
|---|---:|---:|---:|
| 매수 조건 미충족 진입 체결 | 0 | 0 | 0 |
| 강제 진입 체결 | 0 | 0 | 0 |
| 매도 점수도 충족한 진입 체결 | 6 | 6 | 0 |
| 다음 평가 일반매도 → 체결 | 5 | 5 | 0 |
| 위 사례 중 매수·매도 모의 체결 라벨 간격 5분 | 5 | 5 | 0 |
| 완결 거래 | 8 | 8 | 2 |
| 평균 보유시간(분) | 549.375 | 549.375 | 110.0 |
| 거래비용 합계 USD | 0.197058 | 0.197058 | 0.040377 |
| 실현손익 USD | -0.352971 | -0.352971 | -0.236377 |
| 미실현손익(매수비용 반영) USD | -0.042688 | -0.042688 | 약 0 |
| 기간 USD 계좌 순수익률 | -0.670713% | -0.670713% | -0.400702% |
| 기간 KRW 환율 포함 수익률 | -0.540213% | -0.540213% | -0.269847% |
| USD 최대 낙폭 | -0.746996% | -0.746996% | -0.400702% |
| 완전 달력월 표본 | 0 | 0 | 0 |

기본 비용에서 실제로 모의 체결된 종목은 HIVE뿐이다. A에는 CMCSA 12회·KDP 9회 강제 진입 판단이 있었으나 공통 1% 위험/가격/수량 조건에서 주문이 제한되어 체결되지 않았다. 과거 실제 운용의 5% 최소매수 위험 덮어쓰기와 학습 순위를 재현하지 않았으므로 **과거 CMCSA/KDP 사건 자체의 경제적 손익 replay가 아니다.** 이는 A=B 결과의 중요한 해석 조건이다.

C는 여기서 약 0.27%p 덜 손실을 보았고 거래비용도 감소했다. 그러나 A/B가 남긴 미실현손실을 포함한 결과이며, C도 순손실이다. 네 세션·실질 체결 1종목의 관측만으로 미래 수익 개선이나 월 +10%를 뒷받침할 수 없다. 거래 수 감소만으로 유리하다고 판정하지 않는다.

| 기본 비용 매도 이유 | A/B 체결 수 / 순손익 USD | C 체결 수 / 순손익 USD |
|---|---:|---:|
| fixed_stop_loss | 2 / -0.239438 | 2 / -0.236377 |
| 일반 기술적 신호 | 5 / -0.147213 | 0 / 0 |
| trailing_profit_protection | 1 / +0.033680 | 0 / 0 |

C에서도 하드 손절 2건이 정상적으로 실행된다. 손실이면 매도하지 않는 정책으로 조기매도 문제를 가린 결과가 아니다.

**비용 스트레스에서는 A/B/C 모두 체결 0건이다.** USD 기간수익률 0%, 원화 환산 +0.131381%는 달러 현금의 FX 변화이며 매매 수익이 아니다. `no_executions`로 표시하고 전략 우수성 증거로 사용하지 않는다. 월 수익률·최악의 월·월 +10% 달성 비율은 미산출이다. summary의 complete_calendar_months=0/target_complete_calendar_months=0을 0% 달성 확률로 해석하지 않는다.

결과 파일: [summary.csv](intraday-actual-comparison/summary.csv), [모의 체결](intraday-actual-comparison/fills.csv), [계좌 평가액](intraday-actual-comparison/equity.csv), [매도 사유](intraday-actual-comparison/reasons.csv), [동일 데이터 양방향 점수](intraday-actual-comparison/decisions.csv), [위험 거부](intraday-actual-comparison/entry_skips.csv), [미체결 거부](intraday-actual-comparison/order_rejections.csv).

## 체결·자료의 한계

`Backtester`는 신호 후 다음 관측 봉에서 지정가 도달 여부를 검사한다. 이 공통 엔진의 DAY 미체결 주문은 **다음 관측 5분봉 한 개에서 미도달하면 만료**한다. 실제 거래소 DAY 주문이 장 마감까지 대기하는 것과 다르다. 마지막 세션 봉에서 생긴 주문이 다음 세션 첫 관측까지 남을 수 있으므로 실제 DAY 만료·장마감 주문 처리를 정확히 재현하지 않는다. 모든 A/B/C에 같은 가정이며 이 한계 때문에 실전 체결 성능으로 해석하지 않는다.

5분 OHLC 범위에 지정가가 닿아도 실제 호가 대기열·스프레드·부분체결을 알 수 없다. 봉 안의 손절/익절 발생 순서는 추정하지 않고 5분 관측 종가에서 보호를 판단한다. 매수는 기존 순수 함수 `price_entry_decision()`으로 현재 5분 종가에 재가격화하지만 이는 실제 ask를 확보한 것이 아니다. 일반 매도는 기존 전략의 일봉 판단 가격, 보호 매도는 보유의 현재 mark를 사용하는 기존 구분을 유지한다.

과거 GUI는 평가 시마다 변하는 당일 일봉을 받았을 수 있다. 이번 실험은 미래 정보 사용을 피하기 위해 이전에 완성된 일봉을 고정한다. 이 차이와 당시 최종 설정·학습 선정 snapshot 부재 때문에 exact incident replay라고 부르지 않는다. 공급자 라벨 +5분 가정 아래 5분 간격의 모의 왕복이 재현됐다는 범위까지만 말한다.

## 구현·검증·재실행

변경 파일은 `nasdaq_auto_trader/entry_intraday_replay.py`, `tests/test_entry_intraday_replay.py`, 이 문서다. 일봉 전략과 5분 체결 이벤트를 연결하는 오프라인 adapter다. 운영 엔진, 설정, 보유 정책, EXE에 연결하지 않았다.

실행한 검증 명령:

```bash
PYTHONIOENCODING=utf-8 python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_entry_intraday_replay.py
uvx --offline ruff check nasdaq_auto_trader/entry_intraday_replay.py tests/test_entry_intraday_replay.py
python -m py_compile nasdaq_auto_trader/entry_intraday_replay.py
```

최종 집중 결과 **10 passed in 2.10s**, Ruff All checks passed, compile exit 0. 기존 전체 테스트 수와 합산하지 않는다. 처음에는 미구현 모듈로 수집 실패했고 구현 후 6개 통과/1개 fixture 생성 인수 오류가 발생했다. CostScenario의 필수 source를 fixture에 넣은 뒤 해결했다. 추가 출력 보존 시험은 기존 summary.csv가 있는 폴더에서 실패를 확인한 후 수정했다: `1 failed (DID NOT RAISE)` → 최종 10개 모두 통과. 기존 파일 또는 frozen protocol이 있는 출력 디렉터리는 계산 전에 거부한다.

회귀는 동일 일봉의 A 강제매수→다음 5분 일반매도, B/C no_trade, 당일/미래 일봉 배제, C 중복 봉의 새 가격 하드 손절, 일반장/완성 여부 필터, 명시적 라벨 가정, 5분 정렬, protocol 동결, 기존 결과 보존을 포함한다.

실제 자료 직접 실행은 Git Bash의 `python - <<'PY'`에서 다음 API로 진행했다. 실행 전에 `sys.addaudithook`으로 `socket.*`, `http.client.connect`, `urllib.Request`, `subprocess.Popen`을 모두 거부하고, 임시 `ModuleType` package 경로로 앱 `__init__` import를 생략했다. 이 격리와 기본 dry_run 프로필을 유지해야 한다.

```python
config = load_entry_profile(Path("experiments/entry_policy/profile.json"))
costs = load_settings(Path("experiments/early_exit/settings.json")).costs
run_intraday_replay(
    config, daily_bars, kis_five_minute_bars,
    tuple(ReplaySession(f"2026-09-{day}T13:30:00+00:00", f"2026-09-{day}T20:00:00+00:00")
          for day in ("23", "24", "25", "28")),
    fresh_output_directory, costs,
    fx_rate=1356.1458605949576, fx_history=ecb_fx_history,
    manifest=source_manifest_with_hashes,
)
```

실제 실행 결과 network_attempts=0, live broker/engine/config imports=0이었다. 6개 정책·비용 조합의 312개 평가 기록 각각을 대상으로 시작 현금 + 체결 현금흐름 = 종료 현금, fee + execution_cost = 총비용, 현금 + 미실현 보유 평가액 = 계좌 평가액을 별도 재계산했고 모두 일치했다. 실제 수익 결과는 입력/수치를 바꾸어 재실행하지 않았다. 출력 보존 수정은 계산식을 변경하지 않는다.

재실행은 protocol에 기록된 시장자료 hash와 FX 이력을 유지하고 **새 빈 출력 폴더**를 사용한다. 운영으로 되돌리는 변경은 필요 없다. 실험 파일을 운영 설정에 복사하거나 EXE를 교체하지 않는다.

최종 코드 검토 후 공통 체결 엔진의 `max_total_position_pct=0.5`도 명시적으로 전달했다. 제출 시 검사에 더해 체결 시점의 시가 평가액·주문 예약·수수료를 반영해 총 투자 상한을 다시 검사한다. 관련 직접 실행은 `python scripts/run_offline_tests.py -q -p no:cacheprovider tests/test_entry_intraday_replay.py tests/test_entry_fill_exposure.py`이며 **23 passed in 3.15s**였다. 위 집중 10개와 중복되므로 합산하지 않는다. 기존 실제 자료 결과의 모든 종가 평가 기록을 별도 재검사한 최대 투자 비중은 **5.938303%**였다. 이번 한도 검사 추가로 수익 결과를 다시 계산하거나 기존 산출물을 덮어쓰지 않았다.
