# Lighthouse harness investigation

Ownership is limited to `qa/lighthouse-*`; this file records investigation evidence without modifying the repository's root debug journal or unrelated files.

Runtime: Node v24.19.0, Lighthouse 13.5.0, installed Chrome controlled through Playwright. Owned ports: HTTP 4187, CDP 9237. No product source edits.

Hypotheses:

1. A Playwright incognito/default-context mismatch prevents quota initialization. Distinguishing test: retry in an isolated regular persistent Chrome profile with all Lighthouse storage checks enabled.
2. Lighthouse and installed Chrome have incompatible CDP versions. Distinguishing evidence: CDP's response reports a backend quota error rather than an unknown command; capture Chrome version during retry.
3. Disk exhaustion prevents Chrome storage-quota initialization. Distinguishing evidence: Windows volume free-byte values and the same operation after any authorized reclamation. No unrelated files may be deleted.

Red reproduction: `node qa/lighthouse-audit.mjs` failed on the first mobile app run before scoring:

```text
Error: Protocol error (Storage.getUsageAndQuota): Protocol error (Storage.getUsageAndQuota): Quota information is not available
```

Windows metadata evidence: Win32_LogicalDisk, Get-Volume, Get-PSDrive, and .NET DriveInfo each report C: with 0 free bytes; total 239370432512 bytes. This supports disk pressure, but causality has not been confirmed.

The failed harness closed its owned Chrome and server. Port checks showed only TIME_WAIT connections with OwningProcess 0. The retry changes only the harness launch to `chromium.launchPersistentContext('')`, whose empty profile path lets Playwright create and clean up its own temporary profile. No storage audit is suppressed.
