# Mobile GP5 PDF v1.1.0

Date: 2026-09-29 · Size: M · Status: Implemented (verification and limits: VERIFICATION.md)

## Goal

Use the existing GitHub Pages converter on iOS Safari and Android Chrome: select a GP5 from Files/downloads, select instruments with touch, convert locally, save/open/share individual PDFs or download one ZIP. Keep the existing desktop flow and Korean score content.

## Acceptance criteria

- Native picker permits unknown GP5 MIME types; extension, header and size validation still reject invalid input.
- Completed PDFs have the same bytes and filenames as ZIP entries, including nonconsecutive selections and partial cancellation.
- Native sharing is offered only after canShare accepts the actual File; share runs within the tap gesture. Cancellation/failure preserves downloadable files.
- ZIP failure preserves individual PDFs. Busy/replacement/unload disables or releases old downloads; bfcache navigation preserves usable results.
- Responsive controls remain usable at 320/375/768/1280px with 44px targets and normal zoom.
- Build and existing desktop browser checks pass; mobile WebKit/Chromium runs exercise real GP5 conversion, PDF download, error recovery, and touch selection.
- Version, documentation, GitHub Pages and release archives are updated together. Actual iOS/Android OS picker and share-sheet verification is distinguished from emulation.

## Design and boundaries

Reuse vanilla JS, alphaTab, PDFKit, and local fonts. Add result-delivery module and File[] outputs; no server, account, new dependency, native package or offline promise. Python remains the MuseScore desktop implementation with a web entry point; phones use the deployed URL.

## Edge cases

Wrong extension/signature, empty/oversize GP5, unavailable fonts, zero selection, cancellation before/after first completed PDF, unsupported/denied/cancelled native share, repeat exports, a new result while sharing settles, long Korean names, and ZIP allocation failure must leave accurate UI and recoverable completed output.

## Review and verification

BOOMER-6: necessity (mobile saving requires direct PDFs), deletion (no framework/PWA/backend), reuse (existing converter/design tokens), complexity (one result-delivery owner), dependency (none added), operability (Pages CI+version tag). Independent goal/code/security/context and visual reviews follow browser evidence. Physical-device OS integration is a release limitation, not claimed by Playwright emulation.
