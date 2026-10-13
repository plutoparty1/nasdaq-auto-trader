# Revision 3 Goal + Visual/CJK Review

recommendation: PASS

blockers: none

## Original intent

Apply the small Revision 3 user-facing changes without redesigning the r1 metronome: subdivision selection should set useful accent presets while keeping beat buttons editable and saved explicit accents intact; BPM entry should request a numeric keyboard and ignore letters or mixed paste without changing the current value; melody accent should be 1320 Hz with regular 660 Hz; the initial/reset tap hint should be empty and measured results should show only `BPM`; and all existing responsive r1 screens should remain visually intact with no CJK clipping.

## Desired outcome

The current build should behave as the same PULSE r1 metronome, with the Revision 3 deltas visible and test-backed on the final artifact:

- final `dist/index.html` SHA256 `33a261057863ed6fd4e0b6c53349ec208bf76ece0ee558924213724ab2929e8b`, 29,239 bytes
- fresh browser evidence after the build, `qa/browser-results.json`: 16 expected, 0 unexpected, 0 skipped, 0 flaky, duration 28,653.817 ms, start `2026-10-09T11:26:38.101Z`
- fresh screenshots in `qa/screens` dated after the build
- no physical r1 claim beyond the documented SDK/browser contract

## Requirement mapping

| Requirement | Verdict | Evidence |
|---|---:|---|
| Selecting 8-bit and triplet applies `[accent, regular] x4` and `[accent, regular, regular] x4` while beat buttons remain editable. | PASS | `src/app.js:157-160` resets subdivision presets to all four beat accents for 8-bit/triplet and first beat only for quarter. `src/core.js:15-19` only accents `part === 0`, so all four beat accents produce the requested pair/triplet pattern. `tests/app.spec.js:327-337` covers preset selection and manual beat edit. |
| Saved explicit accents restore unchanged rather than being replaced by presets on load. | PASS | `src/app.js:136-137` loads saved `accents: [...accents]`; `src/core.js:44-49` normalizes four boolean accents; `src/library.js:20` saves explicit accent copies. `tests/app.spec.js:94-101` verifies restored saved accents. |
| BPM input requests numeric keyboard and ignores alphabetic/sign/decimal/mixed input without changing the current value. | PASS | `index.html:20` uses `type="number"`, `min="20"`, `max="300"`, `step="1"`, `inputmode="numeric"`, and digit pattern. `src/app.js:145-155` blocks non-digit key, beforeinput, and mixed paste data, and reverts bad input to `bpmDraft`. `tests/app.spec.js:339-356` exercises letters, exponent, sign, decimal, valid digits, and mixed paste. Live Chrome style probe on `dist/index.html` returned `type=number`, `inputmode=numeric`, `appearance=textfield`, focused input active with a 2px visible outline. |
| Number spinners absent while focus remains usable. | PASS | `src/style.css:46-47` sets `appearance: textfield` and hides WebKit spin buttons. Direct screenshots `qa/screens/240-home.png`, `375-home.png`, `768-home.png`, and `1280-home.png` show no visible spinner controls. Live probe reported `outlineStyle=solid`, `outlineWidth=2px`, `outlineColor=rgb(255, 179, 125)`, and active focus on the input. |
| Melody has exactly accent/regular sounds: accent 1320 Hz, regular 660 Hz; drum remains accent 150 and regular 1000. | PASS | `src/audio.js:86` maps drum to `150/1000` and melody to `1320/660`. `tests/app.spec.js:253-285` inspects actual Web Audio oscillator pitches for triplet modes and confirms no buffer source sequence. |
| Initial/reset tap subtitle removes the old “real-time BPM measurement” copy; measured result shows only `BPM`. | PASS | `index.html:28` starts `#tap-time` empty. `src/tap.js:27` uses `BPM` for measured result, and `src/tap.js:45` resets to empty. Exact-string search over `index.html`, `src`, and `dist/index.html` returned no removed initial/reset copy. `tests/app.spec.js:141`, `164`, and `358-361` cover measured and reset states. |
| Existing Revision 2 wheel direction remains intact. | PASS | `src/app.js:169-170` maps `scrollUp` to `bump(-1)` and `scrollDown` to `bump(1)`. `tests/app.spec.js:36-44` covers native events and PC wheel direction. |
| No redesign or responsive layout regression. | PASS | Directly opened all 20 fresh screenshots listed below. The r1 surface remains 240×282, desktop previews remain centered, and the four-page layout, nav, header, buttons, saved song row, delete confirmation, silent-playing state, tap-result state, and install QR page remain visually consistent. |
| CJK text does not clip, tofu, or break into harmful orphan lines in the enumerated screens. | PASS | Direct visual inspection of every listed capture found no clipped baselines, missing glyphs, one-syllable orphan line, or broken Korean semantic phrase. The empty tap subtitle leaves intentional blank space and does not create clipping. |
| Private Sites access / physical r1 scope preserved. | PASS with explicit gap | `.openai/hosting.json` still points at the existing project and no hosting/deployment files were changed by this review. Access policy is not locally represented in that file, so I did not claim a Sites permission verification. Physical r1 OS keyboard, wheel/button hardware, speaker timbre, and actual device installation remain unverified. |

## Fresh artifacts directly inspected

Build and browser evidence:

- `dist/index.html` — SHA256 `33a261057863ed6fd4e0b6c53349ec208bf76ece0ee558924213724ab2929e8b`, 29,239 bytes, timestamp before screenshots.
- `qa/browser-results.json` — 16/16 expected browser scenarios passed with no unexpected failures.
- `npm test` — 11/11 Node tests passed locally.
- `npm run check` — JavaScript syntax checks passed locally.
- `qa/revision-3/manual-review.md` — 25/25 installed-Chrome manual QA scenarios passed on the same final hash, including actual keyboard empty/backspace/246/max-three/English-preserve cases, audio patterns for drum and melody across quarter/eighth/triplet, saved custom accents, legacy volume migration, slow native writes, tap timing, and pulse/reduced-motion states.
- `qa/revision-3/code-review.md` — bounded Revision 3 code quality review reports PASS/CLEAR/APPROVE with no blockers over the same scoped delta and final hash.

Screenshot set inspected:

- `qa/screens/240-home.png`
- `qa/screens/240-tap.png`
- `qa/screens/240-settings.png`
- `qa/screens/240-library.png`
- `qa/screens/375-home.png`
- `qa/screens/375-tap.png`
- `qa/screens/375-settings.png`
- `qa/screens/375-library.png`
- `qa/screens/768-home.png`
- `qa/screens/768-tap.png`
- `qa/screens/768-settings.png`
- `qa/screens/768-library.png`
- `qa/screens/1280-home.png`
- `qa/screens/1280-tap.png`
- `qa/screens/1280-settings.png`
- `qa/screens/1280-library.png`
- `qa/screens/silent-playing.png`
- `qa/screens/tap-result.png`
- `qa/screens/delete-confirmation.png`
- `qa/screens/install-qr.png`

Visual findings:

- Home screens: BPM input remains visually centered and spinner-free at all four viewport captures; 240px remains dense but readable.
- Tap screens: initial tap subtitle is empty as intended, no clipping from the removed line, and tap-result shows `120` with `BPM` only.
- Settings screens: copy and controls remain unchanged; no CJK clipping or duplicate mute/volume UI appears.
- Library screens: saved Korean/Latin mixed title remains in a single-row clipped label where expected; delete confirmation status fits the reserved footer/status area.
- Special states: silent-playing preserves the stronger pulse state without covering the header/nav; delete-confirmation remains XSS-safe visually; install QR page content is readable and not clipped in the captured desktop viewport.

## Slop and maintainability pass over the Revision 3 delta

I reviewed the bounded diff against `qa/revision-3/baseline` using the remove-ai-slops/programming criteria. I did not find excessive or tautological production code, deletion-only tests, implementation-only tests, unnecessary parsing/normalization, new speculative abstraction, dead code, or scope drift in the Revision 3 changes.

The added input guards are boundary handling for real browser input paths rather than redundant interior validation: keydown, beforeinput, paste, and input validity cover distinct browser event cases. The new tests assert observable user outcomes: visible accent button state, actual Web Audio oscillator frequencies, and displayed BPM value stability under invalid keyboard/paste input. `tests/app.spec.js` is already a large browser scenario file, but the Revision 3 additions are two narrow user-outcome tests in the existing suite rather than a new oversized abstraction or duplicate test harness.

## Evidence gaps

- Physical r1 hardware was not attached; native OS keyboard selection, physical scroll wheel/button wiring, speaker timbre, QR scan installation, and Sites account access were not physically verified.
- The local hosting config does not encode public/private audience, so private Sites access is preserved by non-mutation rather than independently proven from local artifacts.
- `qa/revision-3/visual-review.md` was not present when checked; this report is the direct visual/CJK Pass B artifact for the requested 20 fresh captures.

## Final user-outcome review

PASS. The final artifact satisfies the four Revision 3 user requests and preserves the existing r1 metronome UI. No blocking visual, CJK, source, test-shape, or artifact freshness finding remains.
