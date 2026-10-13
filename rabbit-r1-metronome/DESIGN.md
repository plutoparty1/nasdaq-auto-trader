# PULSE: rabbit r1 metronome

## 0. Research Log
- Official rabbit Creation SDK, commit `62ef8b37de9c8ec74499987eeed1f07b9cfaaaf0`: 240×282 viewport, native `scrollUp`, `scrollDown`, `sideClick`, Base64 persistent storage. This device constraint governs layout.
- Embedded shortlist: Raycast (instrument chrome), Spotify (music navigation), Linear (dense controls). Pick: Raycast. Read its full reference and taste-skill; keep restrained inset highlights and dark controls, substitute rabbit orange, use system fonts to avoid loading latency on r1. Marketing-specific taste rules do not apply to this device utility.
- Lazyweb endpoint preliminary request returned HTTP 404. No screens viewed; unavailable research is not visual evidence. Official device dimensions and native SDK demo are the concrete reference.
- Bitmap concept drafts omitted for this control-only, constrained device UI. No bitmap assets are needed for its functional surface.

## 1. Brief and personas
A musician can set a tempo, subdivide a 4/4 bar, measure taps continuously in real time, and recall songs with one hand. Small-screen, silent-practice, Korean-input, keyboard, and reduced-motion users must complete the same actions.

## 2. Tokens
- Canvas `#07080a`, surface `#15171a`, lifted `#202328`, border `#363a40`.
- Text `#f9f9f9`, secondary `#b7bcc4`, muted `#949ba5`.
- Accent `#ff9a52`, pressed `#ffb37d`, accent ink `#17100a`, tint `#302116`.
- Error `#ffb4ab`, focus `#ffb37d`.
- Pulse color `#fe5000`, peak opacity0.62, duration110ms.
- Body system sans (`Arial`, `Malgun Gothic`, sans-serif); numbers system monospace. No remote fonts.
- Type sizes 10, 11, 12, 13, 16, 20, 48px. Medium body, bold headings, tabular tempo.
- Spacing 2, 4, 6, 8, 10, 12, 16, 20, 24px. Radius 4px small, 8px controls, 12px preview.
- Interactive depth: inset top white highlight and bottom dark inset. Background stays dark except for the meaningful silent beat pulse.

## 3. Layout
At 240×282: header 32px, content 210px, navigation 40px. Home centers a 72px tempo control, 32px beat selectors, and 44px subdivision selector, with 12px gaps and 8px vertical padding. Playback uses only the r1 side button. Other pages scroll inside their 210px content pane. The outer screen never scrolls horizontally. Larger browsers center the same device surface, without scaling touch coordinates.

## 4. Content and states
All app labels and errors are English; music subdivision controls use ♩, ♪, and 3. Loading, empty library, invalid BPM, insufficient taps, storage failure, and audio failure each have visible states. Never insert song titles through HTML parsing.

## 5. Reusable primitives
- Button: base, orange primary, selected (`aria-pressed`), disabled, focus, hover, active.
- Segmented controls: ♩ / ♪ / 3; Drum / Melody. Selected border, fill and text; not color alone.
- Beat button: 1–4, pressed for accent and separate playing indicator. At least 30px high at this device size.
- Input: visible label or accessible name, focus ring, inline invalid message; numeric keyboard for BPM.
- Song row: truncated display title, complete accessible name; separate 44px delete action with inline confirmation.
- Status: transient notifications occupy the reserved 40px footer/navigation slot, never the content or action area; two lines maximum and no pointer blocking. Navigation remains operable and reappears after three seconds. Polite live region; never announce every audible beat.
- Navigation: Tempo, Tap, Setting, ★ tabs with `aria-current`, 40px height.

## 6. Motion
No idle animation. Beat indicator follows the audio clock. In silent mode each quarter note drives a pronounced orange wash (#fe5000, peak opacity0.62, duration110ms, held for the first55%). It sits behind the live page controls, covers only the content pane and passes pointer events; header and navigation remain clear. During a pulse, content secondary text uses the foreground token (#f9f9f9), keeping small labels above 4.5:1 contrast at the orange peak. These values are reusable pulse tokens. Reduced motion retains a gentler discrete wash at opacity0.2 without fades. Fast subdivisions change the active beat indicator without additional screen flashes.

## 7. Accessibility
Keyboard Tab/Enter and arrows for BPM outside inputs; the r1 side button alone toggles playback. Native inputs and buttons have clear focus rings and high contrast. Tempo +/- and delete targets are 44px. Compact 28–40px subdivision/beat/navigation targets are an intentional device-size constraint. Text-entry panes can scroll when the on-device keyboard reduces viewport height.

## 8. Verification and limitations
Capture actual pages at 240×282 and 375/768/1280 desktop previews, including playback, mute, triplets, tap result, Korean saved song, invalid input and delete confirmation. Hardware event and native-storage mocks prove the documented integration contract; physical r1 audio output and QR installation require the device and a reachable hosted URL.

## 9. Revision 2 interactions
Reverse native/PC wheel direction; no application volume control or duplicate mute row. Top mute toggle is the sole mute control. Sound modes each have exactly accent/regular sounds; subdivisions use the regular sound. Real-time tap displays BPM from the second tap and applies every valid estimate immediately, averaging the latest four intervals. Reset or a gap over four seconds begins a new series; a return button leaves the tap page. Stored songs with the removed volume field are normalized without losing their identity or other settings.

## 10. Revision 3 controls
Selecting quarter/eighth/triplet sets accent presets [first of bar]/[first of each pair]/[first of each triplet]; beat buttons remain editable, saved explicit accents restore unchanged. BPM requests the number keyboard through type=number plus inputmode=numeric, accepts only up to three ASCII digits, and ignores alphabetic, exponent, sign, decimal or mixed paste input without changing the displayed value. Number spinners are suppressed, retaining the existing 44px +/- controls. Melody accent1320Hz, regular660Hz. Tap initial/reset hint removed, measured unit BPM.

## 11. Revision 4 audible pulse option
The Setting page has one independent checkbox, “Flash with sound”, off by default, with a44px label target and20px native checkbox using the existing accent token. Selecting it adds the existing quarter pulse while sound continues. Deselecting stops the current pulse immediately when sound is on; mute always retains the pulse. Settings and songs retain the boolean, old saves default tofalse, malformed values are rejected. Visual-only changes keep the audio clock and binary gain unchanged. Sound-note spacing reduces from10px to6px to retain the210px page without clipped help.
