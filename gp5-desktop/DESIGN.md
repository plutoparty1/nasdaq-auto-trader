# GP5 PDF desktop

## 1. Intent

A local music utility for selecting one GP5, choosing its instruments, and saving one PDF per selected instrument beside it. Korean first. All notation assets ship with the app. No network, account, installation wizard, or development settings in the user flow.

## 2. Color

Reuse the parent workspace's calm document-tool palette: background #f4f6f5, paper #ffffff, text #17201d, secondary #52605b, border #cdd6d2, primary #123b2f, hover #286650, primary-soft #e1eee8, error #9a3030, error-soft #f7e4e4, focus #164a91. Declare once as CSS custom properties. White page and black ink for printed scores.

## 3. Typography

App text uses system-ui, Malgun Gothic, Apple SD Gothic Neo, sans-serif; scale 12, 14, 16, 20, 28px with line height 1.5. Headings use weight 700. Word-boundary Korean wrapping; break long filenames only as needed. Printable scores embed Noto Sans CJK KR and Bravura: title18px, part12px, metadata10px.

## 4. Layout and spacing

Window 960×760, minimum760×640. Content max-width880px. Spacing scale4/8/12/16/24/32/48px. Panel radius6px. Header, file selection, track rows, conversion action, results. No decorative hero or fake preview. Smaller widths stack status/actions naturally; results scroll within the window. Print A4 210×297mm with12mm margins; whole score systems stay within186×273mm content boxes.

## 5. Primitives and states

- Buttons: primary convert, secondary choose/open-folder, quiet cancel. Default/hover/focus-visible/disabled; minimum44px hit area.
- File panel: empty/selected/invalid; display filename and source directory, change control.
- Track list: native list with a labeled checkbox, original sequence, name, and state. New files start with all instruments checked. A labeled whole-list checkbox supports checked/unchecked/indeterminate states. Selection controls use the primary accent, existing spacing tokens, 16px checkboxes, and minimum44px label hit areas. Keep Korean instrument names intact at word boundaries and wrap long unbroken names only as needed.
- Selection: show selected/total counts; zero selected instruments disables conversion and explains how to continue. Cancelling file replacement preserves the current selection. Progress follows original track indices, while the progress count includes selected instruments only.
- Status: aria-live polite text and progress; busy locks instrument selection, file changes, folder opening, and duplicate exports, while cancellation remains available. Unselected rows say they are not selected; selected unfinished rows settle to incomplete after cancellation/failure. Finished PDFs remain intact.
- Results: completed/partial/failure; never label partial work as complete, list saved file names.
- Error: role alert, plain Korean explanation, retry control via normal main actions.

## 6. Motion and accessibility

Only150ms color/opacity feedback; reduced-motion disables transitions. Visible2px focus ring. Semantic buttons/headings/list/progress, keyboard operation, explicit text in all statuses. No color-only feedback and no unexpected sounds.

## 7. Assets and consistency

Local fonts and alphaTab SVG only. No external CDN, photo, mockup, marketing decoration, or browser install prompt. UI strings must not expose IPC, renderer, binaries, or implementation jargon. Main controls never include raw command inputs.

## 8. Verification and accepted constraints

Check empty/busy/error/complete states at window minimum and default sizes, plus all/partial/zero instrument selections and selection changes via keyboard. Verify nonconsecutive original indices (such as 0 and 2), selected-only progress and cancellation, and cancelled file replacement. Actual GP5 fixture includes guitar/bass/drums; a long score verifies pagination and Korean text. PDF content and glyph visibility require rendered evidence. Windows executable is exercised on this host; macOS runtime requires a Mac. Code signing requires distributor certificates.
