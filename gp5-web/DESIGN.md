# GP5 PDF browser

## 1. Intent and source

Port the existing `../gp5-desktop/DESIGN.md` document-tool design to the browser. This is an existing design-system adaptation: preserve its quiet paper panels, dark green actions, Korean-first copy, and real instrument list. A person selects one GP5, chooses instruments, creates their PDFs, and explicitly saves an individual PDF or one ZIP. Files stay on the person's device. Downloads follow browser settings, not the GP5's original directory.

Primary users are a musician with a desktop keyboard and a musician opening the page on a small touch screen. Both must identify their file, change the instrument selection, cancel safely, understand partial results, and download without accounts or additional applications. Screen-reader users need named native controls and separate live feedback.

## 2. Color and material

Reuse background #f4f6f5, paper #ffffff, text #17201d, secondary #52605b, border #cdd6d2, primary #123b2f, hover #286650, primary-soft #e1eee8, error #9a3030, error-soft #f7e4e4, and focus #164a91. Declare these once as custom properties. Use flat paper panels with thin borders, not decorative shadows, images, hero artwork, or fake score previews.

## 3. Typography

Use system-ui, Malgun Gothic, Apple SD Gothic Neo, sans-serif. The scale is 12/14/16/20/28px; body line height 1.5, heading 1.3, weights 400/600/700. Korean prose wraps at word boundaries. Filenames and exceptionally long uninterrupted strings may wrap anywhere to prevent overflow. Initial UI uses system fonts; the score engine owns its lazy notation fonts.

## 4. Layout and spacing

Support viewport widths from 320px. Main content has an 880px maximum width, 32px padding on desktop and 16px on small screens. Reuse spacing 4/8/12/16/24/32/48px and 6px panel radius. Header, file panel, instrument list, conversion controls, feedback, and ZIP result follow that order. At 600px and below, file and action panels stack. Safe-area insets supplement the existing page padding; output actions wrap and expand for touch use. Track labels can wrap, while the original number and state remain identifiable. All content stays reachable through ordinary page scrolling.

## 5. Primitives and states

- Buttons and download link: shared 44px minimum hit area, primary/secondary variants, visible focus, hover, disabled. Downloads use a real anchor activated by the user, never automatic separate file downloads.
- File panel: empty/loading/selected/invalid; show filename and optional score title. The native picker remains the primary file input. Omit the accept filter so iOS and Android can select unregistered GP5 files; validate extension and a 64MB size limit before reading. Cancelled or stale reads cannot replace the current score.
- Track list: labeled native checkboxes, original sequence, name, and textual state. New files select every track. The 16px whole-list checkbox supports checked/unchecked/indeterminate states with a 44px label area. Show selected/total counts and disable conversion at zero.
- Busy state: lock file input, checkboxes, conversion, and existing download actions. Keep cancellation available. Preserve source and selection when file picking is cancelled.
- Progress: selected ordinal/total, original track row, and an accessible progress element. Unselected rows remain unselected. Selected unfinished rows settle to incomplete after cancellation or failure.
- Result: a reusable output row contains the filename, PDF save and open links, and a share button only when file sharing is supported. The ZIP save/share group follows all rows. All actions reuse the 44px button primitive, spacing tokens, and wrapping layouts. Completed PDFs remain available even if ZIP assembly fails. Sharing is called directly from a tap, supports cancellation and retry, and never claims a file was saved. Busy state removes download/open hrefs and disables sharing; replacement revokes object URLs, while persisted pagehide preserves them. Separate live share feedback cannot overwrite conversion state.
- Error: role alert and plain Korean feedback; retry uses the normal file and conversion actions.

## 6. Accessibility and motion

Use semantic headings, named buttons, implicit checkbox labels, a labeled progress element, a polite live status, and alert errors. Checkbox rows and all actions offer at least 44px targets. All focusable controls have a 2px blue focus ring. No color-only state or forced sound. Only short opacity feedback is allowed; reduced-motion disables transitions. Do not disable zoom. Text and controls must remain usable at 320px and enlarged text.

## 7. Assets, privacy, and performance

Use local app assets and lazy engine/font loading through the core API. Initial HTML, CSS, and interaction logic remain small. No external web fonts, analytics, user-file uploads, implementation jargon, extra runtime installation, decorative imagery, or preview placeholders. Restrict scripts and connections to the app's origin with a content security policy; retain inline style support for notation rendering. The footer links to the bundled open-source notices. Do not promise first-load offline availability: loading the page and its conversion resources may require a connection.

## 8. Verification and remaining evidence

The parent QA lane owns real-browser and independent visual checks after integration: 320/390/1440px; empty/all/partial/zero selections; keyboard focus and Space; invalid/large GP5; cancellation during loading and conversion; nonconsecutive indices 0 and 2; partial ZIP; explicit repeated downloads; object-URL replacement; long Korean names; and file replacement cancelled or completed out of order. Check network requests for absent uploads and verify downloaded PDFs. Review artifacts against this document before approving visual completion. Safari download behavior requires a real Safari-capable environment; do not infer it from Chromium alone. No accessibility debt is intentionally accepted.
