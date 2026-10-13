# 비공개 배포 및 설치 QR

사용자 선택: 비공개 유지. 접근 권한을 공개로 변경하지 않았다.

- URL: https://pulse-r1-metronome.plutoparty.chatgpt.site
- 상태: succeeded
- 최신 버전: 4 · 소리와 화면 깜빡임 체크박스
- 배포 확인: 2026-10-09T11:59:44.433989+00:00
- 앱 SHA-256: `f5576f8abee85e62c294afaf9ca043d7033d1388eef4e46cee31f1f5f3eea39d`
- project_id: appgprj_6ac8bef96d148191b15ccb382f1f6204
- version_id: appgprj_6ac8bef96d148191b15ccb382f1f6204~appgver_342518ca0afc8191bcda0fdffd9b743d
- deployment_id: appgdep_6ac8d7233a8081918d5f38d46f144a69
- 소스 커밋: c8d0364b558142f4146e776bcf248666001a8536
- 체크아웃: published-site (메트로놈 배포 파일만 포함, 기존 트레이더와 별도)
- QR: ../qa/pulse-r1-install-qr.png
- QR 데이터: ../qa/pulse-r1-install-qr.json

공식 rabbit Creation JSON 형식의 QR이다. 비공개 Sites 접근에는 로그인이 필요하다. r1에서 해당 로그인을 통과할 수 있는지, QR 설치 및 앱 실행은 실물 기기로 확인하지 않았다. 로그인 없이 r1에서 실행 가능한 공개 설치 QR로 간주하면 안 된다.

Windows 포장 과정에서 Git Bash PATH, 지원되는 static.directory=dist, GNU tar의 Windows 드라이브 경로 인식 문제를 확인했다. Git bin을 PATH에 추가하고 TAR_OPTIONS=--force-local로 실행한 공식 site-workflow가 종료0, 네이티브 저장 및 비공개 배포가 succeeded를 반환했다. 비밀 토큰은 세션 메모리와 stdin으로만 전달했고 저장하지 않았다.
