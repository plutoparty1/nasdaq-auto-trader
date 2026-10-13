# Revision 4 independent manual QA

Verdict: **PASS (installed Chrome runtime scope)**. 25/25 scenarios passed.

Started 2026-10-09T11:58:31.386Z; updated 2026-10-09T11:58:52.798Z; Chrome 154.0.8037.98; Node v24.19.0. Tested http://127.0.0.1:4173/ in private disposable contexts.

dist/index.html: 30069 bytes, SHA-256 `f5576f8abee85e62c294afaf9ca043d7033d1388eef4e46cee31f1f5f3eea39d`. Current SHA-256 `f5576f8abee85e62c294afaf9ca043d7033d1388eef4e46cee31f1f5f3eea39d`. Build stable: **true**.

Actual Web Audio contexts/nodes run with transparent method forwarding, not an audio replacement. Gain reads wait for a processing quantum. Keyboard checks use real Chrome key events. Checkbox inputs use actual browser label clicks, native checkbox changes and real keyboard Space/Tab. Pulse observations come from live runtime playback; no artificial flash class is applied. Audio scheduling and gain are measured from the running native context. Persisted malformed/legacy data use isolated fixtures. Physical r1 OS keyboard, wheel/button wiring, native storage implementation, speaker/perceived timbre and installation remain unverified. Headless installed Chrome, no new packages or Lighthouse.

## Executed scenarios

| # | Scenario | Result | Exact observed values |
|---|---|---|---|
| 1 | Default is one native unchecked accessible checkbox | PASS | {"type":"checkbox","checked":false,"count":1,"label":"소리 재생 중에도 화면 깜빡임"} |
| 2 | Settings pane fits240x282 with single-line44px label row | PASS | {"layout":{"docWidth":240,"width":240,"height":282,"paneHeight":210,"paneScroll":210,"rowHeight":44,"rowBottom":195.171875,"labelHeight":15.390625,"lineHeight":15.4,"rowWidth":216,"labelWidth":144.234375}} |
| 3 | Clicking label text checks option without starting paused playback | PASS | {"checked":true,"running":"false","flash":false} |
| 4 | Real Space toggles checkbox with visible keyboard focus | PASS | {"checked":false,"focus":{"active":true,"visible":true,"outline":"solid","width":"2px"}} |
| 5 | Real Tab reaches checkbox and next navigation control | PASS | {"first":"flash-with-sound","next":"home"} |
| 6 | Checked option stays visually quiet while transport is paused | PASS | {"pulses":[],"running":"false","contexts":0} |
| 7 | drum sound, mute=false, flashWithSound=false branch | PASS | {"context":{"state":"running","time":0.632,"sampleRate":48000},"master":1,"pulseOnsets":[],"pitches":[150,1000,1000],"checked":false} |
| 8 | drum sound, mute=false, flashWithSound=true branch | PASS | {"context":{"state":"running","time":1.912,"sampleRate":48000},"master":1,"pulseOnsets":[2976.899999976158,3226.8000000715256,3477.100000023842],"pitches":[150,1000,1000,1000],"checked":true} |
| 9 | drum sound, mute=true, flashWithSound=false branch | PASS | {"context":{"state":"running","time":3.010666666666667,"sampleRate":48000},"master":0,"pulseOnsets":[4093.5,4343.399999976158,4593.399999976158],"pitches":[150,1000,1000,1000],"checked":false} |
| 10 | drum sound, mute=true, flashWithSound=true branch | PASS | {"context":{"state":"running","time":4.181333333333333,"sampleRate":48000},"master":0,"pulseOnsets":[5243.700000047684,5493.399999976158,5743.399999976158],"pitches":[150,1000,1000,1000],"checked":true} |
| 11 | melody sound, mute=false, flashWithSound=false branch | PASS | {"context":{"state":"running","time":5.32,"sampleRate":48000},"master":1,"pulseOnsets":[],"pitches":[1320,660,660,660],"checked":false} |
| 12 | melody sound, mute=false, flashWithSound=true branch | PASS | {"context":{"state":"running","time":6.530666666666667,"sampleRate":48000},"master":1,"pulseOnsets":[7610.700000047684,7860.5,8110.300000071526],"pitches":[1320,660,660,660],"checked":true} |
| 13 | melody sound, mute=true, flashWithSound=false branch | PASS | {"context":{"state":"running","time":7.730666666666667,"sampleRate":48000},"master":0,"pulseOnsets":[8810.200000047684,9060.200000047684,9310.300000071526],"pitches":[1320,660,660,660],"checked":false} |
| 14 | melody sound, mute=true, flashWithSound=true branch | PASS | {"context":{"state":"running","time":8.792,"sampleRate":48000},"master":0,"pulseOnsets":[9876.800000071526,10126.700000047684,10376.700000047684],"pitches":[1320,660,660,660],"checked":true} |
| 15 | Audible checked subdivision1 flashes on quarter ticks only | PASS | {"onsets":[11026.899999976158,11276.899999976158,11527.100000023842,11776.800000071526],"pulseIntervals":[250,250.20000004768372,249.70000004768372],"audioIntervals":[0.25,0.25,0.25],"master":1,"context":{"state":"running","time":10.141333333333334,"sampleRate":48000},"peaks":[{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"}]} |
| 16 | Audible checked subdivision2 flashes on quarter ticks only | PASS | {"onsets":[12260.200000047684,12510.300000071526,12760.200000047684,13010.200000047684],"pulseIntervals":[250.10000002384186,249.89999997615814,250],"audioIntervals":[0.125,0.125,0.125,0.125,0.125,0.125,0.125],"master":1,"context":{"state":"running","time":11.36,"sampleRate":48000},"peaks":[{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"}]} |
| 17 | Audible checked subdivision3 flashes on quarter ticks only | PASS | {"onsets":[13493.600000023842,13743.600000023842,13993.600000023842,14243.600000023842],"pulseIntervals":[250,250,250],"audioIntervals":[0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393],"master":1,"context":{"state":"running","time":12.592,"sampleRate":48000},"peaks":[{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"},{"opacity":"0.62","duration":"0.11s","top":"32px","bottom":"40px","layer":"0","pointer":"none","labelColor":"rgb(249, 249, 249)"}]} |
| 18 | Toggling checked option retains AudioContext, gain1 and continuous triplet schedule | PASS | {"contexts":1,"beforeTime":13.232,"afterTime":14.170666666666667,"state":"running","master":1,"running":"true","intervals":[0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393,0.08333333333333393],"cancellations":0} |
| 19 | Unchecking during audible pulse clears synchronously without muting | PASS | {"change":{"before":true,"trusted":true,"checked":false,"started":16286.600000023842,"captureMicrotask":true,"after":false,"elapsed":0.20000004768371582,"nextTask":false},"master":1,"state":"running","running":"true"} |
| 20 | Pause clears checked audible pulse and current beat immediately | PASS | {"state":{"flash":false,"running":"false","playingBeats":0,"opacity":"0"}} |
| 21 | Settings persist and reload flashWithSound=true | PASS | {"saved":{"bpm":240,"subdivision":3,"sound":"melody","accents":[true,true,true,true],"mute":false,"flashWithSound":true},"checked":true,"mute":"false"} |
| 22 | Settings persist and reload flashWithSound=false | PASS | {"saved":{"bpm":240,"subdivision":3,"sound":"melody","accents":[true,true,true,true],"mute":false,"flashWithSound":false},"checked":false,"mute":"false"} |
| 23 | Saved true and false songs restore option and keep identities | PASS | {"before":[{"id":"a4110c34-833c-4812-b8ab-2153da23f2fa","title":"Flash on song","flashWithSound":true},{"id":"d0941851-28dd-4a55-87ce-82396bdcca23","title":"Flash off song","flashWithSound":false}],"trueRestored":true,"falseRestored":false,"after":[{"id":"a4110c34-833c-4812-b8ab-2153da23f2fa","title":"Flash on song","flashWithSound":true},{"id":"d0941851-28dd-4a55-87ce-82396bdcca23","title":"Flash off song","flashWithSound":false}]} |
| 24 | Legacy absent boolean defaults false while preserving old song | PASS | {"settingsChecked":false,"songChecked":false,"bpm":"80","accents":["false","true","false","true"],"saved":{"settings":{"bpm":80,"subdivision":3,"sound":"melody","accents":[false,true,false,true],"mute":false,"flashWithSound":false},"songs":[{"bpm":80,"subdivision":3,"sound":"melody","accents":[false,true,false,true],"mute":false,"flashWithSound":false,"id":"legacy-r4-song","title":"Preserved old song"}]}} |
| 25 | Wrong-type persisted option rejects both settings and song payloads | PASS | {"cases":[{"field":"settings","bad":"true","saveDisabled":true,"songCount":0,"checked":false,"status":"저장소를 읽지 못했습니다. 새로고침 후 다시 시도하세요.","bpm":"120"},{"field":"song","bad":1,"saveDisabled":true,"songCount":0,"checked":false,"status":"저장소를 읽지 못했습니다. 새로고침 후 다시 시도하세요.","bpm":"120"}]} |

## Fresh screenshot evidence

- [manual-checkbox-default.png](./manual-checkbox-default.png): Default native unchecked option; complete settings pane at240x282.
- [manual-checkbox-focus.png](./manual-checkbox-focus.png): Native checkbox focused after actual keyboard Space, with2px outline.
- [manual-audible-pulse.png](./manual-audible-pulse.png): Real running unmuted melody triplets: checked option flashes only at quarter onset.
- [manual-paused-cleared.png](./manual-paused-cleared.png): Stopping audible checked playback clears pulse and current beat.
- [manual-songs-preserved.png](./manual-songs-preserved.png): Two saved songs preserve separate true/false flash preferences and identities.

## Failures and reproduction

No scenario failed.

## Browser errors

```json
[]
```

## Cleanup and scope

All owned Chrome contexts and the browser were closed. Reused root preview 4173 read-only; no server process was launched or terminated. Only qa/revision-4/manual-* files were created. No product, test, dependency or trader edits. Parent independent visual reviewers must consume these fresh captures for the complete visual gate.

## Probe correction and direct inspection

The first pass reported 24/25 because its uncheck probe sampled a capture-phase microtask before the app target handler. Three possibilities were assessed: capture-phase sampling order, a real failure to apply the unchecked setting, and a new quarter pulse arriving during sampling. The corrected probe retained a strict post-handler synchronous-clear assertion and recorded the event phases. With a trusted native change, flash was true before the handler and in the capture microtask, then false at document bubble in 0.20000004768371582 ms and false in the next task. Checked was false, gain was 1, the context was running and transport stayed true. No product change was made. The final complete focused run passed 25/25 on the same hash. Reproduce with node qa/revision-4/manual-driver.mjs.

All five final screenshots were opened and inspected. The settings option fits one line in a 44px row with no pane overflow, keyboard focus has a visible 2px outline, the actual audible pulse retains white labels and uncovered header/navigation, stopping clears the field, and both saved song identities remain visible. Visual PASS in the bounded installed-Chrome scope. Physical r1 touch/keyboard, speaker output, native bridge and installation remain unverified.
