# Release process

The first public GitHub snapshot is the `0.1.0-dev.32` development preview.
GitHub publication is separate from ChatGPT Plugin Directory submission. The
package has not received Directory review or approval.

The initial public branch uses an audited source snapshot. Private local
development history and applicant workspaces are intentionally not published.
Push the public branch explicitly, never private branches with `--all` or `--mirror`.

## Prepare

1. Update the README, coverage, milestone evidence and known limitations. Keep
   synthetic evidence, draft-save receipts and independently verified results
   distinct. Preserve the known owned-dropdown limitation.
2. Check `plugin.json`, `pyproject.toml` and the Python runtime version agree.
3. Review the tracked tree and all history being pushed. Exclude private files,
   student PDFs, profiles, images, account details and secrets. Only documented
   synthetic PDFs under `tests/fixtures/` belong in Git.
4. Check current official [packaging](https://developers.openai.com/plugins/build/plugins)
   and [submission errors](https://developers.openai.com/plugins/deploy/submission-errors).
   The vendored schema and local validator cover public format rules, not private
   Directory scans or review decisions.

## Verify and build

From the repository root in PowerShell:

```powershell
./tools/check.ps1 -BuildRelease
```

This runs Python and host tests, builds the Python wheel and allowlisted ZIP,
validates structure/imports, and exercises the extracted offline runtime using
synthetic records. It writes the ZIP and validation reports under `outputs/`.
GitHub Actions runs the same Windows check and uploads only generated packages
and reports as its downloadable artifact.

## Publish

- Commit verified source and public documentation. Keep private work excluded.
- Push the checked history and verify the remote head.
- Create a **prerelease** at that exact commit. Attach only the plugin ZIP,
  archive validation report, clean-runtime report and SHA-256 checksum file.
- State the Windows/Edge requirements and unfinished M5 scope. Do not call this
  stable or Directory-approved.
- Verify uploaded asset names and checksums. Report GitHub Actions separately;
  a successful push alone does not establish passing CI.

Use `tools/stage_plugin.py <release.zip>` for local installation. Never install
or upload the private development checkout as a plugin package.
