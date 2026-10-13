# 정식 운영 승인 연결 개발 계획
사용자가 구현/배포를 명시 승인했으며 실계좌 승인과 실주문은 금지했다. 개발승인을 재질문하지 않는다.
- [completed] 기존 주문/세션승인 재사용 + 실행파일/계좌/전략/설정 binding,별도운영프로필,기본대기.
- [completed] 기존GUI로 사전점검/승인/모의/시작/신규진입중지/전체종료 구현.
- [completed] 원시시장입력→자동선정→risk→승인→KISfakewire→부분/불명확/재시작 대사 격리 시험.
- [completed] 단일정식배포 경로 deploy-operating/NasdaqAutoTrader/NasdaqAutoTrader.exe 빌드·실행검증.
- [completed] 5개독립검토 + GUI캡처 검토 + 보존확인 + 미수행실체결구분 보고.
## BOOMER-6 검토
누락: buildbinding/credentialfingerprint/초기미승인/신규진입중지보호 유지 포함.
과설계: 기존엔진/승인/registry/GUI재사용,새모델·backtester없음.
유지보수: 소유모듈분리,250LOC이하,공유파일engine_orders최소guard연결.
오류: 응답불명확failclosed/재시작persist/승인파일변경즉시감지.
위험: real store 승인금지,시험token sandbox 전용,원본보존.
일관성: strategy pinned 동일spec,기존Safe Event lock무변경.
