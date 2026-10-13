# Korean GP5 and selected instruments

Status: Complete; implementation, runtime, artifacts and five review lanes passed. Size: M. Authorization: explicit user bug report and request to add instrument selection; no extra approval needed for these local reversible changes.

## Problem and goal

The app decodes GP5 metadata as UTF-8 only, causing legacy Korean metadata to break in both the list and PDFs. It also exports every track. Correct Korean legacy decoding and export only checked tracks, retaining offline standalone behavior.

## Acceptance criteria

- CP949/EUC-KR Korean GP5 title and part names survive list, PDF headings and filenames. UTF-8 Korean and ASCII remain correct.
- The importer and PDF renderer use the same selected charset.
- All tracks start checked; individual and all-selection controls work with keyboard and accessible labels.
- No selected tracks means conversion is disabled. Main process rejects empty, duplicate, non-integer and out-of-range indices without writing files.
- Non-contiguous selected tracks retain original track numbers and correct progress/row states. Unselected tracks create no PDF.
- Cancel, repeat export, malformed-file recovery, original GP5 and existing PDF preservation remain correct.
- Rebuilt Windows portable EXE and unpacked folder contain the fix; actual final artifact generates correct Korean PDFs for a chosen subset.

## Technical contract and tests

`chooseFile()` returns metadata plus `encoding`. `convert(indices)` accepts original track indices. Progress contains selected ordinal `current`, selected `total`, original `trackIndex`, track name and status. `renderTrackPdf(bytes, trackIndex, signal, encoding)` forwards encoding to its renderer job.

Failing-first tests cover real GP5 legacy/UTF-8 metadata and selection boundaries. Runtime QA uses real Electron rendering, native dialog return interception, visual capture, and PDF content extraction. No new end-user dependency. Mac execution/signing is outside this Windows repair's validation scope.

## Delivered evidence

`release/1.1.0/GP5-PDF-Windows-x64.exe` and its sibling `win-unpacked` contain the update. An active older app and a default-output EBUSY failure led to this isolated version folder. The actual portable EXE reports packaged=true and version=1.1.0, creates only Korean tracks 01/03, and passes independent PDF inspection. 21 packaged source/font/license files match current source. See `VERIFICATION.md`; existing root release artifacts and Mac staging ZIPs are not this update.
