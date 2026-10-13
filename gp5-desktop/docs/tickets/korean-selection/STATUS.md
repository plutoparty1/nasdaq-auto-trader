# Korean GP5 and selected instruments

Current phase: complete. Test command: npm test. Windows build: npm run build:win -- --config.directories.output=release/1.1.0. Pure JavaScript syntax checks use node --check; no TypeScript conversion required.

| Ticket | Scope | Status | Acceptance/test |
| --- | --- | --- | --- |
| T1 | Import charset and PDF charset propagation | Done | 35 bundled-runtime tests; real CP949 extended/UTF-8 GP5 and all 10 PDFs pass |
| T2 | Track checkboxes and strict selected export | Done | non-contiguous/empty/invalid subsets, original numbering, keyboard, busy and cancel pass |
| T3 | Review and Windows artifacts | Done | new EXE, both final PDFs, 21-file ASAR audit, checksum and all five reviews pass |

Pre-implementation BOOMER-6 review: boundaries and ownership explicit; ambiguity in legacy bytes tested; no engine replacement; shared charset decision; subset progress carries original index; retained PDF/cancel behavior checked. No blocking design issue. Final BOOMER-6 and all five independent review results: `qa/korean-selection-review.md`. No remaining blocker.
