# PRD: 뉴욕 정규장 단위 실거래 승인

**Version**: 0.3
**Author**: Codex
**Date**: 2026-08-11
**Status**: Implemented and deployed
**Size**: M

---

## 1. Problem Statement

### 1.1 Background

현재 자동선택 실거래 승인은 발급 시각부터 최대 60분, 최대 12개 자동 주기로
제한된다. GUI는 5분마다 자동 주기를 실행하므로 사용자가 장 시작 전에 승인해도
개장 전에 만료될 수 있고, 개장 후 승인해도 약 60분 뒤 `live_authorization_expired`
또는 `live_authorization_cycle_limit_reached`로 보유종목 평가와 주문이 중단된다.
2026-08-10 WBD 사례에서는 승인 만료 뒤 모든 자동 주기가 결과 0건으로 종료되어
익절 조건 재평가가 중단됐다.

### 1.2 Problem Definition

명시적으로 승인한 한 개의 뉴욕 거래일 동안에는 벽시계 60분이나 단순 조회 주기
횟수 때문에 승인이 끊기지 않아야 한다. 주문 가능 시간은 해당 거래일의 NASDAQ
정규장으로만 한정하고 다음 거래일에는 새 승인을 요구해야 한다.

### 1.3 Impact of Not Solving

- 장중 보호 매도와 정상 전략 주문이 승인 만료 때문에 예고 없이 중단된다.
- 사용자가 장중 매시간 프로세스를 재시작하거나 승인 저장소를 초기화해야 한다.
- 화면상 자동운영 중이어도 실제 주문은 차단되는 운영 오해가 반복된다.

## 2. Goals & Non-Goals

### 2.1 Goals

- [x] G1: 승인 1회를 정확히 한 개의 NASDAQ 거래일과 결합한다.
- [x] G2: 해당 거래일 정규장 `[market_open, market_close)`에서만 실거래 승인 검사를
  통과시킨다. 조기 폐장일은 거래소 달력의 실제 마감 시각을 사용한다.
- [x] G3: 장 전 승인은 당일 거래일, 장 마감 후·휴일·주말 승인은 다음 NASDAQ
  거래일에 결합한다.
- [x] G4: 5분 조회/평가 주기는 승인 한도를 소비하지 않는다. 실제 주문 의도가
  `AutomaticOrderGuard.begin`에 도달할 때만 원자적으로 1회를 소비하며 최대 12회
  상한은 유지한다.
- [x] G5: 다음 거래일, 장 밖, 승인 결합 변경, 13번째 주문 의도에서는 브로커 POST
  0건을 보장한다.
- [x] G6: 현재 장기 실행 GUI가 새 승인 정책을 사용하도록 전체 onedir를 재빌드하고
  해당 거래일 승인을 명시적으로 재발급한다.

### 2.2 Non-Goals

- NG1: 다음 거래일 자동 승인 또는 영구 승인을 도입하지 않는다.
- NG2: 정규장 밖, 프리마켓, 애프터마켓 주문을 허용하지 않는다.
- NG3: 일일 매수·매도 횟수, 현금, 포지션, 신호 claim, 감사, broker lease,
  reconciliation 안전장치를 완화하지 않는다.
- NG4: bounded live canary의 별도 `live-canary-arm` 계약은 변경하지 않는다.
- NG5: 승인 없이 앱 재시작만으로 새 거래일 권한을 자동 생성하지 않는다.

## 3. User Stories & Acceptance Criteria

### US-1: 거래일 전체 자동운영

**As a** 실거래 운영자, **I want** 승인한 뉴욕 거래일의 정규장 전체에서 자동매매가
동작하기를, **so that** 60분 만료 때문에 보호 매도와 전략 주문이 중단되지 않는다.

**Acceptance Criteria:**

- [x] AC-1.1: Given 2026-08-11 NASDAQ 거래일 승인이 있고 시각이 정규장 안일 때,
  when 60분이 지났거나 12회보다 많은 무주문 평가 주기가 실행되어도, then 승인은
  시간·평가주기 이유로 차단되지 않는다.
- [x] AC-1.2: Given 동일 승인과 최대 11개의 실제 주문 의도 소비가 있을 때, when
  12번째 주문 의도가 도달하면 허용되고 13번째는
  `live_authorization_attempt_limit_reached`로 차단되며 POST는 0건이다.
- [x] AC-1.3: Given 승인한 거래일의 정규장 안일 때, when 주문 의도가 생기면,
  then 기존 settings/risk/market-hours/claim/audit/confirm/finish 경로를 모두 통과한다.

### US-2: 장 밖과 다음 거래일 차단

**As a** 계좌 소유자, **I want** 승인이 한 거래일을 넘어 재사용되지 않기를,
**so that** 무인 프로세스가 다음 날 자동으로 실거래하지 않는다.

**Acceptance Criteria:**

- [x] AC-2.1: Given 당일 승인, when 시각이 정규장 전 또는 마감과 같거나 이후이면,
  then selection/report와 보유종목 평가는 계속되지만 주문 의도는 기존 엔진의
  `regular_market_closed` 선행 게이트 또는 승인 런타임의
  `live_authorization_outside_regular_session`으로 차단되고, attempt 소비 0, POST 0이다.
- [x] AC-2.2: Given 전 거래일 승인, when 다음 거래일 정규장이 열리면, then
  `live_authorization_market_date_mismatch`, POST 0이며 새 명시 승인이 필요하다.
- [x] AC-2.3: Given 장 전 승인, when 당일 정규장이 열리면, then 동일 승인이
  활성화된다. Given 장 마감 후·휴일·주말 승인, then 다음 예정 NASDAQ 거래일에
  결합된다.
- [x] AC-2.4: Given 조기 폐장 거래일, when 거래소 달력의 실제 마감 시각에
  도달하면, then 즉시 장 밖으로 차단된다.

### US-3: 안전한 저장·배포

**As a** 운영자, **I want** 기존 60분 승인 파일이 새 정책으로 자동 승격되지 않기를,
**so that** 배포만으로 실거래 권한이 생기지 않는다.

**Acceptance Criteria:**

- [x] AC-3.1: Given schema 1 승인 파일, when 새 바이너리가 시작되면, then
  `live_authorization_reapproval_required`로 fail-closed하고 POST 0이다.
- [x] AC-3.2: Given 사용자가 새 승인을 명시적으로 요청하면, when 기존 승인 파일을
  잠금 아래 archive/clear한 뒤 발급하면, then schema 2 파일에 `market_date`,
  `max_attempts`, `attempts`가 저장된다.
- [x] AC-3.3: Given schema 2 파일과 프로세스 재시작, when 같은 거래일 정규장에
  재개하면, then 이미 소비한 attempt 수가 보존되고 한도가 초기화되지 않는다.
- [x] AC-3.4: Given 구버전 rollback, when schema 2 승인 파일이 존재하면, then
  archive 후 제거하고 구버전 형식의 새 승인을 요구한다.
- [x] AC-3.5: Given broker environment, account fingerprint, product 또는 exchange route가
  승인 시점과 달라지면, when 주문 의도를 검증할 때, then
  `live_authorization_binding_changed`, POST 0이며 새 명시 승인이 필요하다.
- [x] AC-3.6: Given 저장된 schema 2 승인이 없을 때, when
  `once --auto-select --confirm-live-orders`, `loop --auto-select`, GUI/controller 또는 직접
  `TradingEngine` 생성을 실행해도, then `live_authorization_required`, 승인 파일 생성 0,
  attempt 소비 0, POST 0이다. schema 2 생성 권한은 `authorize-live-session`에만 있다.

## 4. Technical Design

### 4.1 Architecture Overview

```text
명시 승인
  -> 다음 적용 NASDAQ market_date 계산
  -> LiveAuthorizationEnvelope(schema 2, market_date, max_attempts=12)
  -> LiveAuthorizationStore 잠금 저장

자동 평가 주기
  -> AutomaticOrderGuard.start_cycle(now)
  -> 저장소를 다시 읽어 명시 승인·취소를 현재 프로세스에 반영
  -> schema/binding 준비 상태만 검증, 장 밖이라는 이유로 평가를 중단하지 않음
  -> attempt 소비 없음
  -> 전략 평가
  -> 주문 의도 발생
  -> AutomaticOrderGuard.begin(..., now)
  -> session/date 재검증 + store.consume_attempt() 원자 증가
  -> 기존 reservation -> audit -> signal claim -> confirm -> broker POST -> finish
```

### 4.2 Data Model Changes

`trading_session.live-authorization.json`을 schema 2로 올린다.

```json
{
  "schema_version": 2,
  "attempts": 0,
  "envelope": {
    "authorization_id": "128-bit-random-hex",
    "market_date": "2026-08-11",
    "max_attempts": 12,
    "mode": "live",
    "strategy_id": "...",
    "strategy_version": "...",
    "strategy_digest": "...",
    "universe_id": "...",
    "universe_effective_date": "...",
    "universe_version": "...",
    "risk_digest": "...",
    "learned_risk_digest": "...",
    "broker_authorization_digest": "..."
  }
}
```

- schema 1의 `expires_at`, `max_cycles`, `cycles`는 schema 2로 자동 변환하지 않는다.
- schema 1은 손상으로 오인하지 않고 `live_authorization_reapproval_required`로 구분한다.
- 승인 명령이 있을 때만 schema 1을 archive하고 schema 2를 새로 저장한다.
- 알 수 없는 미래 schema는 `live_authorization_store_corrupt`로 fail-closed한다.
- 저장은 기존 file lock, 임시 파일 fsync, `os.replace` 원자 교체를 유지한다.
- `authorization_id`는 승인 발급마다 CSPRNG로 새로 만드는 128-bit nonce다. 같은
  거래일·같은 binding으로 재발급해도 이전 세대와 구분되며, `consume_attempt`와
  `validate_current(expected)`는 반드시 이 값을 비교한다.
- `broker_authorization_digest`는 비밀이 아닌 broker binding의 canonical JSON SHA-256이다.
  KIS에서는 broker kind, live/paper endpoint label, 기존
  `account_fingerprint(account_no, account_product_code)`, product code, 주문/가격 exchange
  route, currency를 포함한다. raw 계좌번호·키·비밀은 저장하거나 감사하지 않는다.
  다른 broker는 해당 adapter가 제공하는 동등한 비밀 없는 account/environment identity를
  사용하며, 이를 제공할 수 없으면 승인 발급을 fail-closed한다.

### 4.3 API Design

외부 HTTP API는 없다. 내부 계약은 다음과 같이 변경한다.

| Interface | Input | Output / Error |
|---|---|---|
| `authorization_market_date(now)` | aware datetime | 현재 정규장 종료 전이면 현재 예정 거래일, 이후면 다음 거래일 `date` |
| `create_live_authorization(request)` | config, paths, now, max_attempts | schema 2 envelope 또는 typed block |
| `store.load()` | 없음 | schema 2 stored authorization 또는 typed reapproval/corrupt block |
| `store.validate_current(expected)` | expected envelope | 삭제·교체·binding 변경 검증, 저장 변경 없음 |
| `guard.start_cycle(now)` | aware datetime | store reload 후 schema/binding 준비 상태 검증, 장 밖 평가 허용, 저장 횟수 변경 없음 |
| `store.consume_attempt(expected)` | schema 2 envelope | 원자 증가 후 `(reason, attempts)` |
| `guard.begin(context, order, now)` | 기존 주문 컨텍스트 | session/date 검증과 attempt 소비 후 기존 permit/block |
| `authorize-live-session` CLI | config, `--confirm`, `--max-attempts` | 기존 파일 archive 후 schema 2 발급 JSON |
| `revoke-live-session` CLI | config | 현재 승인을 잠금 아래 archive 후 제거, broker/client 생성 0 |

명시 승인 명령은 다음 계약을 사용한다.

```text
NasdaqAutoTrader.exe --config <deployed-config> authorize-live-session \
  --max-attempts 12 \
  --confirm "I UNDERSTAND THIS WILL PLACE REAL ORDERS DURING ONE NASDAQ SESSION"
```

- 정확한 확인 문구가 아니면 `live_session_confirmation_required`, exit 2, 저장 변경 0이다.
- 명령은 broker/market-data client를 만들거나 주문·조회 API를 호출하지 않는다.
- 승인 intent 감사가 먼저 성공해야 저장소를 교체한다. intent 감사 실패 시 권한 0이다.
- 기존 `loop --live-auth-minutes`는 승인 발급 기능을 잃고 제거한다. 모든 자동 실거래
  실행 표면인 `once --auto-select`, `loop --auto-select`, GUI/controller cycle과
  `TradingEngine.__init__`은 이미 저장된 schema 2 승인만 load-only로 사용한다. 앱
  재시작이나 `--confirm-live-orders`만으로 새 승인을 만들지 않는다.
- `--max-attempts` 허용 범위는 `1..12`, 기본값 12이다.
- `revoke-live-session`은 현재 파일이 없어도 idempotent success이며, 승인 revoke 감사가
  성공한 뒤에만 저장소를 archive/clear한다. broker/market-data client와 주문·조회 API를
  만들거나 호출하지 않는다. 실행 중 GUI는 다음 `start_cycle`에서
  `live_authorization_required`를 반영한다.
- `start_cycle`은 유효한 schema 2 승인이 장 전·마감 후라는 이유만으로 selection/report를
  빈 결과로 만들지 않는다. 정규장과 target market date는 실제 주문 의도의 `begin`과
  broker POST 직전 `confirm`에서 각각 다시 검증한다.

### 4.4 Key Technical Decisions

| Decision | Options Considered | Chosen | Rationale |
|---|---|---|---|
| 승인 범위 | 영구 / 60분 / 거래일 | 거래일 | 장중 중단을 없애면서 다음 날 재승인 유지 |
| 한도 소비 | 매 평가주기 / 주문 의도 | 주문 의도 | 5분 감시가 권한을 소모하지 않으며 실거래 위험은 12회로 제한 |
| 장 판정 | 고정 09:30~16:00 / 거래소 달력 | `regular_market_session` | 휴일·DST·조기폐장 정확성 |
| schema 1 처리 | 자동 승격 / fail-closed | 명시 재승인 전 fail-closed | 배포만으로 권한 생성 방지 |
| 장 밖 처리 | 대기 허용 / 승인 차단 | 평가 가능하되 승인·POST 차단 | GUI 감시는 유지하고 실주문만 차단 |
| 승인 표면 | GUI 자동발급 / 전용 CLI | 전용 authorize-only CLI | 실행과 승인을 분리하고 broker 생성 0을 검증 가능 |

## 5. Edge Cases & Error Handling

| # | Scenario | Expected Behavior | Severity |
|---|---|---|---|
| E1 | naive datetime | typed invalid-time block, 저장 변경·POST 0 | P1 |
| E2 | 장 전 승인 | 당일 거래일 결합, 개장 전 attempt 0 | P1 |
| E3 | 장 마감 후 승인 | 다음 예정 거래일 결합 | P1 |
| E4 | 주말·휴일 승인 | 다음 예정 거래일 결합 | P1 |
| E5 | DST 전후 | `America/New_York` 달력 기준 동일 동작 | P1 |
| E6 | 조기 폐장 | 실제 close부터 장 밖 차단 | P1 |
| E7 | 정확히 open / close | open 포함, close 제외 | P1 |
| E8 | 12번째 / 13번째 주문 의도 | 12번째 허용, 13번째 차단 | P1 |
| E9 | begin 뒤 confirm 전에 장 마감 | confirm에서 차단, 기존 claim REJECTED, POST 0 | P0 |
| E10 | 두 프로세스 동시 주문 의도 | store lock으로 attempt 원자 증가, 최대 12 초과 없음 | P0 |
| E11 | schema 1/미래 schema/손상 JSON | 재승인 요구 또는 corrupt fail-closed, POST 0 | P0 |
| E12 | strategy/universe/risk digest 변경 | binding changed, 새 승인 전 POST 0 | P0 |
| E13 | 앱 재시작 | 동일 schema 2 attempt 유지 | P1 |
| E14 | 승인 발급 중 write/lock 실패 | 이전 권한을 승격하지 않고 typed block | P0 |
| E15 | 확인 문구 오타/누락 | exit 2, archive·store·broker 변경 0 | P0 |
| E16 | 승인 intent 감사 실패 | 저장소 교체 0, 기존 만료 권한 유지 | P0 |
| E17 | 승인 archive 뒤 신규 write 실패 | 활성 승인 없음, 재승인 필요, 원본 archive 보존 | P0 |
| E18 | GUI 실행 중 CLI 승인/`revoke-live-session` | 다음 `start_cycle`에서 reload, 재시작 없이 반영 | P1 |
| E19 | begin 후 confirm 전 승인 파일 삭제·동일 binding 재발급 | authorization_id 불일치로 confirm 차단, claim REJECTED, POST 0 | P0 |
| E20 | attempt 저장 직후 audit/claim 전 crash | attempt 1회는 영구 소비, claim 없음, POST 0 | P0 |
| E21 | claim 뒤 confirm/POST 전 crash | 기존 SUBMITTING -> UNCERTAIN 복구 및 reconciliation, 추가 POST 0 | P0 |
| E22 | broker POST 뒤 응답 저장 전 crash | 기존 exact-order reconciliation 경로, 추가 POST 0 | P0 |

### 5.1 Attempt Crash Consistency

- `consume_attempt`의 잠금 내 원자 저장이 성공한 순간 attempt는 소비 완료다. 이후
  readiness, safety reservation, audit, claim, confirm 실패나 프로세스 종료가 있어도
  rollback하지 않는다.
- attempt 저장 뒤 claim 전 종료는 "소비 1, claim 없음, broker POST 0"으로 재개한다.
- claim이 생성된 뒤 종료는 기존 `SUBMITTING -> UNCERTAIN` 복구와 reconciliation을
  그대로 사용하며 새 attempt나 새 POST를 만들지 않는다.
- broker POST 이후 종료는 기존 order-response/reconciliation 계약을 그대로 사용한다.
  attempt를 되돌리거나 같은 주문 의도를 자동 재전송하지 않는다.

## 6. Security & Permissions

### 6.1 Authentication

- KIS 자격증명·계좌 식별자는 승인 파일이나 로그에 새로 기록하지 않는다.
- live mode, environment authorization, champion strategy, universe/risk digest 검증을
  그대로 유지한다.
- 신뢰 경계는 현재 Windows 운영 사용자다. 이 사용자는 설정 파일을 변경하고 승인 CLI를
  직접 실행할 권한이 있으므로, 동일 사용자 권한을 탈취한 악성 프로세스에 대한 승인 파일
  위조 방지는 이 기능의 범위가 아니다. 다른 OS 사용자로부터의 격리는 기존
  `%LOCALAPPDATA%\NasdaqAutoTrader` ACL에 의존한다.
- 범위 안에서는 우발적 손상, 이전 schema 재사용, stale generation, 동시 소비와
  account/broker/config binding 변경을 모두 fail-closed한다. 암호학적 서명이나 DPAPI
  무결성 키 도입은 별도 보안 강화 기능으로 다룬다.

### 6.2 Authorization

| Operation | Permission |
|---|---|
| 거래일 승인 발급 | 사용자의 명시 요청이 있는 로컬 운영자만 |
| 장중 평가 | 앱 running 상태 |
| 주문 의도 소비 | 동일 envelope binding + 정규장 + store lock |
| broker POST | 기존 모든 guard/claim/audit/lease 조건 통과 후만 |

### 6.3 Data Protection

- 감사 이벤트에는 market date, reason, attempt count만 기록하고 토큰·키·계좌번호·raw
  broker 응답은 기록하지 않는다.
- archive 파일은 기존 runtime 권한을 유지하며 자동 재사용하지 않는다.

## 7. Performance & Monitoring

| Metric | Target | Measurement |
|---|---|---|
| session/date 승인 검사 p95 | 20ms 이하 | guard timing audit |
| attempt 원자 소비 | 주문 의도당 정확히 1회 | store/audit counter |
| 장 밖 broker POST | 0 | fake broker 및 production audit |

### 7.1 Monitoring & Alerting

- `live_authorization_session_approved`, `outside_regular_session`,
  `market_date_mismatch`, `attempt_limit_reached`, `reapproval_required` 사유를 민감정보 없이
  기록한다.
- UI에는 대상 뉴욕 거래일과 남은 주문 의도 한도를 표시하거나 기존 차단 사유 로그에
  포함한다.

## 8. Testing Strategy

### 8.1 Unit Tests

- `authorization_market_date`: 장 전, 장중, 장 마감, 주말, 휴일, DST, 조기폐장 경계.
- envelope 생성: market date/digest/max attempts binding과 naive datetime 차단.
- store schema 2 round-trip, attempt 12/13 경계, schema 1·미래 schema fail-closed.
- guard `start_cycle`은 무주문 주기에서 attempt를 소비하지 않음.
- CLI 확인 문구, max-attempt 범위, broker/client 미생성, 감사 실패와 archive/write 실패.
- 저장 승인 없이 `once --auto-select --confirm-live-orders`를 실행해도 승인 파일·attempt·
  broker POST가 0이고 `live_authorization_required`인지 확인한다.

### 8.2 Integration Tests

- 78개의 5분 무주문 주기 뒤에도 같은 거래일 장중 주문 의도가 허용됨.
- 실제 주문 의도만 1회 소비하고 재시작 뒤 수가 보존됨.
- 장 마감 직전 begin 후 close 시각 confirm은 POST 0 및 claim 정리.
- 두 `LiveAuthorizationStore` 인스턴스/프로세스의 동시 소비가 12를 넘지 않음.
- 기존 live settings/risk/market-hours/claim/audit/broker lease 테스트 전부 유지.
- frozen EXE QA는 자격증명과 live env를 제거한 격리 경로에서 수행해 POST 0을 증명.

### 8.3 Edge Case Tests

- Section 5의 E1~E22를 deterministic aware clock과 fake broker로 모두 매핑한다.
- E15 확인 문구 실패, E16 승인 intent 감사 실패, E17 archive 뒤 write 실패를 각각
  저장 변경 0 또는 활성 승인 0의 명시 계약으로 검증한다.
- E18은 실행 중 guard가 다음 `start_cycle`에서 새 승인/`revoke-live-session`을
  reload하는 통합 시험으로 검증한다.
- E19는 begin 뒤 동일 market date·동일 binding이지만 새 `authorization_id`인 승인으로
  교체할 때 claim REJECTED와 broker POST 0인 통합 시험으로 검증한다.
- E20~E22는 attempt 저장, claim 저장, broker 요청 경계를 강제 종료한 뒤 디스크를 다시
  열어 소비 수, claim 상태, 추가 POST 0을 검증한다.
- 장 전·마감 후에는 selection/report가 계속 생성되고 attempt 0, broker POST 0인지
  별도 통합 시험으로 고정한다.
- 배포 후 실제 EXE `--help`, package audit, GUI responsiveness, 예약작업 결과를 확인하되
  실주문 QA는 하지 않는다.

## 9. Rollout Plan

### 9.1 Migration Strategy

1. 신규 바이너리 배포 전 현재 schema 1 승인을 만료 상태 그대로 보존한다.
2. 신규 바이너리 시작 시 schema 1은 자동 승인되지 않고 재승인 필요 상태가 된다.
3. 사용자의 명시 승인 요청에서 schema 1을 timestamped archive 후 제거한다.
4. 배포된 GUI는 신규 바이너리를 적용하기 위해 한 번 재시작한다.
5. `authorize-live-session`으로 다음 적용 거래일의 schema 2 승인을 발급한다. 이후
   실행 중 승인 또는 `revoke-live-session` 취소는 다음 `start_cycle`에서 hot reload되며
   추가 재시작이 필요 없다.

### 9.2 Feature Flag

N/A. live authorization 핵심 안전 계약이므로 이중 정책을 장기 유지하지 않는다.

### 9.3 Rollback Plan

- 구버전 복귀 전 schema 2 승인 파일을 timestamped archive 후 제거한다.
- 구버전은 새 60분 형식 승인을 다시 받아야 하며 schema 2를 재사용하지 않는다.
- 미해결 주문/claim/reconciliation 상태가 있으면 rollback과 신규 승인을 모두 차단한다.

## 10. Dependencies & Risks

### 10.1 Dependencies

| Dependency | Owner | Status | Risk if Delayed |
|---|---|---|---|
| NASDAQ calendar / `pandas_market_calendars` | existing runtime | available | session binding fail-closed |
| `LiveAuthorizationStore` file lock | existing runtime | available | concurrent attempt safety unavailable |
| existing AutomaticOrderGuard | existing runtime | available | broker POST prohibited |

### 10.2 Risks

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| 장시간 승인으로 주문 표면 증가 | Medium | High | 거래일 한정, 실제 주문 의도 12회, 일일 주문 한도 유지 |
| 평가주기와 주문의도 횟수 의미 혼동 | Medium | Medium | 필드와 reason을 `attempts`로 명명, schema 2 |
| 달력 오류/시간대 오류 | Low | High | aware clock, NASDAQ calendar, boundary tests |
| rollback이 schema 2를 오해 | Low | High | archive+clear 후 fresh old-format approval |

## 11. Success Metrics

| Metric | Baseline | Target | Measurement Method |
|---|---|---|---|
| 승인 후 장중 시간 만료 차단 | 60분 뒤 발생 | 0건 | block audit |
| 무주문 평가로 attempt 소비 | 주기마다 1 | 0 | store counter |
| 장 밖/다음날 POST | 0 | 0 유지 | fake broker + audit |
| 13번째 주문 의도 POST | 기존 cycle 차단 | 0 | concurrency/integration test |

## 12. Open Questions

없음. 사용자는 거래일 정규장 종료까지의 승인 방식을 승인했고, 실제 주문 의도 12회
상한과 기존 주문 안전장치는 유지한다.
