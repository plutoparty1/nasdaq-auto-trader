# GP5 PDF web / GitHub Pages

Status: implemented and verified for release. Size: L (platform port). Publish the standalone browser converter through a dedicated GitHub repository, Pages and versioned release archives.

## Outcome

An entirely static, Korean-first web app that reads a local GP5, lets users select instruments, creates one actual PDF per selected track, and offers one ZIP download. It runs without MuseScore, Guitar Pro, Python, Electron installation or an upload server. Browser permissions prevent a universal promise to save next to the source; use an explicit browser download instead.

## Acceptance

- Genuine GP5 v5.00/5.10 under 64MB, ASCII/UTF-8/CP949 Korean including extended syllables.
- Default all selected; individual/all/mixed/empty selection; original track indices and numbering; accessible keyboard controls.
- Real PDF conversion in browser with Korean/music fonts, A4 pagination, correct selected-track notes, long score systems kept within pages.
- Explicit ZIP download gesture works across browser engines; cancellation/errors retain completed PDFs and label partial results accurately.
- No source upload, third-party requests, server, account, secret, or filesystem writes to the source.
- Responsive 320px through desktop, clear empty/loading/busy/complete/error states, focus, contrast and 44px targets.
- Build output works both at domain root and a repository subpath. GitHub Pages workflow and exact upload/deploy instructions supplied. Remote deployment is not claimed without executing it.

## Boundaries and contracts

`loadGp5(File)` returns name/title/trackNames/encoding/score. `exportSelected({source,indices,signal,onProgress})` returns ZIP Blob or null, filename, files, cancelled and error. `renderTrackPdf({score,trackIndex,signal,onProgress})` returns PDF Blob. UI owns download URL lifetime; exporter owns cancellation/partial output; renderer owns local font and page layout. All dependencies pinned and licenses distributed.

## Verification

Node regression tests plus real browser upload/selection/download scenarios in Chromium, WebKit and Firefox. Inspect ZIP entries and actual PDF text/raster; test CP949/UTF-8, non-contiguous subset, cancellation, invalid input and repository subpath. Never substitute a fake renderer for final browser QA. Results and repeatable commands are in VERIFICATION.md.

## BOOMER-6 design review

Boundaries: static hosting separates no server responsibilities. Omissions addressed: Safari downloads, code-page detection, page breaks, cancellation and invalid input. Overengineering avoided: port existing design and renderer, no React/backend/accounts. Maintainability: separate input/render/ZIP/UI and reuse original indices. Evidence: real GP5/PDF/ZIP browser artifacts. Risks: browser memory and font/decoder differences require explicit limits and engine QA; hosted app needs first-load network and cannot guarantee original-folder save.
