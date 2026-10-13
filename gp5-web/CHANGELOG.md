# Changelog

## 1.1.2

- Android GP5 uploads open the general file picker using the `.gp5` extension and generic binary MIME hint; mobile regression coverage now checks this picker hint.

## 1.1.1

- Android GP5 upload file-picker hint update (see 1.1.2 for the release with matching regression coverage).

## 1.1.0

- iPhone/iPad Safari and Android Chrome usage: unrestricted native file picker with GP5 validation, individual PDF save/open links and supported native sharing.
- Completed PDFs remain available after cancellation, later-track errors or ZIP creation failure; download actions are locked while busy and replaced URLs are released.
- Touch-friendly result actions, safe-area spacing and Korean mobile saving guidance.
- iPhone, iPad and Android emulation checks alongside desktop Chromium, WebKit and Firefox; native OS dialogs still require physical-device verification.

## 1.0.0

- First browser release with local GP5 import and selectable instrument PDFs.
- UTF-8 and CP949 Korean titles and instrument names, embedded Korean/music fonts.
- Vector A4 PDF pagination, explicit ZIP download, cancellation and partial results.
- Responsive Korean UI, pinned dependencies, automated three-engine browser checks and GitHub Pages deployment.
