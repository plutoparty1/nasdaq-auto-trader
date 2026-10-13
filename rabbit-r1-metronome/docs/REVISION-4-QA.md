# Revision 4 검증

앱30069bytes, SHA-256 `f5576f8abee85e62c294afaf9ca043d7033d1388eef4e46cee31f1f5f3eea39d`.

- 단위12/12 PASS, syntax/build PASS.
- 실제 Chrome17/17 PASS(30.6초). 체크박스 실제AudioContext running/gain1 유지, 체크 시pulse, 해제즉시pulse해제와650ms재발없음, 무음gain0/pulse·다시소리gain1/pulse, 재시작/곡설정복원 검증.
- checkbox·이전저장defaultfalse 회귀는 기존 빌드RED 확인 후GREEN. 잘못된boolean(null/1/string)은설정·곡모두거부.
- 네 화면×240/375/768/1280 및5상태 캡처21개 새로 저장.

독립검토: 코드/설계 PassA PASS, 목표/시각/CJK PassB PASS(21개 캡처 직접확인), 실제사용25/25 PASS(추가5개 캡처 직접확인), 보안PASS, 맥락PASS. 모든5검토영역에 차단이슈 없음.

런타임감사: H1확인—기존pulse조건mute단독을mute||flashWithSound로확장, part0조건유지. H2확인—새flag를decode/settingsOnly/songload에명시해이전저장false·새저장true복원검증. H3기각—checkbox만바꿀때AudioContext계속running/gain1, 기존audio.configure의timingChanged는오디오설정만참조해서재시작하지않음.

기존privateowner1명/그룹0접근확인. 물리r1기기검증미수행. 비공개 버전4 배포 succeeded. 기존URL/QR 유지. [배포 기록](DEPLOYMENT.md).

[코드 검토](../qa/revision-4/code-review.md) · [시각/CJK 검토](../qa/revision-4/goal-visual-review.md) · [실제 사용 검증](../qa/revision-4/manual-review.md). 실제48kHz context1개, master1, triplet interval83.333ms 연속·취소0, quarterpulse약250ms·0.62/110ms. 초기 capture단계 probe는 app changehandler 실행 전 microtask에서 측정해1회 실패했으며, target후 bubble과nexttask로 측정경계를 수정한 뒤 동일 앱해시에서25개 전체 통과. 엄격한 handler후동기검증은0.200ms내flash=false, 소리/재생유지. 첫 소스push는 단기토큰만료403으로 실패; 새credential로 공식workflow재실행, sourcepush/save/privateDeploy 성공. 토큰은 메모리/stdin에만 사용. ZIPindex와배포index해시일치.
