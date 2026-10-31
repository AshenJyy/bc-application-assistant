# Contributing

This project is a development preview. Start with [requirements](docs/REQUIREMENTS.md),
[coverage](docs/FIELD_COVERAGE.md) and [open milestones](docs/TASKS.md).

## Local checks

Use Windows x64, Python 3.12 and Node.js 22+. Create the development environment
and run the commands in the [README](README.md#develop-and-verify). Use the full
`tools/check.ps1 -BuildRelease` check before proposing a release.

Keep changes focused on one workflow or defect. Describe the observed problem,
resulting behavior, relevant tests and remaining limitations. Update coverage and
architectural decisions when the supported contract changes.

## Test data and browser work

- Use invented students, schools, identifiers and transcripts in tests and issues.
- Never commit real PSRs, profiles, screenshots, passwords, cookies or portal logs.
  Keep private local work under ignored `work/`; original source documents can
  stay in their existing locations.
- Use the documented host connection and observed UI. Do not add a hidden browser
  endpoint, unsupported protocol or framework-state mutation as a workaround.
- A passing fixture does not establish live support. Document synthetic,
  actual draft-save and independently verified results separately.
- Real-account tests need explicit authorization, a recoverable original state
  and restoration checks. Never submit, pay, attest or send invitations.

## Shared data and packaging

Keep one canonical profile with source references and explicit verification states,
not copied per-university profiles or invented academic facts. Keep future planning
interfaces internal until a documented integration exists.

Add new runtime files to `tools/release_files.json` and check that they work after
extraction outside the checkout. Dependency wheels are intentionally bundled for
offline setup; update their hashes together using `tools/lock_runtime.py` and
preserve embedded licenses and metadata.

Use [SECURITY.md](SECURITY.md) for sensitive reports. Ordinary bug reports must
contain only synthetic or redacted reproduction steps.
