# Nasdaq Auto Trader Operator GUI

This desktop surface is an internal operator console for non-developers.

## Design Contract

- The GUI must not expose a live-order execution button.
- The primary state must explain whether live trading is blocked before any action is taken.
- Risk-changing actions must use plain-language labels, helper text, and confirmation prompts.
- Every action result must show a human-readable explanation first and raw JSON second.
- File paths and strategy inputs must be visible on the same screen as the action buttons.

## Visual Direction

- Operational, calm, and explicit rather than dashboard-dense.
- Warm paper background, deep green header, high-contrast safety badges.
- Use Aptos Display for hierarchy, Aptos for labels, and Cascadia Mono for JSON output.
- Avoid relying on color alone: badge text, status headlines, and checklist text must repeat the safety state.

## Safety Language

- Prefer "실주문 차단", "주문 없음", "no-trade 롤백", and "차단 사유" over abstract trading jargon.
- Never label a button "라이브 시작" or "실거래 실행" in this GUI.
- When a command can change strategy state, say what changes and require a confirmation dialog.

## Dependent Settings

- `과거 데이터 기반 종목 자동 선택` is a checkbox in the symbol section.
- When enabled, only the manual ticker and legacy AI candidate ticker entries are disabled.
- Disabled entries retain their saved values and become editable again when the checkbox is cleared.
- Automatic-selection readiness is written to the existing execution log in plain Korean; it does not add a live action.
