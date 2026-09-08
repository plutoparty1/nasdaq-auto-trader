# PRD: 일일 최소 1주 안전 주문 시도

**Version**: 0.2  
**Author**: Codex  
**Date**: 2026-08-11  
**Status**: Approved  
**Size**: L

---

## 1. Problem Statement

### 1.1 Background

현재 AI 자동선택 경로는 적격 전략과 신호가 없으면 정상적인 `no_trade`로
종료하며 대체 주문을 만들지 않는다. 이 동작은 불필요한 거래를 막지만,
운영자는 뉴욕 정규 거래일마다 기존 전략 주문이 한 건도 없을 때에도 1주짜리
최소 주문을 한 번 시도하기를 원한다.

현재 시스템에는 LIVE 환경 잠금, 시장일/실주문 시도 한도 승인, 현금·손실·노출 한도,
정규장 제한, 중복 신호 방지, 결과 불명 주문 차단이 있다. 신규 기능은 이
안전장치를 우회하지 않고 별도의 명시적 동의 설정으로만 활성화되어야 한다.

### 1.2 Problem Definition

뉴욕 정규 거래일의 장 마감 60분 전까지 매수·매도 주문 시도가 0건이면,
검증된 프로그램 소유 1주를 매도하거나 승인된 최상위 후보 1주를 매수하는
단 한 번의 안전 주문 시도를 생성한다.

### 1.3 Impact of Not Solving

- 신호가 드문 시장 구간에는 여러 거래일 동안 실제 주문 경로가 실행되지 않는다.
- 운영자가 요청한 일일 최소 주문 활동을 자동운영이 충족하지 못한다.
- 임시 수동 주문으로 우회하면 기존 감사·중복·대사 안전장치 밖에서 주문할 위험이 있다.

## 2. Goals & Non-Goals

### 2.1 Goals

- [ ] G1: 뉴욕 정규 거래일마다 기존 주문 시도가 0건이고 모든 안전 게이트가
  통과할 때 1주 주문을 최대 한 번 시도한다.
- [ ] G2: 프로그램이 정확히 소유권을 확인한 1주가 있으면 매도를 우선한다.
- [ ] G3: 소유 포지션이 없으면 현재 LIVE 승인 전략이 생성한 신호 중
  진입 임계값 적용 전 최상위 적격 후보를 1주 매수 대상으로 사용한다.
- [ ] G4: 재시작·동시 실행·응답 유실 상황에서도 중복 POST를 0건으로 유지한다.
- [ ] G5: 주문 의도, 제출, 차단, 대사 결과를 비밀정보 없이 감사 로그와 GUI에 표시한다.

### 2.2 Non-Goals

- NG1: 체결을 보장하거나 시장가 주문으로 가격 위험을 무제한 수용하지 않는다.
- NG2: 휴장, 실거래 승인 만료, 현금 부족, 손실 한도, 데이터 오류, 브로커 거절을
  우회하지 않는다.
- NG3: baseline 0의 exact app fill과 전용운영 동의로 소유권을 설정하지 않은 수동
  보유 종목이나, 관측 가능한 소유권 모순이 있는 포지션을 강제 매도하지 않는다.
- NG4: 결과 불명 POST를 추정하거나 자동 재제출하지 않는다.
- NG5: 한 거래일에 두 번째 최소 주문을 만들지 않는다. 최소 주문의 1회 잠금은 이후 정상 전략 주문을 제한하지 않는다.
- NG6: 이번 버전에서 Alpaca LIVE 강제 주문을 지원하지 않는다. 대상은 현재 운영 중인
  KIS 해외주식 LIVE 경로다.
- NG7: 기존 전략의 신호 계산, 종목 점수, 손절·익절 규칙을 변경하지 않는다.
- NG8: 거래일 경계를 넘어 같은 실거래 승인을 재사용하지 않는다.

## 3. User Stories & Acceptance Criteria

### US-1: 주문이 없는 날의 최소 1주 주문 시도

**As a** 무인 실거래 운영자, **I want** 거래일마다 주문이 없으면 1주 주문을
한 번 시도하고, **so that** 실제 주문 경로가 안전하게 일일 최소 활동을 수행한다.

**Acceptance Criteria:**

- [ ] AC-1.1: 뉴욕 정규 거래일의 장 마감 60분 전 이후 첫 자동운영 사이클에서,
  `close-60분 <= now < min(기존 매수중지시각, close)`인 경우에만, 당일 매수·매도
  안전 예약 합계가 0이면 최소 주문 평가를 정확히 한 번 수행한다. 설정된 매수중지
  시각이 `close-60분` 이하이면 해당 거래일 최소 주문을 평가하지 않는다.
- [ ] AC-1.2: 당일 기존 전략 주문 시도가 한 번이라도 있으면 최소 주문을 만들지 않는다.
- [ ] AC-1.3: 기능이 비활성화되어 있으면 기존 `no_trade` 동작과 결과가 바이트 수준의
  공개 계약에서 변하지 않는다.
- [ ] AC-1.4: 정규장 밖이거나 마감 60분 전 평가 시점을 놓쳤으면 다음 날로 이월하거나
  장외 주문을 만들지 않는다.
- [ ] AC-1.5: 당일 주문 0건 확인, 일일 평가 claim, 주문 방향의 안전 예약은
  canonical `TradingSessionStore`에서 조정한다. 먼저 0건 확인+평가 claim을 원자 저장하고,
  POST 직전 같은 잠금에서 0건을 재확인한 뒤 safety reservation+intent+
  `post_may_have_started`를 한 번의 원자 저장으로 수행한다.
- [ ] AC-1.6: 승인 만료, 후보 없음, lease 충돌, 위험 게이트 차단처럼 POST 전에 끝난
  평가도 해당 시장일의 단 한 번인 평가를 소비하며 같은 날 다시 평가하지 않는다.
- [ ] AC-1.7: daily evaluation claim은 다른 daily 평가만 막으며 이후 정상 전략 주문을
  막지 않는다. 단, `POST_MAY_HAVE_STARTED`, `ORDER_KNOWN`, manual terminal의 결과불명
  노출은 시장일과 무관하게 모든 자동 POST를 차단하고 대사를 먼저 수행한다.

### US-2: 소유권이 확인된 1주 매도 우선

**As a** 계좌 소유자, **I want** 프로그램이 만든 1주만 우선 매도하고,
**so that** 수동 보유분이 자동으로 처분되지 않는다.

**Acceptance Criteria:**

- [ ] AC-2.1: 정확한 주문 ID와 후속 보유수량 대사로 확인된 최소주문 소유분만
  `owned_symbol`, `owned_quantity=1`로 기록한다.
- [ ] AC-2.2: 소유 상태와 브로커의 최신 보유수량이 일치할 때만 1주 매도를 만든다.
- [ ] AC-2.3: 보유수량이 줄었거나 늘었거나 종목이 다르면 매도하지 않고
  `daily_minimum_ownership_mismatch`로 차단한다.
- [ ] AC-2.4: 매도 접수 후 정확한 주문 ID와 보유수량 감소가 확인될 때만 소유 상태를 지운다.
- [ ] AC-2.5: 최소 매수 직전 동일 종목 보유수량은 정확히 0이어야 하며, 정확한 매수
  주문 ID가 `FILLED`, 체결수량 1, 최신 총보유수량 1, 미결 잔량 0이고 그 사이 외부
  체결·이체·분할이 없을 때만 프로그램 소유 1주로 확정한다.
- [ ] AC-2.6: 매도는 최신 총보유수량이 정확히 1이고 외부 변동이 없을 때만 허용한다.
  정확한 매도 주문 ID가 `FILLED`, 체결수량 1, 최신 총보유수량 0일 때만 완료한다.
  부분체결·수량 불일치·기업행동·외부 체결은 수동대사 terminal 상태로 전환한다.
- [ ] AC-2.7: KIS 주문·포지션 API는 이체/기업행동의 완전한 부재를 증명하지 못하므로,
  자동 소유권은 baseline 0, exact app order fill, observable contradiction 0과
  “owned symbol을 외부에서 거래·이체하지 않는다”는 감사된 전용운영 동의에 한정한다.

### US-3: 적격 후보 1주 매수

**As a** 무인 실거래 운영자, **I want** 소유분이 없을 때 승인된 후보 중 하나를
1주 매수 대상으로 사용하고, **so that** 수동 티커나 무승인 종목으로 폴백하지 않는다.

**Acceptance Criteria:**

- [ ] AC-3.1: LIVE로 승격된 `CHAMPION` 전략과 최신 유니버스가 만든 신호를
  진입 임계값 적용 전에 점수 내림차순·종목 오름차순으로 정렬한 첫 적격 종목만
  최소 주문 후보가 된다.
- [ ] AC-3.2: 정상 `no_trade`에서는 임계값 미달 신호의 최상위 후보를 사용할 수
  있지만, 선택이 `blocked`이거나 유효한 신호가 하나도 없으면 수동 티커로
  대체하지 않고 `daily_minimum_candidate_unavailable`로 끝낸다.
- [ ] AC-3.3: 후보에 이미 포지션이 있거나 최대 보유수량·노출·현금 한도를 넘으면
  다음 후보를 평가하되 모든 후보가 막히면 주문하지 않는다.
- [ ] AC-3.4: KIS의 최신 가격을 사용한 1주 지정가 DAY 주문만 허용한다.
- [ ] AC-3.5: 매수는 POST 직전 동기 GET의 KIS `pask1`, 매도는 `pbid1`을 사용한다.
  값은 USD, 유한한 양수, `ask >= bid`, configured `max_spread_bps` 이하여야 한다.
  로컬 monotonic request 시작부터 응답까지 5초를 넘으면 stale로 차단한다.
- [ ] AC-3.6: 신규 shared Decimal normalizer는 가격 `>=1 USD`에 tick `0.01`, 그 아래에
  tick `0.0001`을 적용한다. BUY ask는 ceiling, SELL bid는 floor로 정규화한 뒤 기존
  `_format_price`로 직렬화한다. 캐시·last 폴백·재호가는 없다. 값이 잘못된 후보는 다음
  ranked 후보로 이동하지만 quote GET timeout/deadline은 평가를 즉시 차단한다.
- [ ] AC-3.7: `TradingSettings.daily_minimum_max_spread_bps`는 기본 50, 허용범위
  1..500이다. spread는 `10_000 * (ask-bid) / ((ask+bid)/2)`이고 설정값 이하를 허용한다.

### US-4: 중복 방지와 결과 불명 차단

**As a** 운영자, **I want** 네트워크 장애나 재시작이 중복 주문을 만들지 않기를
원하고, **so that** 주문 결과가 불분명할 때 계좌 노출이 증가하지 않는다.

**Acceptance Criteria:**

- [ ] AC-4.1: POST 전에 날짜·종목·방향·수량·가격을 포함한 의도를 원자적으로 저장한다.
- [ ] AC-4.2: POST 응답에서 정확한 KIS 주문번호를 얻지 못하면 상태를
  `MANUAL_RECONCILIATION_REQUIRED`로 전환하고 신규 최소 주문을 영구 차단한다.
- [ ] AC-4.3: 재시작 시 ID 없는 `POST_MAY_HAVE_STARTED`는 즉시 수동대사 terminal로
  고정한다. `ORDER_KNOWN`만 exact ID GET으로 대사하며, 미해결인 동안 새로운 POST는 없다.
- [ ] AC-4.4: 명시적으로 거절된 주문도 해당 거래일의 한 번뿐인 시도로 계산하고
  자동 재제출하지 않는다.
- [ ] AC-4.5: `post_may_have_started=true`를 fsync한 뒤에만 POST를 호출한다. 이 상태에서
  정확한 주문번호가 저장되지 않은 채 종료되면 broker GET 결과와 관계없이
  `MANUAL_RECONCILIATION_REQUIRED`이며 날짜가 바뀌어도 신규 POST를 영구 차단한다.
- [ ] AC-4.6: 당일 주문 0건 판정에는 동일 `TradingSessionStore`의 자동 매수·매도 예약과
  KIS 당일 주문 history가 모두 포함된다. broker lease를 잡은 상태에서 fresh open-order,
  history, position GET을 수행하고, 미식별 미결 주문이나 카나리의 known/manual 상태가
  있으면 POST 0으로 끝낸다.

### US-5: 운영자 가시성

**As a** 운영자, **I want** 최소 주문의 결정과 차단 이유를 확인하고,
**so that** 실제 주문 여부를 추측하지 않는다.

**Acceptance Criteria:**

- [ ] AC-5.1: 감사 로그에 `daily_minimum_evaluated`, `daily_minimum_intent`,
  `daily_minimum_submitted`, `daily_minimum_blocked`, `daily_minimum_reconciled`를 기록한다.
- [ ] AC-5.2: GUI 실행 로그에는 날짜, 방향, 종목, 1주, 결과와 안정적인 사유 코드만 표시한다.
- [ ] AC-5.3: 계좌번호, API 키, 토큰, 원시 브로커 응답은 상태·감사·GUI 로그에 저장하지 않는다.
- [ ] AC-5.4: 기능을 false로 바꿔도 기존 `ORDER_KNOWN`, 프로그램 소유 1주,
  `MANUAL_RECONCILIATION_REQUIRED`의 GET 대사와 지속적 고우선순위 경고는 유지한다.

### US-6: 승인·계좌 바인딩

**As a** 계좌 소유자, **I want** 새 최소주문 정책과 현재 계좌가 실거래 승인에
정확히 묶이기를 원하고, **so that** 이전 승인이나 다른 계좌 상태가 재사용되지 않는다.

**Acceptance Criteria:**

- [ ] AC-6.1: versioned `daily_minimum_policy_digest`는 enabled 상태, 정책 버전,
  후보 전략/유니버스, 수량 1, 주문종류 DAY limit, 시간창, max spread, 5초 quote
  deadline, tick policy version, exclusive-owned-symbol 동의를 포함하며
  `LiveAuthorizationEnvelope`, `AutomaticOrderContext`, session state에 함께 바인딩된다.
- [ ] AC-6.2: 기능 false에서 true로 변경하거나 정책 digest가 달라지면 기존 승인은
  `live_authorization_binding_changed`로 무효화되고 신규 명시 승인을 받기 전 POST 0이다.
- [ ] AC-6.3: 상태 load·대사·평가 첫 경계에서 현재 KIS 계좌 바인딩과 저장된 바인딩이
  정확히 일치하지 않으면 `daily_minimum_account_binding_changed` terminal 상태로
  전환하고 주문 GET 해석과 POST를 모두 금지한다.

## 4. Technical Design

### 4.1 Architecture Overview

```text
정상 자동선택 사이클
  -> 기존 전략/위험/주문 처리
  -> 장 마감 60분 전 + 기능 활성화
  -> DailyMinimumPolicy (순수 결정)
       -> 확인된 소유 1주: SELL 우선
       -> 소유 없음: 승인 전략의 임계값 적용 전 일일 후보 순위에서 BUY 후보
  -> TradingSessionStore 원자 claim
       -> 당일 안전 예약 합계 0 확인 + `EVALUATED_PREFLIGHT` 저장
  -> 기존 AutomaticOrderGuard의 동일 cycle/context/authorization 경로
  -> account-wide broker lease 획득
  -> fresh open-order/history/position/quote GET preflight
  -> intent 감사 fsync
  -> 같은 store lock에서 당일 합계 0 재확인
       -> safety reservation + intent + post_may_have_started 원자 저장
  -> KIS 1주 지정가 POST 최대 1회
  -> 정확한 주문번호 기반 GET 대사
  -> 소유권/완료/수동대사 상태 갱신
```

미해결 daily state를 먼저 대사하는 전역 게이트를 제외하면 기존 전략 주문 경로는
최소주문보다 선행하며 결정 규칙을 변경하지 않는다. 최소 주문 코디네이터는 자동선택
사이클이 정상적으로 계좌·포지션·선택 결과를 확보한 뒤에만 실행한다. 선택 자체가
운영상 차단되었거나 계좌 조회가 실패하면 최소 주문도 함께 차단한다.

단, 매 cycle/startup의 가장 첫 주문 단계는 daily state 대사다. account-wide
`POST_MAY_HAVE_STARTED`, `ORDER_KNOWN`, `MANUAL_RECONCILIATION_REQUIRED`가 있으면
시장일과 무관하게 정상 전략을 포함한 모든 자동 POST를 차단한다. `EVALUATED_PREFLIGHT`
재시작은 POST가 시작되지 않았으므로 `EVALUATED_BLOCKED`로 닫고 정상 전략은 허용한다.
owned lot 자체는 다른 종목의 정상 주문을 막지 않는다. owned symbol의 추가 BUY는
차단한다. 다만 기존 guarded strategy/risk engine이 현재 position을 줄이기 위해 만든
수량 1의 SELL은 손절·익절·trailing/time exit를 약화하지 않도록 허용한다. 이 SELL은
daily owned-exit intent에 연결해 POST 전 fail-closed 상태를 저장하고 exact order ID를
같은 reconciler로 대사한다. full fill+position 0이면 owned lot을 제거하고,
timeout/unknown/partial이면 account-wide manual terminal로 전환한다.

### 4.2 Data Model Changes

별도 삭제 가능한 일일 JSON을 만들지 않는다. 기존
`%LOCALAPPDATA%\NasdaqAutoTrader\runtime\trading_session.json`의
`TradingSessionStore`를 schema version 2로 확장하고, 기존 safety count·signal claim과
같은 파일 잠금 및 원자 교체를 사용한다. schema 1은 최초 load에서 기존 필드를 보존한
채 비활성 daily state를 추가하여 schema 2로 원자 migration한다. 손상, 알 수 없는
future schema, 시장일 역행, migration 쓰기 실패는 fail closed이며 POST 0이다.

일일 평가와 장기 소유권은 서로 다른 typed record다.

| Record / Field | Type | Invariant |
|---|---|---|
| `daily_attempt.market_date` | ISO date | 거래소 달력의 시장일, 역행 금지 |
| `daily_attempt.state` | enum | `NOT_EVALUATED`, `EVALUATED_PREFLIGHT`, `EVALUATED_BLOCKED`, `POST_MAY_HAVE_STARTED`, `ORDER_KNOWN`, `COMPLETED_NO_FILL`, `COMPLETED_FILLED`, `MANUAL_RECONCILIATION_REQUIRED`, `RESOLVED_NO_EXPOSURE`, `HANDOFF_CONFIRMED` |
| `daily_attempt.evaluated_at` | aware datetime/null | claim과 함께 한 번만 기록 |
| `daily_attempt.terminal_reason` | stable code/null | blocked/reject/no-fill/manual 이유 |
| `daily_attempt.intent` | typed object/null | 종목·방향·수량 1·정규화 지정가·제출 시장일 |
| `daily_attempt.post_may_have_started` | bool | POST 직전 fsync하며 true에서 false로 역행 금지 |
| `daily_attempt.known_order` | typed object/null | 정확한 주문 ID·종목·방향·수량·가격·제출 시장일 |
| `owned_lot` | typed object/null | acquisition order ID/date, symbol, quantity=1, baseline=0 |
| `account_binding` | HMAC digest | 현재 KIS 계좌/상품 바인딩, 원시 계좌번호 저장 금지 |
| `policy_digest` | digest | 승인된 versioned 최소주문 정책과 정확히 일치 |

`account_binding`은 설치별 무작위 키로 HMAC-SHA256을 계산한다. 키는 Windows
DPAPI CurrentUser로 보호해 앱 데이터에 저장하고, 현재 사용자와 SYSTEM ACL만 허용한다.
비교는 constant-time으로 수행한다. 계좌 원문이나 무염 SHA-256 계좌 지문은 신규
daily state에 저장하지 않는다.

상태 전이는 다음 표 외에는 codec에서 거부한다.

| From | Event | To | 다음 시장일 동작 |
|---|---|---|---|
| `NOT_EVALUATED` | 0건 확인+평가 claim | `EVALUATED_PREFLIGHT` | 재시작 시 `EVALUATED_BLOCKED(interrupted_before_post)`, POST 0 |
| `EVALUATED_PREFLIGHT` | policy/guard/lease/GET/quote/audit 준비 차단 | `EVALUATED_BLOCKED` | 새 `NOT_EVALUATED`, owned lot은 별도 보존 |
| `EVALUATED_PREFLIGHT` | 0건 재확인+safety reservation+intent+post-start 원자 저장 | `POST_MAY_HAVE_STARTED` | 자동 rollover 금지 |
| `POST_MAY_HAVE_STARTED` | 정확한 주문 ID 응답을 같은 원자 저장에 기록 | `ORDER_KNOWN` | 제출 시장일로 계속 대사 |
| `POST_MAY_HAVE_STARTED` | 예외·종료·ID 누락 | `MANUAL_RECONCILIATION_REQUIRED` | 영구 fail closed |
| `ORDER_KNOWN` | exact order가 open | `ORDER_KNOWN` | 제출 시장일로 계속 대사, 신규 POST 금지 |
| `ORDER_KNOWN` | exact full fill + exact position equation | `COMPLETED_FILLED` | BUY면 owned lot 보존, SELL이면 owned lot 제거 |
| `ORDER_KNOWN` | exact order가 terminal reject/cancel/expire, fill=0 | `COMPLETED_NO_FILL` | 다음 시장일 새 평가 허용 |
| `ORDER_KNOWN` | absent/ambiguous/partial/mismatch/external mutation | `MANUAL_RECONCILIATION_REQUIRED` | 영구 fail closed |
| `EVALUATED_BLOCKED` / `COMPLETED_*` / `RESOLVED_*` / `HANDOFF_CONFIRMED` | 시장일 증가 | 새 `NOT_EVALUATED` | owned lot은 인수일과 함께 보존, handoff면 제거 |
| 모든 상태 | 계좌·날짜·schema 불일치 | `MANUAL_RECONCILIATION_REQUIRED` 또는 load fail | 운영자 대사 전 POST 0 |
| 새 평가 | 현재 policy digest가 승인/세션과 불일치 | `EVALUATED_BLOCKED` | 재승인 전 POST 0 |
| `MANUAL_RECONCILIATION_REQUIRED` | typed admin evidence + 운영자 확인 | `RESOLVED_NO_EXPOSURE` 또는 `HANDOFF_CONFIRMED` | 신규 자동 POST 해제 여부를 명시 저장 |
| `COMPLETED_FILLED` + owned lot, pending order 0 | 자발적 수동 인계 확인 | `HANDOFF_CONFIRMED` | owned lot 제거, 기존 승인 무효화 |

`POST_MAY_HAVE_STARTED`에는 “주문이 없었다”는 GET 결과만으로 자동 복구하지 않는다.
request bytes 전송 여부를 증명할 수 없기 때문이다. `ORDER_KNOWN`만 GET으로 자동
대사한다. 알려진 주문은 새 현재일이 아니라 저장된 `submitted_market_date`를 포함한
history 구간에서 ID+종목+방향+수량+가격을 모두 exact match한다.

기능 flag나 policy digest가 바뀌어도 이미 알려진 exact order는 제출 당시 immutable
digest와 account binding으로 GET 대사를 계속한다. 다만 신규 평가·POST는 새 digest에
대한 승인이 없으면 차단한다. 기존 owned lot은 계좌 바인딩과 acquisition evidence를
보존하지만, flag=false에서는 자동 매도하지 않고 경고만 유지한다.

`TradingSettings`에는 `daily_minimum_order_enabled: bool = False`를 추가한다.
기존 설정 파일에 필드가 없으면 비활성화된다. 현재 사용자 배포에서만 별도 백업 후
`true`로 설정하며, 새 설치의 기본값은 계속 `false`다.

### 4.3 API Design

외부 HTTP API 변경은 없다. 내부 계약은 타입이 지정된 값 객체로 제한한다.

| Contract | Input | Output | Purpose |
|---|---|---|---|
| `DailyMinimumPolicy.evaluate` | 시장 세션, 안전 상태, 일일 후보 순위, 계좌, 포지션, 소유 상태 | `NoAction | BuyOne | SellOne` | 부작용 없는 결정 |
| `TradingSessionStore.claim_daily_evaluation` | 시장일, 정책/account binding | typed claim result | 0건 확인+`EVALUATED_PREFLIGHT` 원자화 |
| `TradingSessionStore.reserve_daily_post` | claim token, typed intent, safety limits | typed pre-reserved token | 0건 재확인+safety reservation+post-start 원자화 |
| `TradingSessionStore.mark_daily_order_known` | pre-reserved token, exact order | typed state | exact ID 원자 저장 |
| `DailyMinimumExecutor.execute` | 결정, 기존 guarded submission entry point, clock | typed execution result | 기존 승인·claim·lease를 통한 POST 최대 1회 |
| `DailyMinimumReconciler.reconcile` | known state, 최신 주문·포지션 GET | typed reconciled state | 소유권/완료 확인 |
| `DailyMinimumAdmin.resolve` | current binding, typed evidence digest, operator confirmation | resolved state | manual terminal 해제/수동 인계 감사 |

대표 typed 흐름은 다음과 같다. 구현 타입명은 달라도 필드 소유권과 결과 의미는 같아야 한다.

```text
claim_daily_evaluation(date=2026-08-11, account=HMAC-A, policy=P2)
  -> Granted(token=T1, state=EVALUATED_PREFLIGHT)
reserve_daily_post(token=T1, intent=BUY AAPL 1 @ 201.24 DAY,
                   max_buy=1, max_sell=1)
  -> Granted(pre_reserved=R1, state=POST_MAY_HAVE_STARTED)
mark_daily_order_known(R1, order_id=exact-private-id, submitted_date=2026-08-11)
  -> ORDER_KNOWN
reconcile(exact fill=1, remaining=0, baseline=0, total=1)
  -> COMPLETED_FILLED + OwnedLot(AAPL, acquisition_order_digest=HMAC-O)
```

blocked 결과는 예외 문자열이 아니라 `Denied(reason=<stable code>, terminal=<bool>)`이고,
token은 account/policy/date/side/intent digest에 묶여 재사용·교차계좌 소비할 수 없다.

가격 oracle 예시는 다음과 같다.

| Input (`pbid1`, `pask1`, elapsed, max spread) | Side | Exact result |
|---|---|---|
| `201.231`, `201.239`, `0.4s`, `50bps` | BUY | limit `201.24` |
| `201.231`, `201.239`, `0.4s`, `50bps` | SELL | limit `201.23` |
| `0.12345`, `0.12346`, `0.4s`, `50bps` | BUY | limit `0.1235` |
| `0.12345`, `0.12346`, `0.4s`, `50bps` | SELL | limit `0.1234` |
| `100`, `101`, `0.4s`, `50bps` | either | `daily_minimum_quote_spread_exceeded`, next candidate |
| valid bid/ask, `5.000001s`, any | either | `daily_minimum_quote_stale`, evaluation blocked |

최소주문 executor는 raw broker를 직접 받지 않는다. 현재 자동 cycle이 이미 시작한
`AutomaticOrderGuard`와 완전한 `AutomaticOrderContext`를 재사용하고, 승인 attempt를
추가 소비하지 않는다. 기존 `_submit_or_block_order`를 typed pre-reserved token을 받도록
확장하여 begin/confirm/finish, 최종 승인 재검사, signal claim, audit, KIS
`broker_submission_guard`를 그대로 거친다. daily claim에서 이미 잡은 safety reservation은
이 token이 정확히 한 번 소비하며 두 번째로 증가시키지 않는다. daily evaluation claim
자체는 정상 `reserve_safety`를 차단하지 않는다. preflight 도중 정상 reservation이 생기면
`reserve_daily_post`의 0건 재확인에서 minimum만 `daily_minimum_prior_order_detected`로
끝난다. 이를 우회하는 별도 POST 표면은 금지한다. 일일 신호 key는
`daily_minimum:<market_date>:<policy_digest>`로 안정적으로 바인딩한다.

임계값 전 후보는 공개 `SelectionReport`에 추가하지 않고 내부
`AutomaticSelectionResult.prethreshold_ranked` typed tuple로만 보존한다. 각 항목은
symbol, score, aware signal timestamp와 계산 기준 가격을 포함한다. 기능 false에서는
이 내부 데이터가 주문 경로에 관여하지 않으며 기존 공개 report serialization은 변하지 않는다.

최소주문은 account-wide broker lease를 fresh preflight 시작 전에 획득하여 POST가
끝날 때까지 유지한다. 이 구간에 저장된 canary state, 모든 open order, 제출 시장일의
paginated order history, positions, best quote를 bounded GET deadline으로 확인한다.
페이지 누락·deadline·미식별 open order·카나리 known/manual 상태는 fail closed다.
수동 주문이 preflight 이후 별도 채널에서 동시에 들어오는 것은 프로그램이 원자적으로
막을 수 없는 외부 위험이므로, 최소주문 감사 이벤트에 preflight cutoff를 남기고 운영자
수동 주문과 자동운영의 동시 사용을 금지하는 운영 계약을 둔다.

잠금 순서는 `broker lease -> TradingSessionStore lock`이다. store lock 안에서는 브로커
I/O, 감사 I/O, sleep을 하지 않는다. 정상 경로의 store lock은 broker lease 획득 전에
항상 해제되므로 역순 nested lock을 만들지 않는다.

소유권 방정식은 정수 share quantity로 계산한다. BUY 직전 `baseline=0`이어야 하며,
exact acquisition order가 `filled_qty=1`, `remaining_qty=0`이고 최신 position total이
`baseline + 1 = 1`이어야 한다. acquisition 시각부터 대사 cutoff까지 같은 symbol의
다른 order ID, transfer 또는 corporate-action evidence가 하나라도 있거나 history가
완전함을 증명하지 못하면 owned lot을 만들지 않고 manual terminal로 간다. SELL 전에도
동일 구간을 재검사하고 `latest_total=1`일 때만 주문한다. exact sell order가
`filled_qty=1`, `remaining_qty=0`, 최신 total이 `baseline=0`일 때만 owned lot을 제거한다.
KIS adapter는 explicit terminal reject/cancel/expire와 filled/remaining quantity를 typed
status로 정규화한다. exact zero-fill terminal을 증명할 수 없으면 주문 부재만으로
`COMPLETED_NO_FILL`을 추정하지 않고 manual terminal로 둔다.

KIS가 제공하는 현재 범위에는 이체/기업행동의 완전한 원장이 없으므로 “외부 변동 0”은
order history/open orders/positions에서 관측 가능한 모순이 없다는 뜻으로 제한한다.
자동 소유분이 있는 동안 해당 계좌·symbol을 앱 외부에서 거래·이체하지 않는다는
`exclusive_owned_symbol` 운영 동의를 feature 활성 시 policy digest와 감사 로그에 포함한다.
관측 불가능한 동일순량 대체 가능성은 잔여 위험으로 명시하며, 이 동의를 하지 않으면
자동 SELL을 사용하지 않고 `daily_minimum_exclusive_ownership_not_accepted`로 차단한다.

typed admin resolution은 원시 응답 대신 account binding, exact order ID의 keyed digest,
관측된 open-order count, position quantity, evidence cutoff, 운영자 확인 시각과 사유를
저장한다. `RESOLVED_NO_EXPOSURE`는 open order 0·관련 position 0을 운영자가 확인했을 때,
`HANDOFF_CONFIRMED`는 남은 position을 자동 소유에서 수동 소유로 인계했을 때만 허용한다.
둘 다 기존 불명확 주문이 실제 없었다는 자동 추론이 아니라 운영자 책임의 감사
checkpoint이며, 원시 계좌/주문 응답은 저장하지 않는다.
admin resolution이나 voluntary handoff는 남아 있는 실거래 승인을 즉시 무효화하며
다음 자동 POST 전에 대상 NASDAQ 시장일 승인을 새로 요구한다.

### 4.4 Key Technical Decisions

| Decision | Options Considered | Chosen | Rationale |
|---|---|---|---|
| 성공 정의 | 체결 보장 / 주문 제출 / 안전한 시도 | 안전 게이트를 통과한 POST 최대 1회 | 체결은 브로커·시장 상태 때문에 보장 불가 |
| 평가 시각 | 개장 직후 / 장중 고정 / 마감 60분 전 | 마감 60분 전 이후 첫 사이클 | 기존 전략에 먼저 기회를 주고 장마감 매수금지보다 충분히 앞섬 |
| 매도 대상 | 모든 보유 / 선택 종목 / 프로그램 소유분 | 정확히 대사된 프로그램 소유 1주 | 수동 자산 처분 방지 |
| 매수 대상 | 수동 티커 / 유니버스 첫 종목 / 승인 전략의 임계값 전 순위 | LIVE 승인 전략의 임계값 전 최상위 적격 신호 | `no_trade` 날에도 기능 목적을 달성하면서 전략·유니버스 승인 경계 유지 |
| 주문 종류 | 시장가 / 지정가 / 적응형 재호가 | 최신 가격 1주 지정가 DAY 1회 | 가격 상한을 유지하고 재제출 위험 제거 |
| POST 복구 | 낙관적 재시도 / 결과 추정 / fail closed | 의도 선저장 + 정확한 주문번호 대사 | 중복 주문 방지 |
| 기능 활성화 | 전역 기본 활성 / CLI 플래그 / 저장 설정 | 기본 false 저장 설정 | 명시적 운영자 동의와 롤백 용이성 |
| 실거래 승인 | 자동 갱신 / 장기 승인 / 시장일 승인 | 명시적 시장일 승인 + 실제 주문 시도 최대 12회 | 장중 보호주문 중단을 피하면서 다음 날 재승인과 노출 상한 유지 |
| 브로커 범위 | KIS+Alpaca / KIS 우선 | KIS LIVE만 | 현재 운영 표면과 지정가·대사 계약에 집중 |
| 상태 원자성 | 별도 JSON / 기존 세션 store 확장 | `TradingSessionStore` schema 2 | 정상 전략 reservation과 TOCTOU 없이 조정 |
| 결과 불명 복구 | 주문검색 후 재시도 / 운영자 대사 | 영구 manual terminal | ID 없는 POST 중복 가능성을 0으로 유지 |

## 5. Edge Cases & Error Handling

| # | Scenario | Expected Behavior | Severity |
|---|---|---|---|
| E1 | 휴장 또는 정규장 밖 | 주문 0, 다음 거래일로 주문 이월 없음 | P0 |
| E2 | 장 마감 60분 전 이후 앱 시작 | `[close-60m, min(buy-stop, close))` 안의 첫 사이클에서 1회 평가 | P1 |
| E3 | 마감 전 평가 구간 전체를 놓침 | 해당 거래일 최소 주문 없음 | P1 |
| E4 | 당일 기존 주문 안전 예약 존재 | 기능 충족으로 간주, 최소 주문 없음 | P0 |
| E5 | LIVE 시장일 불일치 또는 시도 한도 소진 | typed authorization block, POST 0 | P0 |
| E6 | 승인 전략/유니버스/데이터 차단 | 안정적 차단 사유, POST 0 | P0 |
| E7 | 후보 없음 | `daily_minimum_candidate_unavailable`, POST 0 | P1 |
| E8 | 현금·구매력 부족 | 기존 현금 게이트 사유, POST 0 | P0 |
| E9 | 일일 손실 또는 노출 한도 도달 | 기존 위험 게이트 사유, POST 0 | P0 |
| E10 | 카나리 broker lease 활성 | `broker_live_owner_active`, 재시도 없음 | P0 |
| E11 | POST 타임아웃/연결 종료 | 수동대사 상태, 같은 날과 재시작 후 POST 0 | P0 |
| E12 | 응답에 정확한 KIS 주문번호 없음 | 수동대사 상태, 원시 응답 저장 금지 | P0 |
| E13 | 주문 명시 거절 | 시도 소비, 감사 기록, 자동 재제출 없음 | P0 |
| E14 | 매수 접수 후 미체결 | known order GET 대사, 추가 주문 금지 | P0 |
| E15 | 매수 체결량이 정확히 1주가 아님 | 소유권 불일치, 수동대사 상태 | P0 |
| E16 | 외부에서 같은 종목 수량 변경 | 소유권 불일치, 강제 매도 금지 | P0 |
| E17 | 상태 파일 손상/시장일 역행 | fail closed, POST 0 | P0 |
| E18 | 두 프로세스 동시 평가 | 파일 잠금·일일 claim으로 POST 최대 1회 | P0 |
| E19 | 상태 저장 실패 | POST 전 차단 | P0 |
| E20 | 감사 로그 저장 실패 | POST 전 차단 | P0 |
| E21 | request bytes 전송 후 응답 전 종료 | `POST_MAY_HAVE_STARTED`에서 manual terminal, 모든 날짜 POST 0 | P0 |
| E22 | exact DAY 주문이 fill=0으로 terminal 만료/취소 | `COMPLETED_NO_FILL`, 다음 시장일 새 평가 허용 | P1 |
| E23 | 매수 부분체결 또는 외부 체결/이체/분할 | manual terminal, 프로그램 소유로 확정하거나 매도하지 않음 | P0 |
| E24 | 계좌 전환 또는 정책 flag/digest 변경 | 기존 승인/상태 해석 차단, POST 0 | P0 |
| E25 | 미식별 KIS open order 또는 카나리 known/manual state | broker lease 안 preflight에서 차단, POST 0 | P0 |
| E26 | 평가 claim 뒤 preflight 중 종료 | 재시작 시 evaluated-blocked, daily 재평가 0, 정상 보호주문 허용 | P0 |
| E27 | unresolved daily state의 시장일 변경 | reconciler가 정상 전략보다 먼저 실행, 모든 자동 POST 0 | P0 |
| E28 | owned symbol 외부조작 전용운영 동의 없음 | 자동 SELL 0, 지속 경고 | P0 |

## 6. Security & Permissions

### 6.1 Authentication

- 기존 KIS 자격 증명과 `NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES` 환경 잠금을 그대로 사용한다.
- `PRD-session-scoped-live-authorization.md`의 현재 시장일
  `LiveAuthorizationEnvelope`가 유효해야 한다.
- 승인은 자동 갱신하지 않으며, 대상 시장일 불일치·실주문 시도 한도 소진·binding
  변경이면 주문하지 않는다. 마감 60분 전은 최소주문 평가 창이지 승인 수명이 아니다.
- `LiveAuthorizationEnvelope`와 `AutomaticOrderContext`에 versioned
  `daily_minimum_policy_digest`와 enabled 상태를 포함한다. false에서 true로 바뀌면
  이전 승인은 즉시 binding mismatch가 되며 운영자의 신규 승인이 필요하다.
- 현재 cycle에서 이미 검증·소비한 승인 permit만 재사용하고 최소주문용 두 번째 승인 attempt를
  만들지 않는다. POST 직전 기존 guard의 최종 승인 검사를 다시 통과해야 한다.
- `LiveAuthorizationStore`의 현재 session schema는
  `daily_minimum_policy_digest`와 enabled binding을 저장한다. 과거 minute/cycle schema 1은
  feature 설정과 무관하게 자동 승격하지 않고 명시 재승인을 요구한다. future schema는
  fail closed다.

### 6.2 Authorization

| Role | Create | Read | Update | Delete |
|---|---|---|---|---|
| 현재 Windows 사용자 앱 | 의도/상태 | 자체 상태·비밀 제외 감사 | 대사 상태 | 임의 삭제 금지 |
| 예약 감시 작업 | 없음 | 프로세스 상태 | 없음 | 없음 |
| 운영자 | 설정 활성/비활성 | GUI·감사·상태 요약 | 명시적 재승인 | 롤백 절차로만 |
| 테스트/진단 | fixture만 | fixture만 | fixture만 | fixture만 |

### 6.3 Data Protection

- 상태에는 계좌번호 대신 설치별 DPAPI-protected key로 만든 HMAC 계좌 바인딩만 저장한다.
- API 키, 비밀키, 토큰, 원시 POST 응답, 원시 잔고 응답을 저장하지 않는다.
- 상태 파일은 임시 파일 flush/fsync 후 원자 교체한다.
- 앱 데이터 디렉터리의 현재 사용자/SYSTEM ACL을 유지한다.
- 감사 로그는 날짜, 종목, 방향, 수량, 지정가, 상태, 사유 코드, 경과시간만 허용한다.

## 7. Performance & Monitoring

| Metric | Target | Measurement |
|---|---|---|
| 정책 평가 p95 | 10 ms 이하 목표 | 별도 benchmark/감사 elapsed field, correctness 단위 테스트의 wall-clock assertion 금지 |
| 추가 브로커 GET | 평가 1회당 필요한 최신 가격·계좌·포지션과 대사 조회만 | fake broker call ledger |
| 최소 주문 POST | 시장일당 최대 1회 | 감사 로그 + durable state |
| 중복 POST | 0 | 재시작/동시성 통합 테스트 |
| 원시 비밀정보 로그 | 0 | package/audit sensitive scan |

### 7.1 Monitoring & Alerting

- `daily_minimum_evaluated`: 평가 시각, 시장일, 기존 주문 수, 결정 사유.
- `daily_minimum_intent`: 종목, 방향, 수량 1, 지정가, 시장일.
- `daily_minimum_submitted`: exact 주문 ID의 domain-separated keyed HMAC display token만,
  원시/정규화 주문번호와 원시 응답 제외.
- `daily_minimum_blocked`: 안정적 사유 코드와 terminal 여부.
- `daily_minimum_reconciled`: owned/completed/manual 상태 전이.
- `MANUAL_RECONCILIATION_REQUIRED`는 GUI의 지속적 고우선순위 상태로 표시한다.
- 경고 acknowledgement는 운영자가 보았다는 감사 이벤트만 남기며 terminal 상태나
  POST 차단을 해제하지 않는다. 해제는 별도 수동대사 절차와 exact broker evidence가 필요하다.

## 8. Testing Strategy

### 8.1 Unit Tests

- aware clock과 NASDAQ calendar를 주입하고 시작/종료 경계 각각 1us 전·정각·1us 후를
  검증한다. 2026-06-26 여름장, 2026-01-05 겨울장, 2026-11-27 13:00 ET 조기폐장,
  DST 전후, host timezone 독립, naive datetime 거부, 시계 역행/도약, 종료 후 앱 시작을 포함한다.
- 당일 주문 수 0/1과 기능 on/off.
- 소유 1주 매도 우선과 소유 불일치 차단.
- 승인 전략의 임계값 전 내부 후보 순서, 동점 정렬, top 후보 포지션 차단 후 다음 후보,
  현금 exact-cent 경계, stale/NaN/zero quote, sub-$1 tick 정규화, 후보 순서를 검증한다.
- 상태 codec의 모든 모드와 불법 조합 거부.
- 시장일 역행, future schema, naive timestamp, 수량 0/2, 원시 비밀 필드 거부.
- account HMAC의 설치별 salt/key 차이, DPAPI roundtrip, constant-time binding mismatch를 검증한다.
- 최소주문 정책 flag/digest 변경 시 기존 실거래 승인이 무효화되는지 검증한다.
- spread 공식의 threshold 1ulp 아래/정각/위, 설정 기본값·범위와 변경 시 승인 무효화를 검증한다.

### 8.2 Integration Tests

- 기존 전략 주문이 있으면 fallback broker POST 0.
- 진입 임계값 미달 `no_trade` + 유효 승인 + 임계값 전 적격 후보에서
  KIS 1주 지정가 POST 1.
- barrier가 있는 독립 store/process로 daily-vs-daily, normal-buy-vs-daily-buy,
  normal-sell-vs-daily, canary lease 경합을 검증한다. 생산 broker ledger의 총 POST는 1 이하이고
  deadlock/lock inversion이 없어야 한다.
- evaluation claim 후 즉시 종료, final authorization/lease/각 fresh GET/quote/audit 실패에서
  disk reopen 시 합법적인 `EVALUATED_BLOCKED`, 같은 날 daily 평가 0, 정상 보호 SELL 허용,
  broker POST 0, safety count 이중 증가 0을 검증한다.
- 당일 0건 확인+daily claim+safety reservation과 intent/post-start 저장이 POST보다 먼저
  발생함을 순서 ledger로 검증한다. pre-reserved daily token은 기존 guard가 한 번만 소비하고
  safety count를 이중 증가시키지 않는다.
- POST 타임아웃, 응답 주문번호 누락, 명시 거절 각각 재시도 0.
- 매수 exact ID `FILLED`, filled_qty=1, baseline=0, total=1, open remainder=0일 때만
  정확한 1주 소유 상태로 전이한다. 각 조건 불일치와 외부 buy/sell interleaving은 POST 0/manual이다.
- 다음 거래일 매도 전 total=1을 재검사하고, exact sell `FILLED`, filled_qty=1,
  total=0일 때만 완료한다.
- Friday buy -> weekend -> Monday에서 owned lot은 보존되고 daily attempt만 reset된다.
- exact ID DAY 주문이 fill=0 terminal인 경우 `COMPLETED_NO_FILL`; absent/partial/contradiction은 manual이다.
- 재시작·두 프로세스 경합에서 POST 최대 1.
- 카나리 lease, 카나리 known/manual state, lease 해제 뒤 남은 unmatched open order가 있으면 POST 0.
- 기능 off일 때 기존 자동선택/no-trade fixture 결과 불변.
- 기능 true로 바뀌었지만 이전 승인을 재사용한 경우 `live_authorization_binding_changed`, POST 0.
- 과거 minute/cycle authorization schema 1과 future schema는 자동 승격하지 않고
  재승인 전 POST 0을 유지한다.
- 계좌 A의 owned state를 계좌 B에서 load하면 `daily_minimum_account_binding_changed`, GET 해석/POST 0.
- PMHS/ORDER_KNOWN/manual state는 다음 시장일에도 정상 자동주문을 전역 차단하고 reconciler가
  먼저 실행된다. `EVALUATED_BLOCKED` 뒤 정상 보호 SELL과 owned가 없는 다른 symbol 정상주문은 허용한다.
- 두 프로세스의 동시 schema-1 migration이 모든 ClaimStatus/count를 보존하고 단일 schema-2를
  만드는지, feature=false에서도 unresolved global gate가 유지되는지 검증한다.
- owned symbol의 정상 BUY와 수량증가 주문은 차단하고 다른 symbol은 허용한다. owned symbol의
  guarded risk-reducing SELL은 장중 어느 시각에도 허용하며 exact fill이면 owned 제거,
  timeout/partial이면 global manual terminal인지 검증한다.
- quote 표의 각 input이 exact Decimal limit/reason을 만들고 transport timeout은 다음 후보로
  넘어가지 않는지 검증한다.

### 8.3 Edge Case Tests

- 휴장, 조기 폐장, DST 전환, 마감 평가 구간 누락.
- 실거래 승인 만료, 계좌 조회 실패, 가격 비정상, 현금 부족.
- 수동 보유와 동일 종목 충돌, 외부 수량 변경, 미체결 잔존.
- 상태/감사 쓰기 실패와 파일 잠금 타임아웃.
- fault injection은 claim 전/후, intent fsync 후, audit 후, request bytes 전송 후,
  exact ID 수신 후 state 저장 전, ORDER_KNOWN 저장 후 audit 전, reconciliation GET 후
  state 저장 전 각각 프로세스를 종료하고 disk reopen 후 추가 POST 0, 올바른 terminal 상태,
  idempotent audit, orphan `.tmp`/lock 0을 검증한다.
- frozen EXE 자동 QA는 KIS credential/LIVE env를 모두 제거하고 임시 LOCALAPPDATA를 사용한다.
  feature-on diagnostic coordinator를 any network/POST에서 즉시 실패하는 sentinel transport로
  실제 실행하며, 외부 call ledger가 GET/POST 0임을 증명한다. payload의 자체 보고 boolean만
  증거로 사용하지 않는다.
- PyInstaller onedir에 신규 모듈·설정 기본값 포함.

## 9. Rollout Plan

### 9.1 Migration Strategy

1. `TradingSettings`에 기본값 false 필드를 추가한다. 기존 JSON은 자동으로 false를 사용한다.
2. canonical `runtime\trading_session.json`의 `TradingSessionStore` schema 1을 기존
   count/claim을 보존하는 schema 2로 원자 migration한다. daily state, safety count, signal
   claim은 이 파일과 `trading_session.json.lock`만 사용함을 package/migration test로 확인한다.
3. 과거 minute/cycle `LiveAuthorizationStore` schema 1은 자동 migration하지 않고
   `live_authorization_reapproval_required`로 차단한다.
4. 소스·단위·통합 테스트는 fake broker로만 수행한다.
5. 별도 PyInstaller onedir staging을 빌드하고 package audit 및 frozen diagnostic을 실행한다.
6. staged/deployed `trading_config.json`은 자동·frozen QA 동안 반드시 false임을 검사한다.
7. 기존 앱/작업을 정지하고 전체 onedir를 원자적으로 교체한 뒤 작업을 재등록한다.
8. 첫 QA는 LIVE 자격 증명을 로드하지 않는 fixture/dry-run 표면에서 수행한다.
9. 실제 LIVE 활성은 사용자에게 최종 배포 승인을 다시 받은 뒤에만 `true`로 변경하고,
   변경된 policy digest로 대상 NASDAQ 시장일 실거래 승인을 새로 받아야 한다.

### 9.2 Feature Flag

- `daily_minimum_order_enabled`, 기본 `false`.
- false에서는 신규 평가·의도·POST를 만들지 않는다. 단, 기존 `ORDER_KNOWN`, owned lot,
  manual terminal의 안전 GET 대사와 GUI 고우선 경고는 계속 수행한다.
- 현재 사용자 설정만 명시적으로 true로 변경한다.

### 9.3 Rollback Plan

- 설정을 false로 바꾸고 앱을 재시작하면 신규 최소 주문 평가를 즉시 중단한다.
- 롤백 시 session state나 DPAPI account-binding key를 삭제·복원하지 않는다.
- 알려진 주문 또는 소유 1주가 남아 있으면 자동으로 상태를 지우거나 수동 보유로
  간주하지 않고 운영자에게 인계한다.
- 기본 rollback은 새 바이너리를 유지하고 flag=false로 바꾸는 것뿐이다. schema 2 migration
  뒤 구버전 바이너리를 파일만 교체하는 rollback은 지원하지 않는다.
- 구버전 복구가 불가피하면 정지된 프로세스에서만 `daily-minimum rollback-session-v1` 관리
  명령을 실행한다. 이 명령은 canonical store lock 획득, exact known/open order 0,
  owned lot 0 또는 typed `HANDOFF_CONFIRMED`, manual terminal 해제 checkpoint를 검증하고,
  schema 2 원본을 timestamp archive로 보존한 뒤 safety count와 claims만 schema 1로 원자
  projection한다. schema-2 LiveAuthorizationStore도 해당 store lock 아래 archive 후 제거해
  구버전에서 fresh 승인을 요구한다. 실제 구버전 parser가 session projection을 load하고
  기존 auth를 재사용하지 않는 compatibility test를 통과해야 한다.
- 위 조건을 하나라도 증명하지 못하면 구버전 복구는 차단하고 새 바이너리 flag=false에서
  대사·경고를 계속한다.

## 10. Dependencies & Risks

### 10.1 Dependencies

| Dependency | Owner | Status | Risk if Delayed |
|---|---|---|---|
| LIVE `CHAMPION` 전략, 임계값 전 신호 순위와 최신 유니버스 | AI Quant artifacts | `AutomaticSelectionResult` 내부 typed tuple 확장 | 후보 없음으로 주문 0 |
| 시장일/실주문 시도 한도 승인 | Operator | Existing gate | 평가 시 승인 불일치·한도 소진으로 주문 0 |
| KIS 가격·계좌·포지션·주문 GET/POST | KIS broker adapter | Existing | 조회/주문 차단 |
| TradingSessionStore 일일 안전 예약 | Core engine | schema 2 + atomic daily claim 필요 | 중복/한도 보장 불가 |
| broker live-owner lease | Canary/KIS client | Existing | 동시 주문 차단 |
| Windows 앱 데이터 ACL | Deployment | Existing | 상태 저장 차단 |

### 10.2 Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| 신호 없는 매수가 손실 발생 | High | High | 1주, 기존 현금·노출·손실 한도, 지정가, 기본 false |
| 사용자 보유분 오매도 | Medium | Critical | baseline 0 + exact app fill + observable contradiction 검사 + 전용운영 동의 |
| POST 타임아웃 후 중복 주문 | Medium | Critical | 의도 선저장, 결과 불명 terminal, 자동 재시도 0 |
| 승인 시장일 불일치·시도 한도로 일일 주문 미실행 | Medium | Medium | GUI에 명확한 사유 표시; 자동 승인 갱신 금지 |
| 마감 임박 지정가 미체결 | Medium | Medium | 시도로만 정의, 재호가/시장가 전환 금지 |
| 기존 no-fallback 계약 회귀 | Medium | High | 기능 off 회귀 테스트와 opt-in 분기 격리 |
| session state 손상 | Low | High | strict codec, 원자 저장, fail closed |
| canary와 main engine 경합 | Medium | High | lease 안 fresh order preflight, canary known/manual 차단 |
| feature flag 활성 전 승인 재사용 | Medium | Critical | policy digest를 승인 envelope에 바인딩, 재승인 강제 |
| 계좌 전환 후 owned state 오해석 | Low | Critical | DPAPI-keyed account HMAC exact match, mismatch terminal |
| 외부 이체/기업행동 원장 부재 | Low | Critical | 한계 명시, owned symbol 외부조작 금지 동의, 관측 모순 fail closed |

## 11. Success Metrics

| Metric | Baseline | Target | Measurement Method |
|---|---|---|---|
| 기능 on + 안전조건 충족 + 당일 기존 주문 0인 날의 최소 주문 시도율 | 0% | 100% | 감사 이벤트/시장일 집계 |
| 거래일당 최소 주문 POST 상한 | N/A | 1 | durable state + audit |
| 중복 POST | 0 | 0 | 주문 ID/claim 감사 |
| 수동 보유분 강제 매도 | 0 | 0 | ownership reconciliation tests/audit |
| 결과 불명 이후 추가 POST | 0 | 0 | fault-injection integration tests |
| 기능 off 회귀 | 기존 동작 | 변화 0 | golden/contract tests |

## 12. Open Questions

없음. 다음 정책은 사용자 승인으로 확정했다.

- 체결이 아니라 안전한 1주 주문 시도를 목표로 한다.
- 장 마감 60분 전까지 기존 주문이 없을 때 한 번 평가한다.
- 검증된 프로그램 소유 1주 매도, 없으면 승인 전략의 진입 임계값 적용 전
  최상위 적격 후보 1주 매수 순서다.
- 기존 안전 게이트와 시장일/실주문 시도 한도 실거래 승인을 우회하지 않는다.
