# Revision 4 Goal + Visual/CJK Review

recommendation: PASS

blockers: none

## Original intent

Add one native settings checkbox, named `소리 재생 중에도 화면 깜빡임`, that lets the existing visual pulse run while sound is playing. It must default off, persist in settings and saved songs, migrate old saved data to false, reject non-boolean saved values, stop sound-on flashing immediately when unchecked, and keep muted playback flashing regardless of the checkbox. The UI must still fit 240×282 and avoid Korean clipping.

## Desired outcome

The shipped artifact remains the same PULSE r1 metronome with only the small checkbox addition. The final build checked here is `dist/index.html`, 30,069 bytes, SHA256 `f5576f8abee85e62c294afaf9ca043d7033d1388eef4e46cee31f1f5f3eea39d`. `qa/browser-results.json` reports 17 expected, 0 unexpected, 0 skipped, 0 flaky, duration 30,625.947 ms.

## Requirement mapping

| Requirement | Verdict | Evidence |
|---|---:|---|
| Native checkbox with required Korean label. | PASS | `index.html:35` adds `<input id="flash-with-sound" type="checkbox">` inside a label with `소리 재생 중에도 화면 깜빡임`; `tests/app.spec.js:377-380` finds it by role/name and confirms default unchecked. |
| Off by default and legacy data becomes false. | PASS | `src/core.js:5` sets `flashWithSound: false`; `src/core.js:49-50` returns `value.flashWithSound ?? false`; `tests/core.test.mjs:78-87` verifies old settings and old songs migrate to false while preserving song identity. |
| Invalid saved values are rejected. | PASS | `src/core.js:41-45` only permits missing legacy value or boolean. `tests/core.test.mjs:88-91` rejects null, number, and string values for settings and songs. |
| Sound-on playback flashes only when selected and keeps audio gain 1. | PASS | `src/app.js:33-39` flashes only on quarter ticks when `mute || flashWithSound`. `tests/app.spec.js:381-391` observes no flashes while unchecked, flashes after checking, `AudioContext.state === running`, and master gain `1`. |
| Unchecking stops current flash immediately. | PASS | `src/app.js:111-117` clears the timer and removes `#app.flash` when both mute and flash-with-sound are false; `tests/app.spec.js:393-397` verifies no class and no new flash count after uncheck. |
| Muted playback still always flashes. | PASS | `src/app.js:33` keeps `mute` as an independent flash trigger; `tests/app.spec.js:398-400` observes flashes after mute is enabled with master gain `0`. `qa/screens/silent-playing.png` still shows the muted pulse state. |
| Preference persists in app settings and saved songs. | PASS | `src/app.js:102` reflects setting into the checkbox, `src/app.js:141-142` restores saved song `flashWithSound`, and `tests/app.spec.js:401-417` verifies reload and saved-song restoration. |
| 240×282 settings layout fits. | PASS | `src/style.css:69-71` tightens the sound note and defines a 44px row with a 20px native checkbox. `qa/screens/240-settings.png` and `qa/screens/sound-flash-settings.png` show the full one-line label and help text inside the nav boundary. |
| Pulse remains quarter-only .62/110 ms behind controls. | PASS | `src/style.css:9` keeps `--pulse-peak: 0.62` and `--pulse-duration: 110ms`; `src/app.js:33` gates on `tick.part === 0`. Existing browser pulse test remains passing. |
| No redesign or CJK regression across requested screens. | PASS | Directly opened all 21 captures. No Korean clipping, tofu, detached particles, one-syllable orphan, clipped baseline, header/nav overlap, or unintended layout redesign found. |
| Physical and hosting scope is not overstated. | PASS with gap | Root reported private owner/custom access preserved. This review did not deploy. Physical r1 OS keyboard, wheel/button hardware, speaker timbre, native storage, and QR installation remain unverified. |

## Fresh artifacts directly inspected

Source and build evidence inspected:

- `docs/REVISION-4.md`
- `index.html`
- `src/core.js`
- `src/app.js`
- `src/style.css`
- `tests/core.test.mjs`
- `tests/app.spec.js`
- `qa/revision-4/baseline/*` diff for the bounded delta
- `dist/index.html` final hash and byte count
- `qa/browser-results.json` 17/17 browser pass
- Local `npm test`: 12/12 pass
- Local `npm run check`: JavaScript syntax checks passed

Screenshots opened and inspected:

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
- `qa/screens/sound-flash-settings.png`

## Visual/CJK Pass B findings

PASS. The new checkbox row fits the 240px settings page, the label stays on one line, and the help text remains above the nav. The checked sound-flash capture shows readable content during the orange pulse, with header and nav clear. The four responsive page sets remain centered and unchanged, and the special states remain readable.

No CJK clipping, tofu, detached particle, one-character orphan, clipped baseline, or unnatural break was visible in the requested capture set.

## Slop and maintainability pass

The Revision 4 delta is small and localized. The new boolean is validated at the saved-data boundary, reflected through existing settings refresh, saved/restored through the existing library path, and reused by the existing pulse path. I found no duplicate mute/volume control, speculative abstraction, implementation-mirroring extraction, deletion-only test, tautological test, or scope drift.

## Evidence gaps

- Physical r1 hardware was not attached; native OS keyboard, physical wheel/button wiring, speaker/perceived timbre, QR scan installation, and on-device storage remain unverified.
- Hosting/private access was not changed by this review; root reported private owner/custom access confirmation, but I did not perform an external Sites permission query.

## Final user-outcome review

PASS. The single-checkbox Revision 4 request is satisfied in source, tests, browser evidence, and the fresh screenshot set. No blocking visual, CJK, source, or artifact-freshness issue remains.
