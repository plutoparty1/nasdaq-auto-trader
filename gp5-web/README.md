# GP5 PDF 웹 버전

GP5 파일을 선택하고 원하는 악기만 체크하면 악기별 PDF를 만드는 웹앱입니다. **v1.1.2부터 Android Chrome의 GP5 첨부는 파일 형식 힌트를 사용해 일반 파일 선택기로 열립니다.** iPhone·iPad Safari와 Android Chrome에서 PDF 저장·열기·공유를 지원합니다. Windows·Mac에서도 프로그램 설치 없이 사용할 수 있습니다. 악보는 서버에 업로드하지 않습니다.

- 사이트: https://plutoparty1.github.io/gp5-pdf-web/
- 소스·이슈: https://github.com/plutoparty1/gp5-pdf-web
- 릴리즈: https://github.com/plutoparty1/gp5-pdf-web/releases

## 사용 방법

1. 배포한 사이트를 열고 GP5 파일을 선택합니다.
2. PDF로 만들 악기만 체크합니다. 처음에는 모두 선택됩니다.
3. PDF 만들기를 누르고 완료 후 악기별 **PDF 저장** 또는 **열기**를 누릅니다. **ZIP 저장**으로 한 번에 받을 수도 있습니다.

원본 GP5 폴더로 자동 저장하지 않습니다. 취소·오류로 일부만 완성되어도 완성된 PDF는 저장할 수 있습니다. ZIP 생성이 실패한 경우에도 개별 PDF를 제공합니다. 초기 사이트·변환 엔진·글꼴을 불러올 인터넷 연결이 필요합니다.

### iPhone·iPad

Safari에서 사이트를 열고 **GP5 파일 선택**을 눌러 파일 앱의 `.gp5`를 고릅니다. iCloud 파일은 기기에 다운로드한 뒤 선택하세요. 변환 후 **공유 → 파일에 저장**을 선택합니다. 공유 버튼이 표시되지 않으면 **열기**로 PDF를 연 뒤 Safari의 공유 메뉴를 사용하거나 **PDF 저장**을 누르세요. ZIP은 파일 앱에서 눌러 압축을 풀 수 있습니다.

### Android

Chrome에서 사이트를 열고 파일 앱이나 다운로드 폴더의 `.gp5`를 선택합니다. 변환 후 **PDF 저장**을 누르면 브라우저 다운로드 설정에 따라 저장됩니다. 파일 공유를 지원하는 기기에서는 **공유**로 다른 앱에 전달할 수 있습니다.

공유 버튼은 해당 파일을 공유할 수 있는 브라우저에서만 표시됩니다. 앱 내 브라우저에서 파일 선택·저장이 되지 않으면 Safari나 Chrome으로 사이트를 여세요. 변환 중에는 화면을 열어 두세요. 큰 악보는 악기를 나누어 변환하세요. 홈 화면에 사이트 바로가기를 추가할 수 있지만 오프라인 실행을 보장하지 않습니다.

## 가장 간단한 GitHub Pages 배포

`release/GP5-PDF-Web-site.zip`은 빌드가 끝난 정적 사이트입니다. Node.js 설치 없이 올릴 수 있습니다.

1. ZIP을 풉니다. `index.html`, `assets`, `LICENSES`, `.nojekyll` 등이 나옵니다.
2. 웹앱 전용 GitHub 저장소를 만들고 **풀린 내용물**을 저장소 최상위에 업로드합니다. ZIP 자체나 `dist` 폴더로 감싸서 올리지 않습니다.
3. 저장소 **Settings → Pages → Build and deployment**에서 **Deploy from a branch**를 선택합니다.
4. 브랜치를 **main**, 폴더를 **/(root)**로 선택하고 저장합니다.
5. 배포가 끝나면 Pages 화면에 표시되는 주소로 접속합니다.

사이트 ZIP의 내용물만 웹앱 전용 저장소에 올리면 됩니다.

## 소스에서 자동 빌드·배포

`release/GP5-PDF-Web-source.zip`의 내용물을 새 저장소 최상위에 올립니다. 숨김 폴더인 `.github`도 포함해야 합니다.

1. **Settings → Pages → Source**를 **GitHub Actions**로 설정합니다.
2. **Actions → Deploy GP5 PDF to GitHub Pages → Run workflow**를 실행합니다.
3. 이후 `main` 브랜치에 변경을 올리면 구문·단위·데스크톱 3종 및 모바일 3종 에뮬레이션 테스트와 빌드 후 자동 배포합니다. PR에서도 같은 검증을 실행합니다.
4. 패키지 버전과 같은 태그(예: `v1.0.1`)를 올리면 릴리즈 ZIP과 체크섬을 생성합니다.

`.github/workflows/pages.yml`은 이 프로젝트의 내용물이 저장소 루트에 있는 구성을 사용합니다. 상대 자산 경로를 사용하므로 저장소 이름을 코드에 하드코딩할 필요가 없습니다. 첫 릴리즈는 위 전용 저장소와 GitHub Pages에서 제공합니다.

## 개발

Node.js 24 LTS 기준:

```sh
npm ci
npm test
npm run check
npm run dev
```

`npm run build` 결과는 `dist/`입니다. `npm run preview`로 확인합니다.
브라우저 검증: `npx playwright install chromium webkit firefox` 후 `npm run test:browser`.
로컬 HTML 파일을 더블클릭하는 대신 HTTP 개발 서버 또는 GitHub Pages로 접속하세요.

`npm run build && npm run package`로 릴리즈 ZIP을 만듭니다. 구조는 [ARCHITECTURE.md](ARCHITECTURE.md), 변경·테스트·릴리즈 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 지원 범위와 제한

- GP5 5.00/5.10, 64MB 이하. Guitar Pro 인쇄물과 일부 배치·특수 표기가 다를 수 있습니다.
- UTF-8과 한국어 CP949를 처리합니다. 혼합 인코딩·이미 깨진 텍스트·두 문자셋 모두에 유효한 바이트는 완전 자동 복구를 보장하지 않습니다.
- 메모리 사용을 제한하기 위해 대형 악보와 출력 용량에 제한이 있습니다. 상세 값과 실제 브라우저 검증 결과는 VERIFICATION.md를 참고하세요.
- 최신 Safari·Chrome을 사용하세요. iOS·Android 지원은 웹앱 방식이며 App Store·Play Store 설치 파일은 아닙니다. `gp5_to_pdf.py` 자체는 Python/Tkinter와 MuseScore를 사용하는 PC용입니다.
- 취소는 처리 단계 사이에서 적용됩니다. 동기 악보 배치 중에는 반응이 지연될 수 있습니다. Playwright의 iPhone·iPad·Android 에뮬레이션은 실제 기기 검증과 다릅니다. OS 파일 선택창·공유창·파일 앱 저장은 실제 기기에서 별도 확인이 필요합니다.

앱 소스: [MIT](LICENSE). 외부 라이브러리·글꼴 라이선스·출처: [public/THIRD_PARTY.md](public/THIRD_PARTY.md).
배포 설정 근거: [GitHub Pages 공식 문서](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [Vite 정적 배포 문서](https://vite.dev/guide/static-deploy).
