# PRD: 미국 정규장 자동 실거래와 일일 최소 안전 주문

**Version**: 0.2  
**Author**: Codex  
**Date**: 2026-08-12  
**Status**: In Review  
**Size**: XL

---

## 1. Problem Statement

### 1.1 Background

현재 운영본은 KIS 실계좌, LIVE 환경 잠금, 정규장 제한, 전략·유니버스·위험 설정
바인딩, 거래일별 최대 12회의 실제 주문 시도 승인, 중복 신호와 결과 불명 주문 차단을
갖는다. 다만 새 거래일에는 운영자가 `authorize-live-session`을 다시 실행해야 한다.

별도로 승인된 `PRD-daily-minimum-one-share-order.md`는 장 마감 전까지 기존 주문이
0건이면 프로그램 소유 1주를 매도하거나 적격 후보 1주를 매수하는 안전 폴백을
설계했지만 아직 구현되지 않았다. 그 문서는 매일의 명시적 실거래 승인을 전제로 한다.

운영자는 다음을 요구했다.

- 미국 정규장이 열리면 별도의 일일 승인 없이 자동 매수·매도가 가능할 것
- 현금, KIS 종목별 주문가능금액, 보유수량과 노출 한도를 고려해 종목을 선택할 것
- 정규장 개장 후 첫 적격 자동 사이클에서 매도 또는 매수 1주 실주문 POST를 실행할 것

2026-08-11 23:42 KST에는 익절 매도 경로가 `$1 이상` 가격을 세 자리 소수로 KIS에
전송해 `1$이상 소수점 2자리까지만 가능` 오류로 거절됐다. 일반 KIS 주문 serializer는
최대 네 자리까지 단순 출력하지만, 가격 band별 tick 정규화는 live-canary 매도에만
존재한다. 자동운영의 모든 주문 경로가 같은 broker-boundary 가격 규칙을 사용해야 한다.

### 1.2 Problem Definition

한 번 명시적으로 승인한 자동운영 정책이 현재 계좌·전략·유니버스·위험 설정과
동일한 동안, 각 NASDAQ 정규 거래일의 장중에 거래일 한정 실주문 permit을 자동
발급한다. 개장 후 첫 적격 자동 사이클에 당일 주문이 아직 없으면 잔고와 보유분을
반영한 1주 DAY 지정가 실주문 POST를 반드시 한 번 실행한다.

### 1.3 Impact of Not Solving

- 다음 거래일 승인 누락으로 익절·손절과 신규 진입 평가가 모두 중단될 수 있다.
- 최상위 후보가 비싸다는 이유만으로 더 저렴한 적격 후보를 평가하지 못할 수 있다.
- 신호가 없는 날에는 실제 주문 경로가 전혀 실행되지 않아 일일 운영 요구를 충족하지
  못한다.
- 거래일 경계가 없는 영구 자동 승인은 기존 감사·중복·대사 안전장치를 우회한다.

### 1.4 Normative Precedence

이 PRD는 다음 기존 계약의 충돌 항목만 대체한다.

| Existing document | Superseded contract | Replacement |
|---|---|---|
| `PRD-session-scoped-live-authorization.md` | 매 거래일마다 CLI로 신규 승인을 발급해야 함 | 사전 승인된 자동운영 정책이 일치하면 정규장 중 당일 permit 자동 발급 |
| `PRD-daily-minimum-one-share-order.md` NG8, AC-6.2 | 만료·신규 거래일 승인을 자동 갱신하지 않음 | 자동운영 정책이 유효한 경우에만 당일 permit 자동 발급 |
| `docs/tickets/daily-minimum-one-share-order/*` | 수동 session authorization 의존성 | 이 PRD 승인 뒤 새 티켓으로 대체하고 기존 티켓은 `Invalidated` 처리 |

기존 문서의 정규장 제한, 최대 실제 주문 시도 횟수, 위험 한도, exact-order 대사,
수동 보유분 보호, 비밀정보 금지와 fail-closed 규칙은 그대로 유지한다. 별도
`live-canary`의 제한시간 승인 정책은 변경하지 않는다.

## 2. Goals & Non-Goals

### 2.1 Goals

- [ ] G1: 승인된 자동운영 정책이 일치하는 모든 NASDAQ 정규 거래일에 장중 자동
  실거래 permit을 만들고, 장 마감과 함께 신규 주문 권한을 끝낸다.
- [ ] G2: 정상 전략 매수와 일일 최소 매수 모두에서 현금, KIS 종목별 주문가능금액,
  현재 포지션과 노출 한도를 반영하여 첫 번째 매수 가능한 후보를 선택한다.
- [ ] G3: 당일 기존 주문이 0건이면 정규장 개장 후 첫 적격 자동 사이클에서 프로그램
  소유 1주 매도 또는 적격 후보 1주 매수 실주문 POST를 정확히 한 번 실행한다.
- [ ] G4: 재시작, 동시 프로세스, 응답 유실과 시장일 전환에도 주문 POST를 중복하지
  않고 결과 불명 상태에서는 모든 신규 자동 POST를 차단한다.
- [ ] G5: 자동 permit 발급, 후보 제외, 일일 최소 주문과 미충족 사유를 비밀정보 없이
  GUI와 감사 로그에서 확인할 수 있게 한다.
- [ ] G6: 모든 KIS 해외주식 주문가격을 POST 전에 허용 tick으로 정규화해 가격 자릿수
  오류로 거절되는 주문을 0건으로 만든다.

### 2.2 Non-Goals

- NG1: 휴장, 장외시간, 현금 부족, 손실·노출 한도, 잘못된 시세, 브로커 거절이나
  결과 불명 주문을 우회해 주문하지 않는다.
- NG2: 체결을 보장하지 않는다. 보장 대상은 모든 물리적·안전 전제조건을 통과한 날의
  단 한 번인 최소 1주 KIS production POST다.
- NG3: 수동 보유분이나 소유권이 불명확한 주식을 최소주문 명목으로 매도하지 않는다.
- NG4: 시장가, 장외주문, 분할주문, 자동 재제출, 차입·마진 주문을 도입하지 않는다.
- NG5: 전략 점수, 익절·손절·trailing·time exit 규칙이나 최대 일일 주문 한도를
  약화하지 않는다.
- NG6: 정책 또는 계좌 바인딩 변경을 자동 승인하지 않는다. 운영자가 자동운영 정책을
  다시 명시 승인해야 한다.
- NG7: 앱이 종료되어 있었던 거래일의 주문을 다음 날 보충하지 않는다.
- NG8: KIS 이외 브로커의 LIVE 일일 최소주문을 이번 버전에서 지원하지 않는다.
- NG9: 별도 bounded live canary의 `expires_at`과 수동 승인 규칙을 변경하지 않는다.
- NG10: 현금과 주문가능금액이 모두 1주 가격보다 작고 프로그램 소유 매도분도 없거나,
  브로커 장애·미확정 주문·규제 차단이 있는 날에 주문을 조작하거나 위험 게이트를
  우회하지 않는다.

## 3. User Stories & Acceptance Criteria

### US-1: 정규장 자동 실거래 permit

**As a** 무인 실거래 운영자, **I want** 승인된 정책으로 매 거래일 장중 주문 권한이
자동 준비되기를 원하고, **so that** 다음 날 승인 누락으로 주문 평가가 멈추지 않는다.

**Acceptance Criteria:**

- [ ] AC-1.1: `automatic_session_authorization_enabled=true`이고 자동운영 정책의 계좌,
  broker route, mode, 전략, 유니버스, 위험 설정과 일일 최소주문 digest가 현재 값과
  정확히 일치할 때만 NASDAQ 정규장 `open <= now < close`에서 당일 permit을 자동
  발급한다.
- [ ] AC-1.2: permit은 기존 `LiveAuthorizationEnvelope`와 동일하게 정확한
  `market_date`, 암호학적 난수 `authorization_id`, `max_attempts=12`, 현재 정책
  digest를 가지며 실제 주문 `begin`에서만 attempt를 하나 소비한다.
- [ ] AC-1.3: 같은 거래일·같은 정책의 permit이 있으면 재시작이나 매 사이클에서
  새 permit을 만들지 않고 원자적으로 재사용한다.
- [ ] AC-1.4: premarket, after-hours, 휴장일, market calendar 오류, naive datetime이면
  permit을 발급하지 않고 기존 permit으로 POST하지 않는다.
- [ ] AC-1.5: 현재 거래일이 바뀌면 이전 permit은 POST에 사용할 수 없다. 다음 정규장
  개장 후 정책이 일치할 때만 새 permit을 발급한다.
- [ ] AC-1.6: 기존 `revoke-live-session`과 신규 긴급정지는 현재 permit을 지우는 동시에
  자동운영 정책을 `SUSPENDED`로 만든다. 재시작해도 자동 재발급하지 않으며 명시적
  재개 명령이 필요하다.
- [ ] AC-1.7: 설정·전략·유니버스·위험·broker/account digest가 달라지면
  `auto_live_policy_binding_changed`로 차단하고 새 값을 자동 승인하지 않는다.
- [ ] AC-1.8: 자동 permit 생성 실패, 감사 로그 fsync 실패, store 잠금 실패는
  POST 0으로 종료하며 같은 사이클에서 수동 permit으로 폴백하지 않는다.

### US-2: 잔고 기반 매수 후보 선택

**As a** 계좌 소유자, **I want** 실제로 1주를 살 수 있는 후보를 선택하기를 원하고,
**so that** 비싼 최상위 종목 하나 때문에 주문 기회를 놓치지 않는다.

**Acceptance Criteria:**

- [ ] AC-2.1: 전략의 점수 내림차순·종목 오름차순 순위는 유지하되 매수 후보마다
  최신 계좌 현금, KIS `get_overseas_buying_power(symbol, limit_price)`, 최신 포지션,
  `max_position_qty`, 노출·손실 한도를 적용한다.
- [ ] AC-2.2: `required_cash=Decimal(limit_price) * 1`이며 `account.cash`와 종목별
  KIS 주문가능금액이 모두 `required_cash` 이상이어야 1주 매수 가능하다. NaN, 음수,
  통화 불일치와 조회 실패는 해당 평가를 fail closed한다.
- [ ] AC-2.3: 상위 후보가 가격·보유수량·노출 한도로 제외되면 같은 immutable ranking의
  다음 후보를 평가한다. 데이터 오류나 shared reconciliation deadline 초과는 다른
  후보로 숨기지 않고 전체 평가를 차단한다.
- [ ] AC-2.4: 정상 전략 매수와 일일 최소 매수는 동일한 balance-aware candidate planner와
  KIS POST 직전 현금·주문가능금액 재검사를 사용한다.
- [ ] AC-2.5: 매도 후보는 현금으로 제외하지 않지만, 최신 보유수량과 주문 수량,
  미결 주문, 소유권 조건이 일치해야 한다.
- [ ] AC-2.6: 후보 제외는 `insufficient_cash`, `insufficient_buying_power`,
  `position_limit_reached`, `exposure_limit_reached`, `account_state_unavailable` 중
  안정적인 reason으로 기록하며 계좌 금액 자체는 로그에 남기지 않는다.
- [ ] AC-2.7: 정상 전략, 익절·손절, sell monitor, AI, day trade, daily minimum과 canary를
  포함한 모든 KIS 해외주식 POST는 하나의 shared Decimal normalizer를 사용한다.
  가격 `>=1 USD`는 tick `0.01`, `<1 USD`는 tick `0.0001`이며 BUY는 ceiling, SELL은
  floor로 정규화한다. buying-power 조회, 안전 예약 intent, 감사 가격, POST body와
  exact-order 대사는 모두 같은 정규화 값을 사용하며 float 재계산으로 바꾸지 않는다.

### US-3: 일일 최소 1주 안전 주문

**As a** 무인 실거래 운영자, **I want** 정상 주문이 없는 거래일에도 한 번의 안전
주문을 원하고, **so that** 일일 최소 거래 활동을 자동 수행한다.

**Acceptance Criteria:**

- [ ] AC-3.1: `daily_minimum_order_enabled=true`이고 당일 KIS history와 canonical
  `TradingSessionStore`의 BUY+SELL 안전 예약 합계가 모두 0일 때만 일일 최소주문
  평가 대상이다.
- [ ] AC-3.2: 평가는 NASDAQ 달력의
  `open + configured market_open_wait_minutes <= now < close-stop` 첫 자동 사이클에서
  정확히 한 번 수행한다. `close-stop=max(configured market_close_stop_minutes, 5분)`이고
  앱이 장중 늦게 시작해도 close-stop 전이면 그 날의 첫 사이클에서 즉시 수행한다.
- [ ] AC-3.3: 프로그램이 exact app fill과 최신 포지션으로 소유권을 확인한 1주가 있으면
  SELL을 우선한다. 없으면 진입 임계값 적용 전 전략 ranking에서 첫 balance-aware 적격
  후보 1주 BUY를 선택한다.
- [ ] AC-3.4: SELL은 저장된 acquisition order, baseline 0, 현재 총수량 정확히 1,
  관측 가능한 외부 변동 없음, 미결 주문 0일 때만 허용한다. 수동 보유분과 수량이
  섞였으면 `daily_minimum_ownership_mismatch`로 차단한다.
- [ ] AC-3.5: BUY/SELL 모두 수량 1, USD, DAY limit만 사용한다. BUY는 최신 `pask1`,
  SELL은 최신 `pbid1`을 Decimal tick으로 정규화하며 quote age는 request elapsed 5초
  이하, spread는 `10_000*(ask-bid)/((ask+bid)/2) <= 50bps`여야 한다.
- [ ] AC-3.6: 당일 정상 주문 POST, daily production POST, 명시적 broker reject,
  알려진 주문은 같은 날 두 번째 daily POST를 만들지 않는다. POST 호출 직전의
  preflight 차단은 당일 평가를 소비하되 production POST 미충족으로 기록한다.
- [ ] AC-3.7: 현금·주문가능금액이 1주 가격보다 작고 프로그램 소유 매도분도 없거나,
  정규장이 닫혔거나, broker/account/quote 조회 실패, 미확정 주문, 손실·노출 한도가
  차단한 경우에만 POST 0을 허용한다. `daily_minimum_unmet`과 stable reason을 고우선순위
  경고로 기록하며 다음 날 주문으로 보충하지 않는다.
- [ ] AC-3.8: 위 예외가 없으면 전략 신호가 `no_trade`여도 임계값 전 ranking에서
  balance-aware 후보를 찾아 1주 BUY하거나 exact program-owned 1주를 SELL해 KIS
  production POST 호출 수가 정확히 1이 되도록 한다. dry-run·paper·canary POST는 이
  요구사항을 충족한 것으로 계산하지 않는다.

### US-4: 정확히 한 번과 결과 불명 차단

**As a** 계좌 소유자, **I want** 재시작과 네트워크 오류가 주문을 복제하지 않기를
원하고, **so that** 자동운영이 노출을 추측하지 않는다.

**Acceptance Criteria:**

- [ ] AC-4.1: `TradingSessionStore` schema 2의 같은 파일 잠금에서 일일 평가 claim과
  정상 전략 safety reservation을 조정한다. 별도 삭제 가능한 일일 상태 파일을 만들지
  않는다.
- [ ] AC-4.2: daily preflight 완료 후 POST 직전 같은 잠금에서 당일 주문 0건 재확인,
  safety reservation, typed intent, `POST_MAY_HAVE_STARTED=true`를 한 번의 fsync로
  저장한다.
- [ ] AC-4.3: 정확한 주문 ID를 받으면 `ORDER_KNOWN`으로 저장하고 제출 시장일을 포함한
  history에서 ID+symbol+side+qty+price를 exact match한다.
- [ ] AC-4.4: `POST_MAY_HAVE_STARTED`에서 ID 없이 종료되거나 partial/ambiguous/mismatch가
  발생하면 `MANUAL_RECONCILIATION_REQUIRED`로 고정하고 시장일·feature flag와 무관하게
  모든 자동 POST를 차단한다.
- [ ] AC-4.5: 정상 전략, 일일 최소주문, sell monitor, day trade, canary는 account-wide
  broker submission lease를 공유한다. daily coordinator는 lease 안에서 fresh open order,
  history, position GET을 완료한 뒤 POST한다.
- [ ] AC-4.6: 자동 permit 발급은 주문 reservation이나 POST가 아니며 broker lease를
  잡지 않는다. permit 발급과 주문 claim의 파일 잠금 순서는 서로 중첩하지 않는다.

### US-5: 운영자 제어와 가시성

**As a** 운영자, **I want** 자동 권한과 일일 주문 상태를 즉시 중지하고 확인하기를
원하고, **so that** 무인 운영을 안전하게 관리한다.

**Acceptance Criteria:**

- [ ] AC-5.1: CLI는 `authorize-auto-live-policy`, `suspend-auto-live-policy`,
  `resume-auto-live-policy`, `auto-live-policy-status`를 제공한다. authorize/resume은
  LIVE mode, KIS real environment, exact confirmation phrase와 현재 binding을 요구한다.
- [ ] AC-5.2: GUI는 자동 실거래 정책 상태(`ACTIVE`, `SUSPENDED`, `BINDING_CHANGED`)와
  당일 permit, attempt `used/12`, 일일 최소주문 상태를 표시한다.
- [ ] AC-5.3: 기존 자동운영 시작/중지 버튼은 사이클 실행만 제어한다. 긴급정지 동작은
  permit과 자동 정책을 함께 suspend하고, 사용자 확인 없이 재개하지 않는다.
- [ ] AC-5.4: 감사 로그는 `auto_live_policy_authorized`, `auto_live_policy_suspended`,
  `auto_live_policy_resumed`, `live_authorization_session_auto_approved`,
  `balance_candidate_excluded`, `daily_minimum_evaluated`, `daily_minimum_intent`,
  `daily_minimum_submitted`, `daily_minimum_blocked`, `daily_minimum_reconciled`를 기록한다.
- [ ] AC-5.5: 로그·상태·GUI에는 계좌번호, 앱키, 토큰, 원시 broker response, 현금·자산의
  실제 금액을 기록하지 않는다.

## 4. Technical Design

### 4.1 Architecture Overview

```text
GUI unattended tick
  -> AutoLivePolicyService.ensure_session(now)
       -> regular market calendar check
       -> persistent policy ACTIVE + binding exact match
       -> existing LiveAuthorizationStore current-day permit load-or-create
       -> audit fsync before permit store activation
  -> DailyStateReconciler (unresolved state globally blocks POST)
  -> existing automatic selection ranking
  -> BalanceAwareCandidatePlanner
       -> account cash + position + risk/exposure
       -> KIS symbol-specific buying power
       -> first affordable eligible candidate
  -> existing strategy order path
  -> no production order today + first eligible regular-session cycle
       -> DailyMinimumCoordinator
       -> owned exact 1-share SELL, else prethreshold affordable BUY
  -> AutomaticOrderGuard begin/confirm/finish
  -> shared KIS Decimal price normalization
  -> account-wide broker lease + KIS POST/reconciliation
```

자동 permit 서비스는 broker client를 생성하거나 네트워크를 호출하지 않는다. 현재
설정에서 이미 계산 가능한 versioned digest와 시장 달력, 로컬 원자 store만 사용한다.
계좌 바인딩 원문은 기존 `broker_authorization_digest(config)`만 사용한다.

정상 전략 selection의 공개 순위와 점수는 바꾸지 않는다. 잔고 계획은 ranking 이후,
주문 결정 이전의 내부 단계이며 어떤 후보가 주문 가능했는지만 안정적인 reason으로
기록한다. SELL exit는 BUY affordability filtering과 무관하게 계속 평가한다.

### 4.2 Data Model Changes

#### Automatic live policy store

`%LOCALAPPDATA%\NasdaqAutoTrader\runtime\automatic_live_policy.json`을 별도 원자 store로
만든다. 이 파일은 장기 운영 동의이며 주문 상태가 아니다. 비밀정보 원문을 저장하지
않는다.

| Field | Type | Invariant |
|---|---|---|
| `schema_version` | int | 정확히 1, unknown future schema fail closed |
| `status` | enum | `ACTIVE` 또는 `SUSPENDED` |
| `authorization_id` | CSPRNG string | authorize 때마다 새 값 |
| `approved_at` | aware UTC datetime | naive/미래 비정상 값 거부 |
| `max_attempts` | int | 1..12, 운영 배포값 12 |
| `binding_digest` | SHA-256 digest | mode/strategy/universe/risk/broker/daily policy의 canonical digest |
| `policy_version` | string | 변경 시 기존 승인을 무효화 |
| `suspended_reason` | stable code/null | ACTIVE에서는 null |

정책 파일 쓰기와 감사 쓰기 중 하나라도 실패하면 기존 ACTIVE 정책을 새 값으로 교체하지
않는다. suspend는 감사 fsync 뒤 정책 상태와 현재 session permit 제거를 원자적 순서로
수행하며, 중간 실패는 fail closed한다.

#### Live authorization store

현재 schema 2 `LiveAuthorizationEnvelope`를 유지한다. 자동 발급 permit도 같은 codec,
원자 교체, attempt 소비, authorization generation 검사를 사용한다. 새 필드는 만들지
않고 감사 event의 source만 `automatic_policy`로 구분한다.

#### Trading session store

`runtime/trading_session.json`을 기존 daily-minimum PRD의 schema 2로 확장한다.
`daily_attempt`과 `owned_lot`은 서로 분리하며, 기존 safety counts와 signal claims를
보존하는 원자 migration을 사용한다. 허용 상태와 전이는 기존 daily-minimum PRD 0.2의
표를 그대로 상속한다.

#### Trading settings

| Field | Default | Valid values |
|---|---:|---|
| `automatic_session_authorization_enabled` | false | bool |
| `daily_minimum_order_enabled` | false | bool |
| `daily_minimum_max_spread_bps` | 50 | int 1..500 |

배포 후 운영 설정에서 앞의 두 flag를 true로 바꾸는 것만으로 ACTIVE 정책이 만들어지지
않는다. `authorize-auto-live-policy`가 현재 설정 digest를 별도로 승인해야 한다.

### 4.3 API Design

외부 HTTP API는 없다. frozen CLI와 내부 typed API를 확장한다.

| Command / API | Input | Result | Broker/Network |
|---|---|---|---|
| `authorize-auto-live-policy` | `--max-attempts 1..12`, exact confirmation | ACTIVE policy JSON summary | 금지 |
| `suspend-auto-live-policy` | exact confirmation | SUSPENDED + current permit revoked | 금지 |
| `resume-auto-live-policy` | exact confirmation, current exact binding | ACTIVE with new authorization id | 금지 |
| `auto-live-policy-status` | none | status, binding match, current permit metadata | 금지 |
| `ensure_automatic_session(now)` | aware datetime + typed policy context | created/reused/blocked typed result | 금지 |
| `plan_affordable_candidates(plan)` | immutable ranking + typed account/position inputs | eligible/excluded typed tuple | KIS GET adapter only |

CLI JSON은 `ready`, `status`, `reason`, `market_date`, `max_attempts`, `attempts`만 공개하며
digest, account identifier, secrets와 raw exception을 출력하지 않는다. 잘못된 confirmation,
live mode 아님, paper KIS, binding mismatch는 exit code 2와 안정적 reason을 반환한다.

### 4.4 Key Technical Decisions

| Decision | Options Considered | Chosen | Rationale |
|---|---|---|---|
| 자동 권한 범위 | 영구 permit / 매일 수동 / 장기 정책+당일 횟수 무제한 permit | 장기 정책+당일 횟수 무제한 permit | 일일 횟수 상한 없이 운영하되 장외·다음날 permit 재사용 방지 |
| 정책 변경 | 현재 설정 자동 승인 / digest 고정 | digest 고정 | 전략·위험 확대의 무의식적 실거래 방지 |
| 비상 정지 | 현재 permit만 삭제 / 정책 suspend | 정책 suspend | 재시작 즉시 자동 재승인되는 위험 방지 |
| 잔고 필터 위치 | 공개 selection 점수 변경 / 주문 전 내부 planner | 내부 planner | 모델 결과 불변, 실행 가능성만 반영 |
| KIS 가격 정규화 | 각 주문 생성기 / broker POST boundary | shared Decimal boundary | 모든 주문 경로를 한 곳에서 동일하게 보호 |
| 일일 최소 시점 | 장 시작 첫 적격 사이클 / 마감 60분 전 | 장 시작 첫 적격 사이클 | 사용자의 실제 일일 주문 요구를 직접 충족 |
| 일일 주문 의미 | production POST / 체결 | production POST | 체결은 시장이 결정하지만 dry-run 평가는 성공으로 오인하지 않음 |
| 일일 상태 | 별도 JSON / canonical session store | canonical store schema 2 | normal-vs-fallback 원자 경쟁 방지 |

## 5. Edge Cases & Error Handling

| # | Scenario | Expected Behavior | Severity |
|---|---|---|---|
| E1 | 휴장·premarket·정확한 close | permit/POST 0, `regular_market_closed` | P0 |
| E2 | DST·조기폐장 | NASDAQ calendar의 해당 session 경계 사용 | P0 |
| E3 | 앱이 장중 재시작, 당일 permit 없음 | ACTIVE exact policy면 permit 한 번 생성 | P1 |
| E4 | 두 프로세스가 동시에 permit 생성 | 한 authorization id만 저장·사용 | P0 |
| E5 | 정책 digest 변경 | `BINDING_CHANGED`, permit/POST 0 | P0 |
| E6 | 긴급정지 뒤 재시작 | SUSPENDED 유지, 자동 발급 0 | P0 |
| E7 | attempt 12회 소진 | 13번째 POST 0 | P0 |
| E8 | 상위 후보 1주가 현금보다 비쌈 | 다음 적격 후보 평가 | P1 |
| E9 | cash는 충분하지만 KIS psamount 부족 | 해당 후보 제외 | P1 |
| E10 | 잔고/psamount GET timeout | 평가 전체 차단, cached 값 사용 금지 | P0 |
| E11 | 개장 첫 사이클 전에 정상 SELL 한 번 수행 | daily 평가/POST 0 | P1 |
| E12 | 소유 lot 없음, 매수 후보 없음 | `daily_minimum_unmet`, POST 0 | P1 |
| E13 | 수동 보유 1주만 존재 | 최소 SELL 금지 | P0 |
| E14 | request 전송 뒤 응답 유실 | manual reconciliation, 신규 POST 0 | P0 |
| E15 | 금요일 BUY 뒤 월요일 | owned lot 보존, 월요일 daily attempt만 reset | P0 |
| E16 | app start가 close-stop 뒤 | 당일 missed 기록, 다음날 보충 금지 | P2 |
| E17 | auto flag false이나 unresolved order 있음 | GET 대사와 전역 POST 차단 유지 | P0 |
| E18 | audit/store 쓰기 실패 | 상태 노출 확대 없이 fail closed | P0 |
| E19 | price 1 USD 경계 | `>=1`: 0.01, `<1`: 0.0001 tick 적용 | P1 |
| E20 | normal BUY와 daily BUY 동시 경쟁 | canonical lock 재확인으로 daily 중복 POST 0 | P0 |
| E21 | `$1 이상` 가격 `27.075` SELL | intent와 POST 모두 `27.07`, KIS 자릿수 오류 0 | P0 |
| E22 | `$1 이상` 가격 `27.075` BUY | intent와 POST 모두 `27.08`, cash/psamount를 정규화 가격으로 재검사 | P0 |
| E23 | `$1 미만` 가격 `0.12345` | SELL `0.1234`, BUY `0.1235` | P1 |

## 6. Security & Permissions

### 6.1 Authentication

- 자동운영 정책 authorize/resume은 현재 설치의 LIVE mode, `broker=kis`, KIS real
  environment, `NASDAQ_AUTO_TRADER_ALLOW_LIVE=YES`, 기존 두 live setting flag와 exact
  confirmation phrase가 모두 필요하다.
- CLI는 broker client, token refresh, 주문·잔고 API를 생성하거나 호출하지 않는다.
- 자동 permit 생성은 ACTIVE 정책의 immutable binding만 확인하며 새 권한을 확대하지
  않는다.

### 6.2 Authorization

| Role | Authorize policy | Suspend | Resume | Read status | Submit order |
|---|---:|---:|---:|---:|---:|
| Local interactive operator | Yes | Yes | Yes | Yes | No direct POST |
| GUI unattended controller | No | Emergency suspend only | No | Yes | Guarded path only |
| Scheduled health task | No | No | No | Process health only | No |
| Live canary task | Separate policy only | No | No | Own state only | Canary lease path only |

### 6.3 Data Protection

- 계좌번호, 상품코드, API key/secret, access token, raw KIS response는 신규 store와 감사
  로그에 저장하지 않는다.
- 계좌·route 바인딩은 기존 canonical broker authorization digest를 constant-time으로
  비교한다.
- store는 현재 사용자 전용 `%LOCALAPPDATA%` 아래 원자 교체와 file lock을 사용한다.
- 자동화·frozen QA는 live 환경변수와 credential 파일을 제거한 임시 `LOCALAPPDATA`에서
  sentinel broker의 모든 network/POST 호출을 실패시키도록 실행한다.

## 7. Performance & Monitoring

| Metric | Target | Measurement |
|---|---:|---|
| 정책/permit 로컬 판정 p95 | 20 ms 이하 | monotonic telemetry, broker I/O 제외 |
| 거래일 permit 생성 수 | 정확히 1 이하 | audit/store authorization id |
| 일일 최소 평가 수 | 거래일당 1 이하 | `daily_minimum_evaluated` |
| 일일 자동 POST 수 | 기존 daily limits 이하 | session reservation + KIS history |
| 결과 불명 뒤 신규 POST | 0 | fault-injection ledger |
| balance-aware GET | 후보당 account 1회 공유, psamount 1회 | fake adapter call count |

### 7.1 Monitoring & Alerting

- GUI 상태 영역에 자동 정책, 당일 permit, attempt 잔여량, daily minimum 상태를 표시한다.
- `BINDING_CHANGED`, `SUSPENDED`, `MANUAL_RECONCILIATION_REQUIRED`는 매 cycle 신규 로그를
  쌓지 않고 상태 변경 시 감사 1회, GUI 지속 경고로 표시한다.
- `daily_minimum_unmet`을 날짜와 안정적 reason별로 집계한다. 실제 금액·계좌 식별자는
  metric label로 사용하지 않는다.
- 12회 attempt 소진, account-state 오류 3회 연속, manual reconciliation은 고우선순위
  운영자 경고다.

## 8. Testing Strategy

### 8.1 Unit Tests

- aware clock 기준 정규장 open/close, 휴장, DST, 조기폐장 permit 생성 경계
- automatic policy codec, binding mismatch, suspend/resume, unknown schema
- actual order `begin`에서만 attempt 증가하고 cycle/selection은 0 소비
- Decimal affordability와 tick/spread 경계: 1 microsecond/1 cent/1 bps 아래·정확히·위
- KIS general order body의 `27.075 SELL -> 27.07`, `27.075 BUY -> 27.08`,
  `0.12345 SELL -> 0.1234`, `0.12345 BUY -> 0.1235` 회귀 테스트
- immutable ranking에서 비싼 후보를 건너뛰고 다음 후보 선택
- daily state transition과 owned-lot 수량 방정식
- 모든 enum/union exhaustive transition 거부

### 8.2 Integration Tests

- 서로 다른 store instance와 실제 process 두 개의 concurrent permit create
- normal BUY/SELL과 daily BUY/SELL의 barrier-controlled atomic reservation 경쟁
- account-wide lease와 canary known/manual/open-order 충돌
- KIS fake wire adapter의 paginated history/open orders/positions/psamount/quote 계약
- audit 실패, lock timeout, fsync/replace 실패, process termination 후 disk reopen
- `authorize -> auto permit -> begin -> confirm -> finish`, suspend 후 다음 cycle 차단
- feature false에서도 unresolved order reconciliation/global gate 유지

### 8.3 Edge Case and E2E Tests

- 현재/다음 거래일, 주말, 2026-11-27 조기폐장, DST 전후, host timezone 독립성
- open 정확히 전·정확히 open·open 뒤 첫 tick, configured open wait, close-stop 경계
- crash boundaries: policy audit 전후, permit write 전후, daily claim, intent fsync,
  request bytes sent, exact ID 수신, known-order 저장과 대사 저장 전후
- frozen EXE `--help`, policy status/authorize bad input, credential-free happy path
- frozen diagnostic daily coordinator는 sentinel broker를 사용해 외부 ledger 기준
  network client constructed=0, POST=0을 증명
- Windows GUI에서 한국어 상태가 잘리지 않고 긴급정지가 재시작 뒤 유지되는지 확인
- staged full onedir package audit 뒤 운영 설정과 ACTIVE 정책이 별도 단계로만 활성화되는지
  확인

## 9. Rollout Plan

### 9.1 Migration Strategy

1. 기능 코드는 두 setting의 기본값 false로 배포한다.
2. 기존 `LiveAuthorizationStore` schema 2는 그대로 사용한다.
3. `TradingSessionStore` schema 1을 기존 필드 보존 상태로 schema 2에 원자 migration한다.
4. 기존 daily-minimum 미구현 상태이므로 owned lot과 unresolved daily order는 비어 있어야
   한다. 예상과 다른 state는 fail closed한다.
5. 자동운영 정책은 배포 후 별도 CLI 승인으로 처음 생성한다. 기존 session permit을
   자동 정책으로 승격하지 않는다.

### 9.2 Feature Flag

- `automatic_session_authorization_enabled=false`
- `daily_minimum_order_enabled=false`
- 소스·테스트·frozen QA·staging 동안 둘 다 false를 유지한다.
- 최종 운영 배포에서만 전체 onedir 교체, runtime config backup, 정책 authorize 순서로
  활성화한다.

### 9.3 Rollback Plan

1. 자동 정책을 suspend하고 current permit을 revoke한다.
2. exact known order와 daily unresolved state를 GET 대사한다. PMHS/manual이면 코드
   rollback을 금지한다.
3. owned lot이 있으면 현재 버전으로 안전 SELL을 완료하거나 typed admin handoff로
   수동 소유권 이전을 감사 기록한다.
4. schema 2 `trading_session.json`을 검증된 v1 projection으로 변환하되 unresolved/owned
   상태가 없는 경우에만 수행한다.
5. 자동 정책 파일을 archive하고 삭제한다. 이전 바이너리에 자동 권한을 이식하지 않고
   필요하면 이전 형식의 신규 수동 승인을 받는다.
6. 직전 전체 onedir backup을 복구하고 scheduled task가 한 설치 경로만 가리키는지
   확인한다.

## 10. Dependencies & Risks

### 10.1 Dependencies

| Dependency | Owner | Status | Risk if Delayed |
|---|---|---|---|
| NASDAQ calendar / market session oracle | existing runtime | Available | 자동 permit과 daily 주문 시간 판정 불가 |
| LiveAuthorizationStore/AutomaticOrderGuard | existing runtime | Available | attempt·binding 재사용 불가 |
| TradingSessionStore canonical lock | existing runtime | Schema extension required | normal-vs-fallback 경쟁 방지 불가 |
| KIS account/psamount/positions/orders/history/quote | broker adapters | Partially available | affordability·대사 구현 불가 |
| account-wide broker lease | existing canary/live path | Available | concurrent POST 배제 불가 |
| prethreshold immutable ranking | selection pipeline | Extension required | no-signal BUY 후보 없음 |

### 10.2 Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| 매일 수동 승인 제거로 실거래 노출 증가 | High | High | one-time bound policy, regular session only, 12 attempts, emergency suspend |
| 설정 변경을 묵시적으로 승인 | Medium | High | exact digest mismatch fail closed |
| 비상 revoke 뒤 자동 재발급 | Medium | High | revoke atomically suspends policy |
| 잔고 GET 지연로 사이클 deadline 초과 | Medium | Medium | shared deadline, no retry after expiry, call-count telemetry |
| daily 주문과 정상 전략 동시 POST | Low | High | one canonical lock, zero-count recheck, account-wide lease |
| 수동 보유분 자동 매도 | Low | High | baseline 0 + exact ID fill + total qty equation |
| “매일 반드시”와 안전 차단의 기대 차이 | Medium | Medium | order-attempt SLO와 unmet reason을 명시 |
| dirty worktree/배포 artifact 혼동 | Medium | High | build provenance, full onedir audit, stale `dist-update` 미사용 |

## 11. Success Metrics

| Metric | Baseline | Target | Measurement Method |
|---|---:|---:|---|
| 정책 일치 거래일의 승인 누락 차단 | 매일 수동 조작 필요 | 0 | auto permit audit |
| 장외 자동 permit/POST | 0 | 0 유지 | market boundary tests + audit |
| 전제조건 충족·기존 주문 0인 날의 KIS production POST | 0 | 100% | external POST ledger + KIS history |
| 현금 부족 상위 후보 때문에 전체 BUY 포기 | 발생 가능 | 0 | exclusion/next-candidate test |
| 결과 불명 뒤 중복 POST | 0 | 0 유지 | crash/fault ledger |
| 수동 보유분 daily SELL | 0 | 0 유지 | ownership reconciliation audit |
| 자동 정책 suspend 뒤 재발급 | N/A | 0 | restart E2E |
| KIS price precision 거절 | 1건 이상 | 0 | broker-boundary payload tests + rejection audit |

## 12. Open Questions

없음. 사용자는 XL 경로와 다음 운영 계약을 승인했다.

- 정규장 자동 권한은 한 번 승인한 immutable 정책 범위에서만 지속된다.
- 일일 보장은 체결이 아니라 최소 1주의 실제 KIS production POST다.
- 현금·시장·위험·결과 불명 상태를 우회하는 주문은 만들지 않는다.
