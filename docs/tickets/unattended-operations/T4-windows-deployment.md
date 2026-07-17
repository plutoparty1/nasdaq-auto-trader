# T4: Windows 감시 작업과 배포

**PRD Ref**: PRD-unattended-operations > US-1
**Priority**: P0
**Size**: M
**Status**: Done
**Depends On**: T2, T3

## 1. Objective

현재 사용자 권한의 Windows 작업 스케줄러에 5분 감시 작업을 등록하고 설치 EXE와 설정을 안전하게 배포한다.

## 2. Acceptance Criteria

- [x] 작업은 현재 사용자 InteractiveToken과 제한 권한으로 등록된다.
- [x] 작업 인수·XML에 브로커 자격증명이 없다.
- [x] 동일 EXE가 실행 중이면 새 프로세스를 시작하지 않는다.
- [x] 배포 시 기존 `.env`와 GUI 설정을 보존한다.
- [x] 작업 등록 직후 프로그램이 실행되고 응답한다.

## 3. TDD Spec (Red Phase)

| # | Test Name | Type | Description | Expected |
|---|-----------|------|-------------|----------|
| 1 | `test_watchdog_script_contains_no_credentials` | Static | 스크립트 검사 | 키 이름/값 없음 |
| 2 | `test_watchdog_targets_exact_installed_executable` | Static | 경로 계약 | 정확한 Path 비교 |
| 3 | `test_build_copies_unattended_scripts` | Packaging | dist 검사 | 두 스크립트 포함 |
| 4 | `test_scheduler_descriptor_has_logon_and_five_minute_triggers` | Contract | DescribeOnly JSON | 두 trigger 확인 |
| 5 | `test_scheduler_descriptor_uses_limited_interactive_current_user` | Security | DescribeOnly JSON | 최소 권한 principal |
| 6 | `test_scheduler_descriptor_ignores_parallel_instances_and_quotes_paths` | Contract | 공백 포함 설치 경로 | IgnoreNew/정확한 인수 |
| 7 | `test_exported_task_contract_contains_no_secret_material` | Security | descriptor/XML/action args | key/token/account 없음 |

## 4. Implementation Guide

| File | Change Type | Description |
|------|------------|-------------|
| `scripts/ensure_unattended_running.ps1` | Create | 프로세스 부재 감시 |
| `scripts/install_unattended_task.ps1` | Create | 작업 등록/검사 |
| `scripts/build_gui_exe.ps1` | Modify | 운영 스크립트 패키징 |

## 5. Edge Cases

- 설치 경로에 공백이 있어도 인수를 올바르게 전달한다.
- 작업 등록 실패는 EXE 배포와 분리해 명확히 보고한다.
- 등록 스크립트는 `-DescribeOnly`에서 실제 등록과 같은 action/trigger/principal/settings 계약을 JSON으로 출력한다.

## 6. Review Checklist

- [x] 정적 Red/Green 확인
- [x] 실제 작업 등록·조회 확인
- [x] EXE 수동 QA
- [x] `.env` 해시 보존 확인
