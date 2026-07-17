# PRD: 무인 자동운영 및 전일 보고

**Version**: 0.1
**Author**: Codex
**Date**: 2026-07-17
**Status**: Implemented
**Size**: L

---

## 1. Problem Statement

### 1.1 Background

현재 프로그램에는 미국 정규장 상태 전환, 장후 학습, 현금 한도, 중복 주문 방지와 안전정지가 있지만 GUI를 열고 `자동매매 실행`을 눌러야 시작한다. 프로세스 종료나 Windows 재로그인 뒤 자동 복구되지 않으며 전일 작업을 한눈에 확인할 구조화 보고서도 없다.

### 1.2 Problem Definition

컴퓨터가 켜져 있는 동안 사람의 반복 조작 없이 프로그램을 유지하고, 나스닥 일정에 맞춰 학습·검증·거래 판단을 실행하며, 매일 오전 전일 운영 결과를 생성해야 한다.

### 1.3 Impact of Not Solving

개장 전 수동 실행 누락, 일시 장애 뒤 장시간 정지, 학습 및 주문 차단 원인 추적 실패가 발생할 수 있다.

## 2. Goals & Non-Goals

### 2.1 Goals

- [x] G1: Windows 로그인 및 프로세스 종료 뒤 5분 이내 자동 실행한다.
- [x] G2: 휴장일과 미국 동부 서머타임을 반영해 정규장에서만 주문 판단한다.
- [x] G3: 장후 새 완료 일봉이 있을 때만 학습하고 동일 날짜 중복 학습을 막는다.
- [x] G4: 조회·시세 사전점검 장애는 안전정지 상태에서 재시도하되 주문 결과 불명 오류는 자동 재개하지 않는다.
- [x] G5: 매일 오전 8시(컴퓨터 현지시간) 이후 최근 완료 미국 거래일 보고서를 한 번 생성한다.
- [x] G6: 단일 프로세스, 신호 키, 일일 주문 횟수, 손실률, 보유 현금 한도를 모든 무인 실행에서 유지한다.
- [x] G7: 일반 LIVE 설정과 별도의 무인 실거래 동의가 없으면 자동 시작 경로는 실주문 권한을 만들지 않는다.

### 2.2 Non-Goals

- NG1: 학습 후보를 실계좌 챔피언으로 무인 승격하지 않는다. 기존 1회 수동 승인 게이트를 유지한다.
- NG2: 이메일·텔레그램·디스코드 전송은 연결 자격증명이 없으므로 포함하지 않는다.
- NG3: Windows 서비스 계정이나 관리자 권한을 요구하지 않는다. 현재 사용자 로그인 세션에서 동작한다.
- NG4: 컴퓨터 전원 켜기 또는 절전 해제는 수행하지 않는다.

## 3. User Stories & Acceptance Criteria

### US-1: 무인 자동 시작

**As a** 개인 운영자, **I want** 로그인 후 프로그램이 자동 실행되고 자동운영을 시작하기를, **so that** 개장 전에 버튼을 누르지 않아도 된다.

- [x] AC-1.1: 무인 운영 설정이 켜진 경우 GUI 시작 시 컨트롤러가 저장된 간격으로 실행 상태가 된다.
- [x] AC-1.2: 같은 Windows 사용자에서 두 번째 프로세스는 설치 경로와 무관하게 거래 엔진을 만들기 전에 종료한다.
- [x] AC-1.3: Windows 작업 스케줄러가 로그인 시와 5분 간격 감시에서 설치 EXE 부재를 복구한다.
- [x] AC-1.4: 무인 실거래 별도 동의가 없으면 LIVE 설정이어도 자동 시작 경로는 주문 권한을 만들지 않는다.

### US-2: 일정 기반 학습·거래

**As a** 운영자, **I want** 시장 일정에 맞춰 학습과 거래 판단이 자동 수행되기를, **so that** 휴장일이나 장외 주문 위험을 피할 수 있다.

- [x] AC-2.1: 휴장·장전·장후에는 주문 판단을 실행하지 않는다.
- [x] AC-2.2: 새 완료 일봉이 있는 장후에만 학습하고 완료 날짜를 원자적으로 기록한다.
- [x] AC-2.2a: 장후 학습을 놓치고 장전 재시작한 경우 주문보다 먼저 완료 일봉 catch-up 학습을 실행한다.
- [x] AC-2.3: 적격 실거래 챔피언이 없으면 장중 무주문 스캔만 수행한다.
- [x] AC-2.4: LIVE 설정, 환경 승인, 현금, 일일 위험 제한, 주문 확인 해제 조건을 기존 게이트에서 재검사한다.

### US-3: 장애 복구와 안전정지

**As a** 운영자, **I want** 조회 장애는 복구하되 불명 주문은 멈추기를, **so that** 가용성과 중복 주문 방지를 동시에 얻는다.

- [x] AC-3.1: 주문 전 시장자료·계좌 조회 실패는 주문 없이 다음 주기에 다시 점검한다.
- [x] AC-3.2: 주문 제출 오류 또는 결과 불명은 자동 일시정지를 유지한다.
- [x] AC-3.3: 운영 상태와 사유는 내구성 있는 JSONL 기록에 남는다.
- [x] AC-3.4: POST 전 claim 이후 프로세스가 중단되면 재시작 시 해당 신호를 `uncertain`으로 복구하고 같은 신호 재주문을 막는다.

### US-4: 전일 작업 보고

**As a** 운영자, **I want** 매일 오전 최근 완료 거래일 보고서를 받기를, **so that** 학습·주문·차단 현황을 빠르게 검토할 수 있다.

- [x] AC-4.1: 오전 8시 이후 최근 완료 거래일별 보고서를 한 번만 생성한다.
- [x] AC-4.2: 보고서에는 실행 주기, 상태 전환, 학습 후보·통과 수, 제출·차단 주문 수, 마지막 차단 사유, 계좌 스냅샷을 포함한다.
- [x] AC-4.3: 보고서는 `%LOCALAPPDATA%\NasdaqAutoTrader\reports`에 Markdown으로 보존하고 GUI에서 최신 보고서를 열 수 있다.
- [x] AC-4.4: 일부 자료가 손상되거나 없더라도 가능한 항목으로 보고서를 만들고 누락을 명시한다.

## 4. Technical Design

### 4.1 Architecture Overview

Windows 작업 스케줄러의 감시 작업이 설치 EXE의 존재를 확인하고 필요할 때 시작한다. EXE는 단일 인스턴스 잠금을 획득한 뒤 GUI를 띄운다. GUI는 저장된 무인 운영 설정으로 `AutoTradeController`를 자동 시작한다. 기존 `AutomationCoordinator`가 NASDAQ 캘린더에 따라 장전 점검, 장중 거래 또는 무주문 스캔, 장후 정산과 학습을 결정한다. 새 `RuntimeJournal`은 상태 전환과 결과를 JSONL로 기록하며 `DailyReportService`가 최근 완료 거래일의 감사 로그와 계좌 스냅샷을 합쳐 보고서를 만든다.

안전정지 분류는 다음과 같이 고정한다.

| Class | Reasons | Controller behavior |
|---|---|---|
| Recoverable pre-order | `market_data_unavailable`, `broker_unavailable`, `account_state_unavailable`가 주문 claim 전에 발생 | running 유지, 다음 주기 예약, 주문 0건 |
| Terminal order outcome | `order_outcome_audit_failed_reconcile_required`, `claim_finalization_failed_reconcile_required`, `order_outcome_and_claim_finalization_failed_reconcile_required`, `signal_key_uncertain` | paused 유지, 자동 재개 금지 |
| Terminal policy/config | `risk_config_invalid`, `session_store_corrupt`, `position_state_mismatch`, emergency stop, 미분류 예외 | paused 유지, 사용자 점검 필요 |

### 4.2 Data Model Changes

`TradingSettings`에 무인 운영 사용 여부, 주기, 일일 보고 사용 여부, 현지 보고 시각과 보존 일수를 추가한다. 기존 JSON 설정은 누락 필드에 기본값을 적용하므로 별도 마이그레이션이 필요 없다.

`unattended_live_trading_enabled`는 일반 LIVE 설정과 분리하며 기본값은 false다. 무인 주문 권한은 `live_trading=true`, `dry_run=false`, 환경 승인, 기존 전략·현금·위험 게이트와 이 별도 동의가 모두 참일 때만 생성한다.

### 4.3 API Design

외부 API 변경 없음. 내부 API는 타입이 지정된 `RuntimeJournal.append`, `DailyReportService.is_due`, `DailyReportService.generate`를 추가한다.

### 4.4 Key Technical Decisions

| Decision | Options Considered | Chosen | Rationale |
|---|---|---|---|
| 스케줄링 | 외부 cron, Windows 서비스, 작업 스케줄러+내부 상태기계 | 작업 스케줄러+내부 상태기계 | 사용자 로그인 권한으로 설치 가능하고 NASDAQ 일정 로직을 한곳에 유지한다. |
| 중복 방지 | PID 파일, 프로세스 이름, 파일 잠금 | 사용자 전역 보유 파일 잠금+작업의 IgnoreNew | 비정상 종료 시 OS가 잠금을 해제하며 다른 설치본도 같은 계좌 자동화를 중복 실행하지 못한다. |
| 보고 기준일 | 한국 달력 전일, 미국 거래일 | 최근 완료 NASDAQ 거래일 | 오전 보고 시 방금 끝난 미국장을 정확히 집계한다. |
| 실전 전략 승격 | 완전 자동, 수동 승인 | 수동 1회 승인 유지 | 검증 후보가 실계좌 권한을 스스로 획득하지 못하게 한다. |

## 5. Edge Cases & Error Handling

| # | Scenario | Expected Behavior | Severity |
|---|---|---|---|
| E1 | 주말·미국 휴장 | 주문 없이 대기하고 최신 완료 거래일 보고만 생성 | P0 |
| E2 | 서머타임 전환 | NASDAQ 캘린더의 timezone-aware 개장·마감 사용 | P0 |
| E3 | 두 프로세스 동시 시작 | 첫 프로세스만 유지, 두 번째는 엔진 생성 전 종료 | P0 |
| E4 | 조회 연결 종료 | GET 안전 재시도 후 실패 시 주문 없이 다음 주기 재점검 | P0 |
| E5 | POST 응답 불명 | 재시도하지 않고 일시정지·감사 기록 | P0 |
| E6 | 보고 자료 일부 손상 | 누락 경고를 포함한 부분 보고서 생성 | P1 |
| E7 | 오전 8시에 컴퓨터 꺼짐 | 다음 실행 시 8시 이후라면 미생성 보고서를 보충 | P1 |
| E8 | 사용자가 무인 운영을 끔 | GUI와 감시 작업은 앱을 열 수 있으나 거래 컨트롤러는 자동 시작하지 않음 | P1 |
| E9 | LIVE지만 무인 실거래 동의 없음 | 자동 운영은 점검·학습만 수행하고 실주문 권한을 만들지 않음 | P0 |
| E10 | POST 직후 프로세스 종료 | claim을 uncertain으로 복구하고 동일 신호 재제출 차단 | P0 |

## 6. Security & Permissions

브로커 키는 기존 `.env`에만 두고 스케줄러 인수·로그·보고서에 포함하지 않는다. 작업은 현재 사용자 `InteractiveToken`과 제한 권한으로 등록한다. 보고서는 event type, timestamp, 상태, 알려진 reason code, 후보·주문 개수, 합계 잔고처럼 명시된 허용 필드만 읽는다. 알 수 없는 payload, 토큰, 계좌번호, 종목별 원시 브로커 응답은 복사하지 않는다. 주문 POST는 자동 재시도하지 않는다.

## 7. Performance & Monitoring

| Metric | Target | Measurement |
|---|---|---|
| 프로세스 부재 복구 | 5분 이내 | 작업 스케줄러 마지막 실행 및 런타임 시작 이벤트 |
| 보고서 생성 | 2초 이내 | 런타임 이벤트 timestamp |
| 중복 프로세스 | 0 | 단일 인스턴스 테스트 및 프로세스 검사 |
| 중복 보고서 | 거래일당 0 | 원자적 파일 생성과 파일명 유일성 |

운영 상태 전환, 자동 시작, 학습 결과, 보고 생성과 복구 가능 오류만 구조화 기록한다. 자격증명과 원시 응답은 기록하지 않는다.

## 8. Testing Strategy

단위 테스트로 시각 판정, 보고 idempotency, JSONL 손상 허용, 단일 인스턴스, 복구 정책과 설정 검증을 고정한다. 통합 테스트로 GUI 자동 시작과 보고 결과 렌더링을 검증한다. 실제 QA는 주문 없는 드라이런, 빌드 EXE 실행, 작업 스케줄러 상태, 프로세스 중복 방지를 확인한다.

## 9. Rollout Plan

기존 설정 파일에 새 필드를 병합 저장하고 사용자의 현재 설정에서 무인 운영만 켠다. EXE와 감시 스크립트를 설치 폴더에 배포한 뒤 현재 사용자 작업을 등록한다. 문제 시 작업을 비활성화하고 `unattended_operation_enabled=false`로 저장하면 기존 수동 실행으로 즉시 복귀한다.

## 10. Dependencies & Risks

| Dependency | Owner | Status | Risk if Delayed |
|---|---|---|---|
| Windows Task Scheduler | Microsoft/OS | Available | 자동 재시작 불가 |
| pandas_market_calendars NASDAQ | Project | Existing | 휴장·시간 판정 차단 |
| KIS API | External | Existing | 조회/주문 안전정지 |

주요 위험은 오작동 자동 재시작과 중복 주문이다. 단일 인스턴스, 주문 신호 claim, POST 무재시도, 결과 불명 시 자동정지로 완화한다.

## 11. Success Metrics

| Metric | Baseline | Target | Measurement Method |
|---|---|---|---|
| 수동 개장 시작 필요 | 매일 | 0회 | 자동 시작 이벤트 |
| 전일 보고서 | 없음 | 거래일당 1개 | reports 디렉터리 |
| 자동 복구 가능한 조회 장애 후 영구 정지 | 가능 | 0건 | 상태 전환 기록 |
| 안전장치 우회 주문 | 0 | 0 | 자동 주문 감사 로그 |

## 12. Open Questions

- 외부 보고 전송 채널은 자격증명과 수신처가 제공될 때 별도 기능으로 추가한다.
