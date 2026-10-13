# Maintaining GP5 PDF Web

Use Node.js 24 LTS and npm. Clone this dedicated repository and run:

```sh
npm ci
npx playwright install chromium webkit firefox
npm run dev
```

On Linux, use `npx playwright install --with-deps chromium webkit firefox` to install browser system libraries too.

Before merging:

```sh
npm run check
npm test
npm run test:browser
npm run build
```

Playwright builds the production site, serves the unchanged build under `/gp5-qa/`, chooses actual GP5 files, and downloads actual PDFs inside ZIPs. Use `GP5_QA_URL` to run against a separately hosted build. Browser checks cover extended CP949 Korean that Node's decoder cannot reliably test. Do not replace these checks with a mock renderer.

Keep changes within the responsibilities in [ARCHITECTURE.md](ARCHITECTURE.md). Add a regression when fixing a parsing, pagination, cancellation, or download boundary. Keep error messages actionable and Korean UI text readable at 320px. A completed-file count alone does not guarantee a downloadable ZIP.

## Dependencies and releases

Update exact dependency versions and the lockfile together. Run the entire suite and inspect PDF output when changing alphaTab, PDFKit, fonts, or the SVG adapter. Review generated `public/LICENSES/npm-notices.txt` and `public/THIRD_PARTY.md`. Check upstream release notes and review SHA changes before upgrading Actions.

1. Update `package.json` and its lockfile version, then `CHANGELOG.md`.
2. Open a pull request; merge only after the browser and unit checks pass.
3. A push to `main` automatically updates the site after checks pass.
4. Tag the tested commit with the matching version, for example `v1.0.1`, and push the tag.
5. The release workflow checks the version, rebuilds and tests, then publishes source/site ZIPs and `SHA256SUMS.txt` to GitHub Releases.

For local archives, run `npm run build && npm run package`. Never commit `dist/`, `release/`, private GP5 files, browser profiles, or local QA artifacts. The packaging script uses an explicit source allowlist. The source archive is a complete standalone project with `.github` workflows.

Configure **Settings → Pages → Source → GitHub Actions** in a new repository. The Pages deployment uses short-lived GitHub permissions; no personal access token is needed in repository secrets. If CI fails, read the failing test before rerunning. Do not publish a release from a failed or untested commit.

Failed browser runs upload their JSON report, screenshots and traces as workflow artifacts for seven days. Download them from the failed Actions run when investigating a browser-only regression.
