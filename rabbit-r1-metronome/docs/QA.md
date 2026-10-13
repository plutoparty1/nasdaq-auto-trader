# PULSE 검증 보고서

초기 버전 검증 기록입니다. 현재 실시간 탭·소리 변경 검증은 [Revision 2 보고서](REVISION-2-QA.md)에 기록합니다.

## 완료된 자동 검증
- 독립 정적 앱: 240×282. 외부 런타임 파일이나 서버 API 호출 없음.
- npm test: **9/9 PASS**. 리듬·10초 탭·유니코드 저장·잘못된 데이터·단일 HTML 구문·잘못된 미리보기 URL 회귀 검증.
- npm run check: 전체 소스/스크립트/테스트 JavaScript 구문 정상.
- npm run test:browser: **11/11 PASS**, 실제 설치된 Chrome. 항상 최신 빌드를 생성한 뒤 실행.
- 추가 실행 QA: **25/25 PASS**, [실행 보고서](../qa/manual-review.md).
- npm audit: 최종 개발 의존성까지 취약점 **0건**.
- 240 / 375 / 768 / 1280 너비의 모든 화면 캡처. [화면 증거](../qa/screens/), 추가 30개 수동 실행 캡처는 qa/manual-*.png.

## 실제 동작 증거
- 10초간 750ms 간격의 14회 탭에서 약 80 BPM을 표시하고 적용.
- 실제 Web Audio: 48 kHz AudioContext. 240 BPM의 4분음표 간격0.25초, 8분음표0.125초, 셋잇단0.083333초.
- 드럼 강조150→45 Hz, 일반 클릭1000 Hz, 8분 하이햇 노이즈. 멜로디 셋잇단12개 이벤트 확인.
- 무음은 현재 오디오 시각에 master gain0 설정 및 실제 처리값0. 시각 박자는 계속 표시.
- 450ms 느린 native 저장에서도 쓰기 최대 동시 실행1. 저장80/현재140, 삭제/현재160이 정확히 복원. localStorage 사용0.
- 실제 suspended AudioContext의 지연 resume 중 우측 버튼 빠른 재클릭 후 재생이 되살아나지 않음. 다음 클릭은 정상 시작.
- 단일 HTML file:// 실행에서 페이지 자체 외 요청0, JavaScript 오류0. 오디오 API 없음에서도 무음 동작.
- 잘못된 URL이 미리보기 서버를 종료하지 않고400을 반환. 경로 이탈 요청404.

## 발견 후 수정한 결함
1. 단일 HTML 코드 삽입 중 String.replace의 $& 치환으로 브라우저 구문 오류 발생. 콜백 삽입으로 수정, 구문 회귀 검사와 Chrome 시작 검증으로 보호.
2. 탭 완료 안내가 결과 버튼을 가림. 결과 표시 자체로 안내하고 기타 상태 메시지는 40px 푸터 영역으로 이동. 버튼을 가리지 않고 터치를 막지 않음.
3. 미리보기 서버 URL 파싱 예외로 프로세스 종료.400 응답 처리와 실제 요청 회귀 검사 추가.
4. 브라우저 검사에서 이전 dist를 사용할 위험. test:browser가 항상 빌드부터 실행하도록 수정.

## 런타임 감사의 가설과 근거
- H1 빌드가 삽입 코드를 변형함: **확인 후 수정**. 원본 실패 빌드의 script 태그3개, 실제 Chrome 오류 Unexpected token '<'; 최종 빌드 태그1개와 정상 시작.
- H2 잘못된 서버나 캐시가 원인: **기각**. 동일 파일의 file:// 실행에서도 초기 오류 재현. 최종 file:// 실행은 외부 요청과 오류0.
- H3 native 저장 또는 오디오 비동기가 잘못된 상태를 만듦: **검증한 시나리오에서 기각**. 손상 저장 데이터에서 앱은 연습 모드로 시작하고 덮어쓰기0; 느린 쓰기 직렬화 및 지연된 실제 오디오 resume의 취소 동작 통과. 실물 r1 정책은 별도 확인 대상.

## 독립 검토
- 코드: PASS, 근거 .omo/evidence/pulse-metronome-code-review.md. stale dist 검사 위험 수정.
- 보안: PASS, 최종 의존성 감사0, 제목 XSS·저장·QR·서버 요청 검증.
- SDK 및 설치 계약: PASS, 공식 고정 SHA62ef8b37de9c8ec74499987eeed1f07b9cfaaaf0.
- 실제 실행: PASS25/25. 초기3개 assertion 문제는 처리 전 AudioParam 샘플, 이전 소스 포함, 이미 running인 resume 준비 상태였으며 실측 조건 수정 후 전부 통과.
- 최종 요구사항·시각·CJK 게이트: **PASS**. 수정된 상태 메시지 위치와 8개 기능, 최종 실행 증거 및 빌드 SHA-256 확인.
- 패키지 정리 후 npm test 9/9, npm run check, npm run build, npm audit 0건 재확인. 최종 앱30844 bytes, SHA-256 `03d4a21778011cb45c76be9b77fcd99dab66ba1e73775d4ad084e7b1a9ea112d`.
- Lighthouse 성능 감사: **INCONCLUSIVE**. 저장 공간 부족과 Chrome 프로필 오류로12개 계획 중 완료0개, 점수 없음. [감사 기록](../qa/lighthouse-summary.md), [시도 JSON](../qa/lighthouse-attempts.json). SDK 검토와 기능 검증의 PASS와 별개다.

## 범위
하드웨어 이벤트와 Creation 저장 브리지를 모의했으며 소리·DOM·타이머는 실제 Chrome에서 실행했다.
실물 r1 스피커, 기기 OS별 오디오 정책, QR 스캔 설치, 공개 배포는 수행하지 않았다.
실물 테스트가 완료됐다고 주장하지 않는다. 기존 트레이더 소스나 사용자 변경은 수정하지 않았다.
