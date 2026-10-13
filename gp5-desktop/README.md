# GP5 PDF

Guitar Pro나 MuseScore 없이 GP5 악보에서 선택한 악기를 PDF로 저장하는 데스크톱 앱입니다. 실행 엔진과 악보·한글 글꼴을 포함하므로 사용자는 Python, Node.js, 추가 글꼴을 설치할 필요가 없습니다. 변환은 인터넷 연결 없이 PC 안에서 진행됩니다.

## 사용 방법

1. Windows에서는 `release/1.1.0/GP5-PDF-Windows-x64.exe`를 실행합니다. 이 실행 파일 하나만 전달하면 됩니다.
2. 바로 열리는 파일 선택창에서 `.gp5` 파일을 선택합니다. 취소했다면 **GP5 파일 선택**을 누르면 됩니다.
3. 악기 목록에서 PDF로 만들 악기만 체크합니다. 처음에는 모두 선택되며 **전체 선택**으로 한 번에 선택·해제할 수 있습니다.
4. **악기별 PDF 만들기**를 누릅니다. 선택한 GP5와 같은 폴더에 체크한 악기의 PDF만 만들어집니다. **저장 폴더 열기**로 확인합니다.

예: `연습곡 - 01 - Guitar.pdf`, `연습곡 - 02 - Bass.pdf`. 같은 악기의 트랙이 여러 개면 각각 별도 파일로 저장합니다. 긴 악보는 여러 A4 페이지를 담은 PDF 한 개가 됩니다.

첫 번째와 세 번째 악기만 선택하면 파일 번호도 `01`, `03`을 유지합니다. 악기를 하나도 선택하지 않으면 변환 버튼이 비활성화됩니다. 선택 해제는 이전에 생성한 PDF를 삭제하지 않습니다.

원본과 기존 PDF는 덮어쓰지 않습니다. 이름이 겹치면 번호를 붙입니다. 취소·실패 시 이미 완성한 PDF는 유지하고, 현재 저장 중이던 불완전한 파일은 정리합니다. 원본 폴더에 쓰기 권한이 필요합니다.

## 운영체제와 배포

| 대상 | 파일 | 상태 |
| --- | --- | --- |
| Windows 10 이상, x64 | `release/1.1.0/GP5-PDF-Windows-x64.exe` | 1.1.0 포터블 앱 |
| macOS 13 이상, Intel | `release/1.1.0/GP5-PDF-macOS-x64-unsigned-unverified.zip` | 1.1.0, Mac 실행·서명 검증 전 |
| macOS 13 이상, Apple Silicon | `release/1.1.0/GP5-PDF-macOS-arm64-unsigned-unverified.zip` | 1.1.0, Mac 실행·서명 검증 전 |

Windows 포터블 앱은 실행할 때 임시 폴더에 런타임을 풉니다. 실행 파일에 코드 서명이 없어 Windows의 게시자 확인 경고가 나타날 수 있습니다. 관리자가 실행을 제한한 PC까지 보장하지는 않습니다.

Mac 스테이징 ZIP은 Windows에서 공식 Electron 아카이브의 Unix 실행 권한과 심볼릭 링크를 보존해 만든 개발용 결과물입니다. **일반 사용자에게 바로 배포할 검증된 Mac 앱은 아닙니다.** 실제 Mac에서 빌드·실행 검증과 서명이 필요합니다. Apple Silicon 서명 요건과 공증 절차는 [MACOS.md](MACOS.md)에 정리했습니다. CI 설정만으로 서명·공증이 완료되지는 않습니다.

이번 1.1.0 수정본은 `release/1.1.0/` 안의 Windows 실행 파일·`win-unpacked`와 두 Mac ZIP에 있습니다. Mac ZIP에도 한글 수정·악기 선택 기능이 포함되며, 압축을 풀면 `GP5 PDF.app`이 나옵니다. 기존 앱이 실행 중이어서 버전별 폴더에 빌드했습니다. `release/` 바로 아래의 예전 EXE·폴더·Mac ZIP은 이번 1.1.0 결과물이 아닙니다. Mac ZIP의 구조와 내용은 검사했지만 실제 Mac 실행과 서명은 검증하지 않았습니다.

실행 엔진을 포함하므로 파일 용량은 일반 Python 스크립트보다 큽니다. Linux, Windows 32비트 및 구형 운영체제는 이번 배포 대상에 포함하지 않습니다.

## 악보 변환 범위

- GP5 5.00/5.10 파일, 64MB 이하를 받습니다.
- alphaTab의 GP5 가져오기·악보 표기를 사용합니다. Guitar Pro 인쇄 결과와 글꼴, 간격, 일부 특수 표기가 다를 수 있습니다.
- A4 용지 안에서 오선·타브 시스템을 나눠 배치합니다. 한 페이지보다 큰 단일 시스템은 크기를 줄여 넣습니다.
- 한글 파일명과 한글 출력 글꼴을 지원합니다. 내부 문자는 유효한 UTF-8을 우선 사용하고, UTF-8로 읽을 수 없는 문자열이 한국어 CP949/EUC-KR로 정상 해석되면 해당 인코딩을 사용합니다. 목록·PDF 제목·파일명이 같은 인코딩을 사용합니다.
- CP949 확장 한글도 번들 런타임에서 검증합니다. 한 파일에 여러 인코딩을 섞었거나 두 인코딩 모두로 유효한 짧은 문자열은 자동으로 구분할 수 없으며, 이 경우 UTF-8을 우선합니다. 이미 깨진 문자로 저장된 원본 텍스트 자체를 복구하지는 않습니다.
- 악보 한 트랙의 변환 제한 시간은 90초입니다. 손상된 파일이나 제한을 넘는 악보는 오류를 표시합니다.

## 개발자 실행·빌드

빌드하는 PC에는 Node.js 22.12 이상과 npm이 필요합니다. 최종 사용자는 필요 없습니다.

```sh
cd gp5-desktop
npm ci
npm test
npm start
```

`npm test`는 시스템 Node의 문자 변환기 차이를 피하기 위해 설치된 Electron의 Node 모드에서 단위 테스트를 실행합니다. 실제 배포 앱과 같은 ICU/문자 변환기를 사용하며 CP949 확장 한글 테스트도 생략하지 않습니다.

Windows에서 `npm run build:win`, Mac에서 `npm run build:mac`을 실행하면 `release/`에 결과물이 생깁니다. macOS용 electron-builder 타깃은 Mac에서 빌드해야 합니다.

[GitHub Actions 설정](../.github/workflows/gp5-desktop.yml)은 수동 실행 시 Windows와 macOS 호스트에서 별도로 빌드합니다. 이 작업에서는 원격 저장소에 업로드하거나 워크플로를 실행하지 않았습니다.

앱 통합 검증은 `node node_modules/electron/cli.js test/desktop.e2e.cjs`로 실행할 수 있습니다. 검증용 파일과 결과는 무시 목록에 있는 `qa/`에 생성됩니다. 파일 선택창 반환값만 검증용 경로로 대체하며, 실제 Electron UI·IPC·악보 렌더링·PDF 저장을 사용합니다.

한글·악기 선택 회귀 검증은 `node node_modules/electron/cli.js test/korean-selection.e2e.cjs`로 실행합니다. 이번 버전의 빌드·최종 실행 파일 검증 명령은 다음과 같습니다(Git Bash):

```sh
npm run build:win -- --config.directories.output=release/1.1.0
GP5_QA_EXE=release/1.1.0/GP5-PDF-Windows-x64.exe node test/packaged.e2e.cjs
```

일반 빌드는 기본 `release/`에 생성됩니다. `GP5_QA_EXE`를 생략하면 실행 파일 검증도 그 기본 위치를 사용합니다.

의존성과 글꼴의 라이선스·원본 출처는 [THIRD_PARTY.md](THIRD_PARTY.md)를 참고하세요.

실제 실행 결과와 검증하지 못한 범위는 [VERIFICATION.md](VERIFICATION.md)에 기록했습니다.
