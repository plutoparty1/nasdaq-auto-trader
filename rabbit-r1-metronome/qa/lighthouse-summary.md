# PULSE Lighthouse audit — INCONCLUSIVE

No Lighthouse scores were produced. Performance, accessibility, best-practices, and SEO remain **unverified by Lighthouse** for both pages and both profiles. The SDK context review passed separately; it does not establish a Lighthouse result.

| Page | Profile | Performance | Accessibility | Best practices | SEO | Completed runs |
| --- | --- | --- | --- | --- | --- | ---: |
| `/` | Mobile | Unverified | Unverified | Unverified | Unverified | 0/3 |
| `/` | Desktop | Unverified | Unverified | Unverified | Unverified | 0/3 |
| `/install.html` | Mobile | Unverified | Unverified | Unverified | Unverified | 0/3 |
| `/install.html` | Desktop | Unverified | Unverified | Unverified | Unverified | 0/3 |

The intended audit used installed Chrome via Playwright `channel: 'chrome'`, an isolated temporary profile, and the Lighthouse Node API attached through CDP port 9237. It did not use the Lighthouse CLI. An owned server on port 4187 served the final production `dist` files. Three runs per page/profile and median scores were planned; neither attempt reached a scoring result.

## Observed failures

1. The first mobile app run stopped during Lighthouse storage preparation:

   ```text
   Error: Protocol error (Storage.getUsageAndQuota): Protocol error (Storage.getUsageAndQuota): Quota information is not available
   ```

   Local Lighthouse 13.5.0 calls this CDP method from `core/gather/driver/storage.js:82`, before navigation/scoring. Chromium emits the quoted message for a failing storage-quota backend status; it does not establish that the protocol command is absent. [Chromium source](https://chromium.googlesource.com/chromium/src.git/+/91e03c28b9ece9806816a73c4dfe95f9b0363465/content/browser/devtools/protocol/storage_handler.cc)

2. A single retry using `chromium.launchPersistentContext('')` failed before browser initialization. Chrome logged:

   ```text
   Failed to create cache directory: ...\playwright_chromiumdev_profile-qS61qQ\GPUPersistentCache: 디스크 공간이 부족합니다. (0x70)
   Failed to open persistent cache files ... error: 2: 디스크 공간이 부족합니다. (0x70)
   ```

   The Korean message means insufficient disk space. Playwright then reported `browserType.launchPersistentContext: Failed to launch the browser process.`

C: had **0 free bytes** out of **239,370,432,512 total bytes**, confirmed independently by Win32_LogicalDisk, Get-Volume, Get-PSDrive, and .NET DriveInfo. Get-Volume reported Healthy/OK. The explicit Chrome cache error confirms disk exhaustion blocked this audit's browser launch. The precise backend mechanism behind the first quota error was not isolated.

Runtime evidence: Node v24.19.0, Lighthouse 13.5.0, Playwright 1.64.0, installed Chrome file version 154.0.8037.98. Chrome's version endpoint was not reached during the persistent-profile retry. Lighthouse's Node requirement (≥22.19) was satisfied. No category thresholds, storage checks, product content, or animations were suppressed.

## Cleanup and next run

- Both attempts ran the harness's `finally` cleanup for its owned server/browser.
- The persistent retry's Chrome log confirms temporary-directory cleanup finished.
- `Test-Path` returned `False` for the owned profile `C:\Users\u\AppData\Local\Temp\playwright_chromiumdev_profile-qS61qQ`.
- The final check found no TCP listeners on 4187 or 9237. Earlier closed connections were TIME_WAIT with OwningProcess 0.
- No unrelated files were deleted and no product source files were edited. The harness passed `node --check qa/lighthouse-audit.mjs`.

The lead reclaimed space from the session-added audit dependency environment after the attempts. The report writer subsequently observed 147,292,160 free bytes; the failed attempts were not rerun, as directed by the lead.

After sufficient disk space is available, ensure Lighthouse 13.5.0 and Playwright are installed and run `node qa/lighthouse-audit.mjs`. The harness runs all 12 audits, saves individual Lighthouse JSON reports, fingerprints the production inputs, and writes median results. Optional isolated port overrides are `PULSE_AUDIT_PORT` and `PULSE_AUDIT_DEBUG_PORT`.

Any completed loopback audit will still require a follow-up against the eventual hosted URL to include public DNS, TLS, and CDN behavior. Native r1 audio/timing and QR scanning remain separate device checks.

The machine-readable attempt evidence is [lighthouse-attempts.json](lighthouse-attempts.json); supporting investigation notes are [lighthouse-debug.md](lighthouse-debug.md).
