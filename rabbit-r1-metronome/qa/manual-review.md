# PULSE independent manual runtime QA

Verdict: **PASS (desktop browser scope)**. 25/25 completed scenarios passed.

Started: 2026-10-09T09:54:07.749Z. Report generated: 2026-10-09T09:54:37.058Z. Node: v24.19.0. Chrome: 154.0.8037.98. Test URL: http://127.0.0.1:4186/.

Tested dist/index.html SHA-256: `03d4a21778011cb45c76be9b77fcd99dab66ba1e73775d4ad084e7b1a9ea112d`. Current SHA-256: `03d4a21778011cb45c76be9b77fcd99dab66ba1e73775d4ad084e7b1a9ea112d`. Build stable during run: **true**.

## Evidence method and limits

Installed Chrome is driven by Playwright in an isolated disposable browser context. Actual Web Audio constructors and nodes execute; transparent method forwarding records source starts/stops, frequencies and gain automation. Audio output waveform, perceived timbre, physical r1 timing, wheel/button hardware, native storage implementation, installation and speaker output are not certified. The resumed-audio delay, missing AudioContext and asynchronous native-storage bridge are controlled fault injection, clearly identified per scenario. Browser uses headless installed Chrome; rendered screenshots are fresh captures of this build. The parent-level independent visual reviewers must consume these captures before claiming the complete visual gate.

## Scenario results

| # | Scenario | Result | Exact observed values / evidence |
|---|---|---|---|
| 1 | Real Chrome corrected single-file HTTP boot | PASS | {"bpm":120,"resourceRequests":[],"playEnabled":true} |
| 2 | Real AudioContext quarter-note scheduling and accented drum frequencies | PASS | {"contexts":[{"state":"running","currentTime":1,"sampleRate":48000}],"starts":[0.035,0.28500000000000003,0.535,0.785,1.0350000000000001],"intervals":[0.25,0.25,0.25,0.25],"frequencies":[[{"method":"setValueAtTime","args":[150,0.035]},{"method":"exponentialRampToValueAtTime","args":[45,0.115]}],[{"method":"setValueAtTime","args":[1000,0.28500000000000003]}],[{"method":"setValueAtTime","args":[1000,0.535]}],[{"method":"setValueAtTime","args":[1000,0.785]}],[{"method":"setValueAtTime","args":[150,1.0350000000000001]},{"method":"exponentialRampToValueAtTime","args":[45,1.1150000000000002]}]],"master":0.6499999761581421} |
| 3 | All four accents off keeps audible regular beats | PASS | {"pressed":["false","false","false","false"],"pitches":[1000,1000,1000,1000,1000]} |
| 4 | Actual eighth-note drum subdivision uses noise sources | PASS | {"kinds":["oscillator","buffer","oscillator","buffer","oscillator","buffer","oscillator","buffer"],"starts":[2.3363333333333336,2.4613333333333336,2.5863333333333336,2.7113333333333336,2.8363333333333336,2.9613333333333336,3.0863333333333336,3.2113333333333336],"scheduledInterval":0.125} |
| 5 | Actual triplet melody frequencies cover a full four-beat bar | PASS | {"frequencies":[523.25,261.625,261.625,659.25,329.625,329.625,783.99,391.995,391.995,659.25,329.625,329.625],"starts":[3.4163333333333337,3.499666666666667,3.5830000000000006,3.666333333333334,3.7496666666666676,3.833000000000001,3.9163333333333346,3.999666666666668,4.083000000000001,4.166333333333334,4.249666666666667,4.333],"intervals":[0.083333,0.083333,0.083333,0.083333,0.083333,0.083333,0.083333,0.083333,0.083333,0.083333,0.083333]} |
| 6 | Master mute applies immediately while visual beats continue | PASS | {"immediateGainProperty":0,"processedGain":0,"automation":{"method":"setValueAtTime","args":[0,4.410666666666667],"at":4.410666666666667},"muteSelected":"true","observedPulseOpacity":0.0574174,"stoppedIndicators":0} |
| 7 | Unmute and zero-volume range update real master gain | PASS | {"zeroMaster":0,"immediateRestore":{"id":0,"value":0,"events":[{"method":"setValueAtTime","args":[0.65,0],"at":0},{"method":"setValueAtTime","args":[0.65,1.08],"at":1.08},{"method":"setValueAtTime","args":[0.65,1.1306666666666667],"at":1.1306666666666667},{"method":"setValueAtTime","args":[0.65,2.2506666666666666],"at":2.2506666666666666},{"method":"setValueAtTime","args":[0.65,2.3013333333333335],"at":2.3013333333333335},{"method":"setValueAtTime","args":[0.65,3.2106666666666666],"at":3.2106666666666666},{"method":"setValueAtTime","args":[0.65,3.3013333333333335],"at":3.3013333333333335},{"method":"setValueAtTime","args":[0.65,3.3813333333333335],"at":3.3813333333333335},{"method":"setValueAtTime","args":[0.65,4.381333333333333],"at":4.381333333333333},{"method":"setValueAtTime","args":[0,4.410666666666667],"at":4.410666666666667},{"method":"setValueAtTime","args":[0,4.581333333333333],"at":4.581333333333333},{"method":"setValueAtTime","args":[0.65,4.610666666666667],"at":4.610666666666667},{"method":"setValueAtTime","args":[0,4.650666666666667],"at":4.650666666666667},{"method":"setValueAtTime","args":[0.42,4.68],"at":4.68}]},"restoredMaster":0.41999998688697815,"volumeLabel":"42%"} |
| 8 | Pause cancels scheduled playback sources and stops future scheduling | PASS | {"immediateSourceCount":36,"after150msSourceCount":36,"cancelledSources":[{"id":4,"stops":[{"args":[1.12],"at":0.9706666666666667},{"args":[],"at":1.0213333333333334}]},{"id":9,"stops":[{"args":[2.2156666666666665],"at":2.112},{"args":[],"at":2.12}]},{"id":17,"stops":[{"args":[3.2513333333333336],"at":3.152},{"args":[],"at":3.1813333333333333}]},{"id":29,"stops":[{"args":[4.383],"at":4.261333333333333},{"args":[],"at":4.32}]},{"id":31,"stops":[{"args":[4.549666666666666],"at":4.432},{"args":[],"at":4.512}]},{"id":34,"stops":[{"args":[4.832999999999999],"at":4.712},{"args":[],"at":4.752}]},{"id":35,"stops":[{"args":[4.906333333333333],"at":4.8213333333333335},{"args":[],"at":4.8213333333333335}]}]} |
| 9 | Timing change cancels old sources and restarts at beat one | PASS | {"oldSourceCount":37,"latestCancellationTime":5.072,"newSource":{"frequency":[{"method":"setValueAtTime","args":[523.25,5.107]}],"start":[{"args":[5.107],"at":5.072}]},"oldImmediateStops":2} |
| 10 | Real AudioContext suspension stops transport and surfaces error | PASS | {"contextState":"suspended","transport":"재생 · 우측 버튼","status":"오디오가 중단되었습니다. 다시 재생하세요."} |
| 11 | pagehide cancels playback and pending tap measurement | PASS | {"tapCount":"0회","tapTime":"10초 측정","applyDisabled":true} |
| 12 | Visibility hidden event stops playback | PASS | {"stopped":"false","playingMarkers":0,"eventInjection":"document.hidden=true + visibilitychange (not physical app background)"} |
| 13 | Keyboard focus ring, arrow tempo and button Space activation | PASS | {"bpmAfterInputArrow":120,"bpmAfterButtonArrow":121,"focus":{"id":"plus","outline":"solid","width":"2px"},"stoppedAfterOneSpaceStart":true} |
| 14 | Space in song input does not start transport or change tempo | PASS | {"input":"밤 음악 ","playing":"false","bpm":"121"} |
| 15 | Decimal and out-of-range tempo error states preserve last valid tempo | PASS | {"low":{"invalid":"true","message":"20–300 사이의 정수 BPM을 입력하세요."},"decimalInvalid":"true","plusUsesPriorValidTempo":"122"} |
| 16 | Two real taps over ten seconds cannot apply insufficient result | PASS | {"elapsedMs":10049,"count":"2회","time":"4회 이상 일정하게 탭하세요","result":"다시 탭","applyDisabled":true} |
| 17 | Tap keyboard Enter and Space each add exactly one tap | PASS | {"afterEnter":"1회","afterSpace":"2회"} |
| 18 | Reduced motion disables silent wash while beat state remains | PASS | {"animation":"none","active":1} |
| 19 | All four pages render at required responsive preview widths | PASS | [{"width":240,"docWidth":240,"app":{"width":240,"height":282},"screen":"home"},{"width":240,"docWidth":240,"app":{"width":240,"height":282},"screen":"tap"},{"width":240,"docWidth":240,"app":{"width":240,"height":282},"screen":"settings"},{"width":240,"docWidth":240,"app":{"width":240,"height":282},"screen":"library"},{"width":375,"docWidth":375,"app":{"width":240,"height":282},"screen":"home"},{"width":375,"docWidth":375,"app":{"width":240,"height":282},"screen":"tap"},{"width":375,"docWidth":375,"app":{"width":240,"height":282},"screen":"settings"},{"width":375,"docWidth":375,"app":{"width":240,"height":282},"screen":"library"},{"width":768,"docWidth":768,"app":{"width":240,"height":282},"screen":"home"},{"width":768,"docWidth":768,"app":{"width":240,"height":282},"screen":"tap"},{"width":768,"docWidth":768,"app":{"width":240,"height":282},"screen":"settings"},{"width":768,"docWidth":768,"app":{"width":240,"height":282},"screen":"library"},{"width":1280,"docWidth":1280,"app":{"width":240,"height":282},"screen":"home"},{"width":1280,"docWidth":1280,"app":{"width":240,"height":282},"screen":"tap"},{"width":1280,"docWidth":1280,"app":{"width":240,"height":282},"screen":"settings"},{"width":1280,"docWidth":1280,"app":{"width":240,"height":282},"screen":"library"}] |
| 20 | Compact keyboard viewport keeps nav visible and library form scrollable | PASS | {"viewport":170,"app":{"x":0,"y":0,"width":240,"height":170,"top":0,"right":240,"bottom":170,"left":0},"nav":{"x":0,"y":130,"width":240,"height":40,"top":130,"right":240,"bottom":170,"left":0},"page":{"client":98,"scroll":181},"input":{"x":12,"y":91.78125,"width":164,"height":36,"top":91.78125,"right":176,"bottom":127.78125,"left":12}} |
| 21 | Touch pointer plus compatibility click deduplicates TAP | PASS | {"afterOneTouch":"1회","afterTwoTouches":"2회"} |
| 22 | Delayed real resume and rapid sideClick start-stop cannot resurrect playback | PASS | {"preStartState":"suspended","pending":{"label":"소리 준비 중","disabled":true},"staleResumeStopped":"false","freshRestart":"true","realResumeCalls":1} |
| 23 | Slow native storage serializes concurrent settings/save/delete snapshots | PASS | {"busy":{"saveDisabled":true,"loadDisabled":true},"maxConcurrentNativeWrites":1,"writes":[{"start":1791539671070,"bpm":80,"songs":[{"title":"느린 저장 music1","bpm":80}]},{"start":1791539671528,"bpm":140,"songs":[{"title":"느린 저장 music1","bpm":80}]},{"start":1791539672867,"bpm":140,"songs":[]},{"start":1791539673320,"bpm":160,"songs":[]}],"afterSave":{"bpm":140,"song":{"bpm":80,"subdivision":1,"sound":"drum","accents":[true,false,false,false],"mute":false,"volume":0.65,"title":"느린 저장 music1","id":"f4f113c2-ed52-4c45-a43a-5ba6645d062e"}},"afterDelete":{"settings":{"bpm":160,"subdivision":1,"sound":"drum","accents":[true,false,false,false],"mute":false,"volume":0.65},"songs":[]},"reloadBpm":160,"localStorageEntries":0} |
| 24 | Unavailable AudioContext gives actionable error and silent fallback runs | PASS | {"failedStart":{"status":"이 기기에서 소리를 사용할 수 없습니다. 무음 모드를 선택하세요.","pressed":"false"},"silentPlayingIndicators":1} |
| 25 | Single file boots directly through file URL without external dependencies | PASS | {"target":"file:///C:/Users/u/nasdaq-auto-trader/rabbit-r1-metronome/dist/index.html","requests":["file:///C:/Users/u/nasdaq-auto-trader/rabbit-r1-metronome/dist/index.html"],"pageErrors":[],"bpm":"120","appSize":[240,282]} |

## Screenshot evidence

- [all-accents-off](./manual-all-accents-off.png): Regular beats remain available when every accent is disabled.
- [triplet-playing](./manual-triplet-playing.png): Triplet playback with one current beat and subdivision marker.
- [mute-playing](./manual-mute-playing.png): Muted playback retains a visible beat indicator.
- [mute-motion-mid](./manual-mute-motion-mid.png): Silent quarter-note wash during its 160 ms pulse.
- [mute-motion-settled](./manual-mute-motion-settled.png): Pause clears playing marker and silent pulse.
- [keyboard-focus](./manual-keyboard-focus.png): Keyboard focus ring on the tempo increment control.
- [invalid-bpm](./manual-invalid-bpm.png): Visible Korean integer range error and invalid input color.
- [insufficient-tap](./manual-insufficient-tap.png): Real ten-second measurement rejects two taps and disables Apply.
- [reduced-motion](./manual-reduced-motion.png): Reduced motion leaves a discrete current beat without the wash animation.
- [240-home](./manual-240-home.png): home page at 240px viewport; same 240×282 device controls.
- [240-tap](./manual-240-tap.png): tap page at 240px viewport; same 240×282 device controls.
- [240-settings](./manual-240-settings.png): settings page at 240px viewport; same 240×282 device controls.
- [240-library](./manual-240-library.png): library page at 240px viewport; same 240×282 device controls.
- [375-home](./manual-375-home.png): home page at 375px viewport; same 240×282 device controls.
- [375-tap](./manual-375-tap.png): tap page at 375px viewport; same 240×282 device controls.
- [375-settings](./manual-375-settings.png): settings page at 375px viewport; same 240×282 device controls.
- [375-library](./manual-375-library.png): library page at 375px viewport; same 240×282 device controls.
- [768-home](./manual-768-home.png): home page at 768px viewport; same 240×282 device controls.
- [768-tap](./manual-768-tap.png): tap page at 768px viewport; same 240×282 device controls.
- [768-settings](./manual-768-settings.png): settings page at 768px viewport; same 240×282 device controls.
- [768-library](./manual-768-library.png): library page at 768px viewport; same 240×282 device controls.
- [1280-home](./manual-1280-home.png): home page at 1280px viewport; same 240×282 device controls.
- [1280-tap](./manual-1280-tap.png): tap page at 1280px viewport; same 240×282 device controls.
- [1280-settings](./manual-1280-settings.png): settings page at 1280px viewport; same 240×282 device controls.
- [1280-library](./manual-1280-library.png): library page at 1280px viewport; same 240×282 device controls.
- [compact-library](./manual-compact-library.png): 170px keyboard-like viewport retains bottom navigation and scrollable form.
- [touch-tap](./manual-touch-tap.png): Two touch taps produce two accepted tap records.
- [native-save-busy](./manual-native-save-busy.png): Slow native save disables song actions during its asynchronous write.
- [no-audio-silent-fallback](./manual-no-audio-silent-fallback.png): No AudioContext: user-selected silent playback still displays beats.
- [file-url-boot](./manual-file-url-boot.png): Direct file:// self-contained app starts and operates without network assets.

## Failures and reproduction

No completed scenario failed.

## Browser errors

```json
[]
```

## Direct visual inspection

All 30 listed screenshots were opened and inspected after the final run. Home, TAP, settings and library at 240, 375, 768 and 1280px show complete Korean labels, no missing glyphs, no horizontal overflow and consistent 240×282 controls. The invalid BPM state is legible; the focused increment button has a 2px outline; the 170px compact viewport retains the form and bottom navigation. Muted playback has a current beat plus a subtle quarter-note wash; reduced motion keeps the discrete beat without the wash. Disabled song actions communicate the slow-save state.

Cosmetic observation for the parent visual gate: `manual-touch-tap.png` captures Chrome's blue native touch highlight over the orange TAP pad immediately after a touch. Touch count and actions remain correct. An explicit `-webkit-tap-highlight-color` could keep that temporary browser feedback on the app palette. This is not a functional failure; independent parent-level visual reviewers must decide the complete UI verdict.

## QA harness corrections and debugging evidence

Three initial assertions were corrected before this final run: a raw `AudioParam.value` read can precede audio graph processing even though `setValueAtTime(value, currentTime)` has already accepted the change; filling/committing tempo can allow additional old notes to be scheduled, so new-note identification now follows the observed cancellation time; Chrome may create a running context, so delayed-resume testing now explicitly suspends the actual context first. No product changes were made for these harness corrections.

Distinguishing hypotheses were rejected or confirmed with runtime evidence: input propagation failure was rejected by a recorded 0.42 gain automation event and a visible 42% label; unexpected suspension was rejected by the actual context's `running` state; delayed graph processing was consistent with immediate gain property 0 followed by processed gain 0.41999998688697815 during playback. The final mute check records automation value 0 at exactly current audio time 4.410666666666667 and processed gain 0. Source restart is observed at 523.25Hz at 5.107 after cancellation at 5.072. Delayed resume starts from observed `suspended`, makes exactly one real resume call, and stale completion cannot restart transport.

Cleanup verification: `Get-NetTCPConnection -LocalPort 4186 -State Listen` returned no listener after the final run. All owned browser contexts were closed. No product/test files were changed by this assignment.

## Artifact and process ledger

Writes were limited to qa/manual-review.md, qa/manual-driver.mjs, and listed qa/manual-*.png screenshots. No product/test edits. Owned preview child PID: 25892. Cleanup status: browser/context closure and owned child termination executed in finally. Root port 4173 was untouched.
