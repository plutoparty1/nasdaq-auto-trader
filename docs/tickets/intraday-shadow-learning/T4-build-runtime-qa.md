# T4: Build, Runtime QA, and Deployment

**PRD Ref**: US-1, US-2, US-3
**Priority**: P1
**Size**: M
**Status**: Todo
**Depends On**: T3

## Acceptance Criteria

- Full tests, source CLI/runtime scenarios, and PyInstaller build pass.
- Existing deployed `.env` remains byte-identical.
- Deployed EXE launches and an actual orderless learning run produces evidence.

## Verification Steps

Run the full unittest discovery suite, source CLI help/bad-input/happy-path
scenarios, a real KIS read-only learning invocation, PyInstaller build, deployed
EXE diagnostic launch, and verify SHA-256 of the deployed `.env` before/after.
Record executable hash and zero-order evidence. No source files are modified by
this ticket.
