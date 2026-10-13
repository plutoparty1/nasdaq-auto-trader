# Architecture

This is a static browser application: native JavaScript modules, Vite, npm lockfile, and GitHub Pages. There is no conversion server, account, Electron runtime, or OS-specific installer. Every score is read through the browser File API and stays in memory on the user's device.

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `src/app.js` | UI state, selected original track indices, progress, AbortController |
| `src/download-results.js` | Individual PDF/ZIP links, native file sharing, busy guards and object URL lifetime |
| `src/import-score.js` / `encoding.js` | GP5 header/size checks, lazy alphaTab parsing, strict UTF-8/CP949 metadata decoding |
| `src/export-score.js` | Selection validation, sequential per-track rendering, safe filenames, ZIP and partial results |
| `src/pdf.js` / `pdf-score.js` | alphaTab SVG rendering and SVG-to-PDFKit conversion |
| `src/pdf-output.js` | PDF stream completion, error/close/abort settlement and byte limits |
| `src/pdf-fonts.js` | Same-origin font loading, PDF embedding, failed-load cleanup and retry |
| `src/pdf-layout.js` | A4 placement, whole-system pagination and header wrapping |

`loadGp5(file)` returns `{name, title, trackNames, encoding, score}`. The UI carries the score object and original zero-based indices into `exportSelected({source, indices, signal, onProgress})`. Its result contains `{blob, filename, files, pdfs, cancelled, error}`. The renderer returns an actual PDF Blob for one track. No UI code interprets GP5 bytes or draws notation.

The UI offers a ZIP link when a ZIP Blob exists and per-PDF links for each File in pdfs. Completed PDF Files survive ZIP assembly failure. Cancellation or a later-track failure preserves already completed PDFs. Track numbers in filenames always refer to the source, including non-contiguous selections. Cancelling is cooperative: synchronous score layout may finish before cancellation is observed.

## Browser and data boundaries

alphaTab and PDF code load when needed. Noto Sans CJK KR and Bravura are bundled; no CDN or remote conversion API is used. Untrusted metadata is displayed with `textContent`; generated SVG is restricted to notation elements and attributes. The HTML CSP permits local assets and the inline styles required by the renderer, and disables objects and forms.

Legacy Korean GP5 metadata is decoded from its original bytes. UTF-8 takes precedence when all original metadata decodes strictly; otherwise valid CP949 Korean metadata can be chosen. Derived short names do not decide the encoding. Tests for extended Korean syllables run in real browsers because Node's ICU decoder differs on some valid CP949 bytes.

Large files and output are bounded to limit browser memory use. See [VERIFICATION.md](VERIFICATION.md). A web app cannot silently write beside a selected local file across browsers, so output uses explicit PDF/ZIP downloads and capability-detected native file sharing. The native sharing dialog is invoked within the original user gesture; rejected sharing preserves download links.

## Deployment

The repository root is the web project root. Vite emits relative asset URLs (`base: './'`), so the same `dist/` works under a GitHub repository path. No server routing or environment secrets are needed. Pull requests run checks; `main` runs the same checks and deploys Pages only after they pass. Version tags run the release workflow to produce archives and SHA-256 checksums.

Dependencies are exact-version pinned with a lockfile. GitHub Actions are pinned to commit SHAs. Runtime license notices are generated during every build and included in `dist/LICENSES/`. Keep alphaTab source attribution and both bundled font licenses in all redistributed builds.
