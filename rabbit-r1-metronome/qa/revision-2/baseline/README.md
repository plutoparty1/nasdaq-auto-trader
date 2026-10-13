# PULSE · rabbit r1 메트로놈

요청한 8개 기능을 갖춘 정적 Creation 앱입니다. 실제 r1 화면인 **240×282**에 맞췄습니다. 외부 서버, 로그인, LLM, 음원 다운로드 없이 실행합니다.

## 바로 실행

배포용 파일은 [dist/index.html](dist/index.html)입니다. PC에서 더블클릭해 미리 볼 수 있습니다. 저장 검증이나 r1 설치에는 HTTP/HTTPS로 여세요.

```sh
cd rabbit-r1-metronome
npm ci
npm run build
npm start
```

PC 미리보기: http://127.0.0.1:4173  
설치 QR 도구: http://127.0.0.1:4173/install.html  
다른 포트는 환경 변수 `PULSE_PORT`로 지정할 수 있습니다.

## r1에 설치하기

1. **dist 폴더**를 Netlify Drop에 끌어다 놓거나 GitHub Pages 등 정적 호스팅에 올립니다. `index.html`만으로 앱은 실행됩니다.
2. 배포 주소가 HTTPS로 열리는지 확인합니다.
3. `dist/install.html`을 PC에서 열고 **배포한 앱 주소**를 입력한 뒤 QR을 생성합니다. QR 도구도 외부 코드 로딩 없이 작동합니다.
4. r1에서 **creations → add via QR code**를 선택해 QR을 스캔합니다.
5. 설치된 PULSE 카드에서 앱을 엽니다. 첫 재생 때 오디오가 시작됩니다.

QR에는 rabbit 공식 형식인 `title, url, description, iconUrl, themeColor` JSON이 담깁니다. `localhost`는 PC 내부 주소이므로 r1 설치 주소로 사용할 수 없습니다.

## 사용법

| 기능 | 조작 |
| --- | --- |
| 템포 | 휠 위/아래로 1 BPM 증감. 큰 숫자를 눌러 20–300 정수 BPM 입력. +/- 버튼도 지원 |
| 재생·일시정지 | r1 우측 버튼 또는 화면의 재생 버튼 |
| 4/4 기본 | 한 마디 4박, 기본 1박 강조 |
| 8비트 | 한 박을 2개로 나눔. 한 마디에 8개 클릭 |
| 셋잇단 | 한 박을 3개로 나눔. 한 마디에 12개 클릭 |
| 강조 박자 | 1–4 숫자를 눌러 선택. 여러 강조 및 강조 없음 지원 |
| 드럼·멜로디 | 소리 탭에서 선택. 킥/클릭/하이햇과 음정이 있는 비트 |
| 무음 | 상단 무음 또는 소리 탭 체크박스. 소리는 즉시 끄고 화면의 박자 표시와 약한 주황빛 펄스로 안내 |
| 탭 템포 | 큰 TAP 버튼을 같은 간격으로 누름. **첫 탭부터 실제 10초** 측정 후 숫자 BPM 표시. 4회 이상 필요. 다시 측정 / 템포 적용 지원 |
| 곡 저장 | 내 곡 탭에서 제목 `music1` 입력. `80-music1`처럼 표시. 곡을 눌러 템포·비트·강조·음색·무음·음량 복원 |
| 삭제 | 삭제 → 확인. 최대 100곡 |
| PC | ↑/↓ 템포, 화면 위에서 마우스 휠. 빈 화면에 포커스 시 Space 재생, 버튼에 포커스 시 Space는 해당 버튼 조작 |

탭 측정 화면에 들어가면 메트로놈은 멈춥니다. 측정 도중 화면을 벗어나거나 재생을 시작하면 측정이 취소됩니다. 앱이 숨겨지면 재생·측정을 중단합니다. 템포·분할·음색·강조를 재생 중 바꾸면 새 설정으로 한 마디를 다시 시작합니다.

## 저장

r1에서는 **공식 `window.creationStorage.plain`**에 UTF-8 Base64로 보관합니다. 한국어 제목을 지원합니다. PC에서는 브라우저 localStorage를 사용합니다. 기기·브라우저 사이 동기화는 제공하지 않습니다. 저장 실패 시 성공으로 표시하지 않습니다. 읽기에 실패하면 기존 데이터를 덮어쓰지 않고 일시적인 연습 모드로 실행합니다.

## 검증

```sh
npm test
npm run check
npm run build
npm run test:browser
```

브라우저 검증에는 설치된 Chrome이 필요합니다. 분리된 브라우저 프로필로 r1 이벤트와 저장 브리지만 모의합니다. 오디오는 실제 Chrome Web Audio API를 사용합니다. 결과와 스크린샷은 `docs/QA.md`, `qa/`에 기록합니다.

**현재 범위:** PC Chrome 및 SDK 계약 검증. 실물 r1 스피커, OS별 오디오 정책, QR 스캔 설치는 실기 검증이 필요합니다. 이 작업에서는 공개 호스팅에 배포하거나 사용자 기기에 설치하지 않았습니다.

## 공식 근거

- [rabbit Creation 사용·설치·화면 제약](https://www.rabbit.tech/support/article/how-to-use-r1-creations)
- [하드웨어 이벤트·저장 계약](https://github.com/rabbit-hmi-oss/creations-sdk/blob/62ef8b37de9c8ec74499987eeed1f07b9cfaaaf0/plugin-demo/reference/creation-triggers.md)
- [공식 설치 QR JSON 형식](https://github.com/rabbit-hmi-oss/creations-sdk/blob/62ef8b37de9c8ec74499987eeed1f07b9cfaaaf0/qr/final/js/app.js)
