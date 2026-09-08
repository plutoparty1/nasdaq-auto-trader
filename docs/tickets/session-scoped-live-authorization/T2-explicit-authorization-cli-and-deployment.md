# T2: 명시 승인 CLI·load-only 실행·배포

**PRD Ref**: PRD-session-scoped-live-authorization > US-3
**Priority**: P0 (Blocker)
**Size**: M (2-4h)
**Status**: Done
**Depends On**: T1

---

## 1. Objective

승인 생성과 자동 주문 실행을 분리해 `authorize-live-session`만 schema 2를 발급하고,
`revoke-live-session`은 안전하게 취소한다. 모든 자동 실행 표면은 저장 승인 load-only로
동작하게 한 뒤 전체 onedir를 배포하고 오늘 대상 세션 승인을 발급한다.

## 2. Acceptance Criteria

- [x] AC-1: 정확한 확인 문구와 `1..12` max attempts에서만 승인되며 발급 명령은
  broker/market-data client와 주문/조회 API를 만들지 않는다.
- [x] AC-2: 승인/revoke 감사가 성공한 뒤에만 store를 변경하며 schema1/기존 schema2는
  timestamp archive한다. write 실패 뒤 활성 승인은 없다.
- [x] AC-3: `once`, `loop`, GUI/controller와 직접 엔진 생성은 승인 파일을 생성하지 않고
  무승인 시 `live_authorization_required`, attempt 0, POST 0이다.
- [x] AC-4: 실행 중 승인/revoke가 다음 cycle에 hot reload되고 재시작은 필요 없다.
- [x] AC-5: frozen EXE help/오입력/승인 happy path, package audit, GUI responsiveness와
  작업 스케줄러 상태가 모두 통과하며 실주문 QA는 하지 않는다.

## 3. TDD Spec (Red Phase)

### 3.1 Test Cases

| # | Test Name | Type | Description | Expected |
|---|---|---|---|---|
| 1 | `test_authorize_live_session_requires_exact_phrase` | CLI E2E | 누락/오타/정상 문구 | exit2 변경0 / exit0 schema2 |
| 2 | `test_authorize_command_never_constructs_broker_client` | Integration | client constructor sentinel | 호출 0, submitted_order false |
| 3 | `test_revoke_live_session_is_audited_and_idempotent` | CLI E2E | 두 번 revoke | exit0, broker0, 다음 cycle required |
| 4 | `test_auto_once_without_stored_authorization_is_load_only` | CLI E2E | live once + confirmation | required, file0, attempt0, POST0 |
| 5 | `test_gui_guard_hot_reloads_authorize_and_revoke` | Integration | 같은 guard 실행 중 외부 명령 | 다음 cycle에 각각 반영 |
| 6 | `test_packaged_cli_exposes_session_authorization_commands` | Frozen E2E | 실제 EXE help/오입력 | stdout 계약, 비정상 exit2 |

### 3.2 Test File Location

- `tests/test_live_session_authorization_cli.py`
- `tests/test_auto_symbol_cli.py`
- `tests/test_live_authorization_lifecycle.py`
- `tests/test_auto_symbol_packaging.py`

### 3.3 Mock/Setup Required

- 임시 `LOCALAPPDATA`, 임시 strategy artifacts/config, `NullAuditLogger`
- broker/client constructor sentinel. 실제 KIS 자격증명·network·POST는 금지한다.

## 4. Implementation Guide

### 4.1 Files to Modify

| File | Change Type | Description |
|---|---|---|
| `nasdaq_auto_trader/live_session_authorization.py` | Create | authorize/revoke application service와 JSON-safe result |
| `nasdaq_auto_trader/cli_parser.py` | Modify | authorize/revoke 명령, 이전 시간/cycle 옵션 제거 |
| `nasdaq_auto_trader/cli_main.py` | Modify | broker-free 명령 dispatch |
| `nasdaq_auto_trader/cli_automatic.py` | Modify | stored authorization load-only 계약 |
| `nasdaq_auto_trader/cli_commands_basic.py` | Modify | loop의 암묵 승인 인자 제거 |
| `README.md`, `DESIGN.md` | Modify | 운영 승인/취소/세션 경계 문서화 |

### 4.2 Implementation Steps (Green Phase)

1. CLI parser와 application service의 실패 계약부터 통과시킨다.
2. 모든 실행 표면에서 duration/cycle 발급 인자를 제거하고 load-only로 고정한다.
3. frozen package 테스트, 전체 빌드와 실제 배포 CLI 수동 QA를 수행한다.

### 4.3 Refactor Phase

- CLI dispatch가 커지면 session authorization dispatch만 독립 함수로 유지한다.

## 5. Edge Cases

- E15~E19. 확인 문구 실패, 감사 실패, archive 뒤 write 실패, 실행 중 hot reload,
  동일 binding 재발급 generation 교체를 모두 포함한다.

## 6. Review Checklist

- [x] Red: 테스트 실행 → FAILED 확인됨
- [x] Green: 테스트 실행 → PASSED 확인됨
- [x] Refactor: 테스트 실행 → PASSED 유지 확인됨
- [x] AC 전부 충족
- [x] 기존 테스트 깨지지 않음
- [x] 코드 스타일 준수
- [x] 불필요한 변경 없음
