# GP5 악기별 PDF 변환기

**iOS·Android·PC에서는 [GP5 PDF 웹 버전](https://plutoparty1.github.io/gp5-pdf-web/)을 사용하세요.** v1.1.0은 휴대폰 파일 선택, 악기별 PDF 저장·열기·공유와 ZIP 다운로드를 지원합니다. iPhone·iPad는 Safari, Android는 Chrome에서 접속하면 됩니다. 악보 파일은 서버에 업로드하지 않습니다.

Python 실행 화면의 `모바일·웹 버전 열기` 버튼 또는 `python gp5_to_pdf.py --web`으로 웹 버전을 열 수 있습니다. 아래 Python/MuseScore 구현은 PC용이며 휴대폰에서는 웹 주소를 엽니다. 웹 소스와 모바일 안내는 [gp5-web/README.md](../gp5-web/README.md), PC 실행 파일은 [gp5-desktop/README.md](../gp5-desktop/README.md)를 참고하세요.

단일 파일 `gp5_to_pdf.py`로 실행하는 Windows용 도구입니다.

## 사용법

1. Python 3.11 이상과 무료 [MuseScore Studio 4](https://musescore.org/en/download)를 설치합니다.
2. `python gp5_to_pdf.py`를 실행합니다. 추가 파이썬 패키지는 필요 없습니다.
3. 바로 열리는 파일 선택창에서 `.gp5` 파일을 고릅니다.
4. MuseScore 경로가 자동으로 표시되지 않으면 `MuseScore 선택`으로 설치한 `bin/MuseScore4.exe`를 지정합니다.
5. `실행`을 누르면 원본 GP5와 같은 폴더에 악기 파트별 PDF가 저장됩니다.

파일 이름은 `곡명_01_악기명.pdf` 형식입니다. 중복 파일에는 `(2)`, `(3)` 번호를 붙입니다.
같은 악기의 트랙이 여러 개면 각각 별도 PDF를 만듭니다. 원본 GP5는 변경하지 않습니다.
악보와 타브 표기는 MuseScore의 GP5 가져오기 결과를 따르므로 Guitar Pro의 인쇄 모양과 다를 수 있습니다.
변환 중에는 창이 응답하며 진행 표시가 나타납니다. 변환 제한 시간은 5분입니다.

## 작업 및 검증

- [x] 공식 MuseScore `--score-parts-pdf` 출력 형식 확인
- [x] 단일 스크립트 및 오류 처리 구현
- [x] 잘못된 출력, 안전한 파일명, 기존 파일 보존, 저장 실패 시 불완전한 PDF 삭제: 테스트 11개 통과
- [x] MuseScore 4.7.5로 기타·베이스·드럼 GP5 변환: 실제 테스트 3개 통과
- [x] 각 PDF의 악기별 내용과 렌더링 확인, 반복 실행 시 원본/PDF 바이트 보존, 손상 GP5 실패 확인
- [x] 실제 Tkinter 이벤트 루프와 실행 버튼 구동: 한글 파일명으로 PDF 3개 생성, 실행 중 버튼 잠금/복구 확인
- [x] 선택 취소, 파일 미선택, MuseScore 미선택, 오류/시간 초과 후 복구 확인

검증 한계: 데스크톱 제어 도구의 연결 실패로 Windows 파일 선택창의 직접 클릭 및 전체 창 스크린샷은 검증하지 못했습니다.
GUI 테스트에서는 파일 선택창의 반환값과 메시지창만 대체했으며, 실제 위젯·이벤트 루프·MuseScore·PDF 저장은 그대로 실행했습니다.

Ruff, basedpyright(오류/경고 0), Python 컴파일, 프로그래밍 규칙 검사 통과.
구조 검토: 단일 파일 GP5 변환 도구로 유지하며, JSON 경계 검사, GUI 메인 스레드 갱신, 외부 프로세스 제한 시간을 확인했습니다.
파일은 200~250 유효 코드 줄 범위이며, 사용자 요청에 따라 여러 실행 모듈로 나누지 않았습니다.

실행 검증 가설 및 결과:

1. 악기 파트가 누락/혼합될 수 있음 → 세 PDF의 서로 다른 악기명과 악보 내용 확인.
2. 재실행이 원본/기존 PDF를 바꿀 수 있음 → 원본 해시와 기존 PDF 바이트가 모두 유지됨.
3. 변환 실패가 성공으로 표시될 수 있음 → 손상 GP5는 오류를 반환하며 PDF를 생성하지 않음.
4. Windows 변환기가 시작 단계에서 멈출 수 있음 → 배포본에 없는 `offscreen` Qt 플러그인 강제 지정을 제거하고 실제 변환 성공 확인.

참고: [MuseScore 명령행 문서](https://handbook.musescore.org/appendix/command-line-usage)
