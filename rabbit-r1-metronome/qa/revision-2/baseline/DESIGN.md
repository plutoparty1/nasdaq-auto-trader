# PULSE: rabbit r1 metronome

## 0. Research Log
- Official rabbit Creation SDK, commit `62ef8b37de9c8ec74499987eeed1f07b9cfaaaf0`: 240×282 viewport, native `scrollUp`, `scrollDown`, `sideClick`, Base64 persistent storage. This device constraint governs layout.
- Embedded shortlist: Raycast (instrument chrome), Spotify (music navigation), Linear (dense controls). Pick: Raycast. Read its full reference and taste-skill; keep restrained inset highlights and dark controls, substitute rabbit orange, use system fonts to avoid loading latency on r1. Marketing-specific taste rules do not apply to this device utility.
- Lazyweb endpoint preliminary request returned HTTP 404. No screens viewed; unavailable research is not visual evidence. Official device dimensions and native SDK demo are the concrete reference.
- Bitmap concept drafts omitted for this control-only, constrained device UI. No bitmap assets are needed for its functional surface.

## 1. Brief and personas
A musician can set a tempo, subdivide a 4/4 bar, measure ten seconds of taps, and recall songs with one hand. Small-screen, silent-practice, Korean-input, keyboard, and reduced-motion users must complete the same actions.

## 2. Tokens
- Canvas `#07080a`, surface `#15171a`, lifted `#202328`, border `#363a40`.
- Text `#f9f9f9`, secondary `#b7bcc4`, muted `#949ba5`.
- Accent `#ff9a52`, pressed `#ffb37d`, accent ink `#17100a`, tint `#302116`.
- Error `#ffb4ab`, focus `#ffb37d`.
- Body system sans (`Arial`, `Malgun Gothic`, sans-serif); numbers system monospace. No remote fonts.
- Type sizes 10, 11, 12, 13, 16, 20, 48px. Medium body, bold headings, tabular tempo.
- Spacing 2, 4, 6, 8, 10, 12, 16, 20, 24px. Radius 4px small, 8px controls, 12px preview.
- Interactive depth: inset top white highlight and bottom dark inset. Background stays dark on every screen.

## 3. Layout
At 240×282: header 32px, content 210px, navigation 40px. Home has a 12px title, 64px tempo control, 30px beat selectors, 28px subdivision selector, and 44px transport, with 4px gaps and 8px vertical padding. Other pages scroll inside their 210px content pane. The outer screen never scrolls horizontally. Larger browsers center the same device surface, without scaling touch coordinates.

## 4. Content and states
All task labels and errors are Korean; logo and BPM/TAP are short musical labels. Loading, empty library, invalid BPM, insufficient taps, storage failure, and audio failure each have visible states. Never insert song titles through HTML parsing.

## 5. Reusable primitives
- Button: base, orange primary, selected (`aria-pressed`), disabled, focus, hover, active.
- Segmented controls: 4분 / 8비트 / 셋잇단; 드럼 / 멜로디. Selected border, fill and text; not color alone.
- Beat button: 1–4, pressed for accent and separate playing indicator. At least 30px high at this device size.
- Input: visible label or accessible name, focus ring, inline invalid message; numeric keyboard for BPM.
- Song row: truncated display title, complete accessible name; separate 44px delete action with inline confirmation.
- Status: transient notifications occupy the reserved 40px footer/navigation slot, never the content or action area; two lines maximum and no pointer blocking. Navigation remains operable and reappears after three seconds. Polite live region; never announce every audible beat.
- Navigation: four equal text tabs, `aria-current`, 40px height.

## 6. Motion
No idle animation. Beat indicator follows the audio clock; a low-opacity accent wash pulses on quarter notes in silent mode. Reduced motion removes fades, retaining a discrete active-beat indicator. No full-screen white strobe. Fast subdivisions change the position indicator rather than flashing the entire screen.

## 7. Accessibility
Keyboard Tab/Enter, Space transport outside inputs, arrows for BPM outside inputs; native inputs and buttons, clear focus rings, high contrast. 44px transport, tempo +/- and delete. Compact 28–40px subdivision/beat/navigation targets are an intentional device-size constraint. Text-entry panes can scroll when the on-device keyboard reduces viewport height.

## 8. Verification and limitations
Capture actual pages at 240×282 and 375/768/1280 desktop previews, including playback, mute, triplets, tap result, Korean saved song, invalid input and delete confirmation. Hardware event and native-storage mocks prove the documented integration contract; physical r1 audio output and QR installation require the device and a reachable hosted URL.
