# T1: Runtime State and Scheduling

**PRD Ref**: US-2
**Priority**: P1
**Size**: M
**Status**: In Progress

## Acceptance Criteria

- Derive the latest completed Nasdaq market date from the exchange calendar.
- Persist the last successfully learned date with backward compatibility.
- Schedule learning only when those dates differ.

## TDD Spec

| Test | Red condition | Expected |
|---|---|---|
| `test_latest_completed_market_date_ignores_open_session` | helper absent | previous closed session date |
| `test_learning_market_date_survives_restart` | field absent | date round-trips |
| `test_completed_learning_runs_once_per_completed_market_date` | hard-coded availability | one call across two cycles |

Files: `market_hours.py`, `operating_state.py`, `controller_operations.py` and
their corresponding tests. Write the marker only after a completed result;
blocked, failed, and cancelled results remain retryable. Holidays use the latest
calendar close and legacy state files default the field to empty.
