# macOS packaging

GP5 PDF embeds Electron, the converter, and its fonts. End users do not install
Python, Node.js, MuseScore, or Guitar Pro. The Python script below is a developer
build tool, not part of the application's runtime requirements.

The pinned Electron 44.4.5 runtime requires **macOS 13 Ventura or later**. Use the
x64 archive for Intel Macs and the arm64 archive for Apple Silicon Macs.

## Windows-created staging archives

The current helper packages **1.1.0**, including Korean decoding and selected-track
export. Both current ZIPs are in `release/1.1.0/`; older ZIPs directly under
`release/` still contain 1.0.0. The helper's `APP_VERSION` is release-specific:
keep it equal to the version inside the supplied ASAR when packaging another release.
The native Mac build below reads the current version from `package.json`.

`scripts/package-macos.py` takes exactly three positional paths:

```text
python scripts/package-macos.py sourceElectronZip appAsar outputZip
```

Use the official Electron release ZIP matching the version pinned by this project
and the intended CPU architecture: `darwin-x64` for Intel or `darwin-arm64` for
Apple Silicon. Obtain it through `@electron/get` with its checksum verification;
do not use an unpacked Windows copy of `Electron.app` as the source.

Example, with already downloaded runtimes and the built application archive:

```text
python scripts/package-macos.py electron-darwin-x64.zip qa/macos-app-1.1.0.asar release/1.1.0/GP5-PDF-macOS-x64-unsigned-unverified.zip
python scripts/package-macos.py electron-darwin-arm64.zip qa/macos-app-1.1.0.asar release/1.1.0/GP5-PDF-macOS-arm64-unsigned-unverified.zip
```

Python 3.11+ and a filesystem supporting same-volume hard links, such as NTFS or
APFS, are required on the build machine. The output directory must exist. Existing
output files are never replaced. A temporary ZIP is audited before the final path
is created; a failed build does not publish a partial archive.

The script copies ZIP entries directly, never extracting symbolic links to NTFS.
It preserves Unix mode bits, symlink payloads, entry comments, extra fields,
timestamps, compression methods, archive comments, and unchanged entry CRCs/sizes.
Compressed byte streams and ZIP offsets may change. Its console summary reports
the number of preserved symlinks, executable files, and Unix entries.

The only application changes are:

- Rename the outer `Electron.app` directory to `GP5 PDF.app`.
- Set the top-level bundle name, identifier `local.gp5pdf.desktop`, and version
  `1.1.0`; retain `CFBundleExecutable=Electron` and all original Mach-O bytes.
- Replace `Contents/Resources/default_app.asar` with `app.asar`.
- Remove any old `ElectronAsarIntegrity` plist entry, since it describes a different
  application. This staging method does not enable or update Electron ASAR fuses.

**These ZIPs are unsigned/unverified staging artifacts, not verified Mac releases.**
The script performs no GP5 PDF signing or notarization. Existing Electron signature
files are copied unchanged, but modifying bundle metadata/resources may invalidate
their seals. A metadata audit is not a code-signature or runtime check. Apple Silicon
requires valid code signatures, which may be ad hoc for local development. Windows
ZIP processing cannot establish that requirement or confirm Mac launch behavior.
No Gatekeeper bypass is promised or performed.

## Current 1.1.0 archive verification

Both runtime ZIP hashes match the official Electron 44.4.5 `SHASUMS256.txt`.
The app payload matches the tested Windows 1.1.0 ASAR byte for byte and has no
native Windows modules. Each output preserves 583 Unix entries, 14 symlinks and
13 executable files. Every unchanged runtime entry is byte-identical to its
official source; both ZIP CRC checks and x64/arm64 Mach-O CPU checks pass.
Both bundle version fields are 1.1.0. See `qa/macos-artifacts-1.1.0.json`,
`qa/macos-app-snapshot-1.1.0.json` and `release/1.1.0/SHA256SUMS.txt`.
These checks establish archive contents, not successful native Mac execution.

## Reliable native macOS build

On a Mac, install the project's build-time Node.js/npm requirements, then run from
`gp5-desktop`:

```sh
npm ci
npm run build:mac -- --publish never
```

The native build should produce separate x64/arm64 ZIPs or an explicitly configured
universal build. Keep `--publish never` for local build and QA. `electron-builder`
does not support building its macOS target directly on Windows; creating a ZIP
manually does not remove the need for native macOS validation.

For a distributable signed release, use an Apple Developer account, a Developer ID
Application certificate installed in the build Mac's keychain, and Xcode command
line tools. Configure electron-builder's macOS signing identity, hardened runtime,
Electron-appropriate entitlements, and notarization credentials using its official
signing documentation. Keep credentials in the build machine's keychain or secret
store. Do not place them in this repository.

Build and sign on macOS, submit the signed app archive to Apple's notarization
service, staple the successful ticket to the `.app`, then create the final ZIP on
macOS while preserving symlinks. Validate before distribution:

```sh
codesign --verify --deep --strict --verbose=2 "GP5 PDF.app"
xcrun stapler validate "GP5 PDF.app"
spctl --assess --type execute --verbose=2 "GP5 PDF.app"
ditto -c -k --sequesterRsrc --keepParent "GP5 PDF.app" "GP5-PDF-macos-signed.zip"
```

Signing/notarization is a separate release action involving certificates and an
Apple submission. The Windows-created staging artifacts have not passed it.

## Required Mac runtime QA

Run the final app on both Intel and Apple Silicon, or explicitly report an untested
architecture. Check a clean launch, native GP5 file selection, cancellation, Korean
file/track names, instrument PDF contents/page breaks, existing-file preservation,
and conversion with network access unavailable. Open the resulting PDFs in Preview.
Keep signing checks, conversion results, and the exact artifact hashes with the
release evidence. Do not label a Windows archive-only audit as Mac runtime QA.

References: [Electron packaging](https://www.electronjs.org/docs/latest/tutorial/application-distribution),
[Electron signing](https://www.electronjs.org/docs/latest/tutorial/code-signing),
[electron-builder cross-platform limits](https://www.electron.build/v26/docs/features/multi-platform-build/),
[Apple notarization workflow](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).
