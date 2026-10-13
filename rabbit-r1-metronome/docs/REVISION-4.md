# Revision 4 · 소리와 화면 깜빡임 함께

수용 기준: 소리 설정에 체크박스 추가, 기본 꺼짐. 소리 상태에서 켜면4분음표마다 기존 .62/110ms 펄스, 끄면 즉시 펄스 해제. 재생/음량/박자 스케줄은 유지. 무음 상태는 기존처럼 항상 깜빡임. 선택은 설정·곡과 저장/복원하며 이전 데이터는 false로 기본값 지정. 잘못된 boolean은 거부. 240×282에서 한 줄 라벨/44px 터치행, 키보드/라벨 클릭 지원. 기존 비공개 URL/QR 유지.

계획:
- [완료] 회귀 RED → 체크박스·상태·저장 구현.
- [완료] 단위12/브라우저17/실제사용25 PASS, 모든5검토 영역 PASS.
- [완료] 비공개 버전4 배포 succeeded·패키지 갱신·해시 검증.

BOOMER-6/런타임 감사: 사운드와 pulse를 별도 boolean으로 분리해 음량 조절/중복 무음과 혼동하지 않음. H1 pulse가mute에만 묶였는지 baseline확인. H2 새boolean이decode/songload에서 유실되는지 회귀확인. H3 시각옵션변경이 audioconfigure에서 재시작/무음으로 이어지는지 실제AudioContext/gain/시간으로 확인. 기존 storagekey와 songIDs, accentpresets유지.
