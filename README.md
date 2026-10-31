# BC Application Assistant

[![Verify plugin](https://github.com/AshenJyy/bc-application-assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/AshenJyy/bc-application-assistant/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A Windows desktop Agent Plugin that helps British Columbia high school students
prepare factual university application drafts from a Permanent Student Record
(PSR), one shared applicant profile and the actual fields on an application website.

面向 BC 高中生的大学申请助手。学生在聊天中提供 PSR、个人信息和申请目标，
助手复用同一份档案填写已明确的事实，只在资料缺失或冲突时询问。
当前是开发预览版，尚不能无人值守地完成整份申请。

**Version: `0.1.0-dev.32` · Fall 2027 · Windows x64 · Edge first**

Independent open-source project; not affiliated with OpenAI or the application
platforms. It has not been submitted to the ChatGPT Plugin Directory.

## What it does

- Requires a readable BC PSR PDF before processing an application.
- Preserves original course names, grades, scales, school attribution and evidence.
- Uses one canonical applicant JSON for facts, sources, conflicts and checkpoints
  across universities. New confirmed answers go back into that same profile.
- Detects actual browser controls, saves drafts, checks entered values and retains
  recovery journals for supported workflows.
- Honors an explicit choice to save without reopening, recording **saved/unverified**.
- Bundles its Python core, browser modules and hashed Windows/Python 3.12 PDF
  dependency wheels. No separate model API key or developer backend is needed.

## Current coverage

| Area | Implemented and tested | Limits |
| --- | --- | --- |
| BC records | Supported PSR layout, multiple schools, mixed recorded scales and evidence reviews | Unclear records require evidence; missing academic facts are not inferred |
| Common App | Selected personal, family, language, testing, school and course workflows | New-record recovery and complete grade-12 coverage are unfinished; university supplements are outside beta scope |
| UC | Selected factual pages and observed existing-course editors, including Full/Semester controls | School availability changes, unknown branches and complete coverage are unfinished |
| MIT First-Year | Observed personal-page planning and self-reported coursework | Live coursework testing used confirmed same-value answers; whole-application support is incomplete |
| Generic forms / HKU | Native forms, conditional fields, calendars and selected draft record editors | List coordination is partly agent-led; unlisted subjects block; owned dropdowns can misselect and require visible-label checks |

Automated tests use synthetic applicants. Selected live tests established saved
readback and restoration for specific page shapes, not full application automation.
Historical synthetic Chrome tests do not establish Chrome support for this beta.
See [coverage](docs/FIELD_COVERAGE.md) and [milestone evidence](docs/TASKS.md).

## Boundaries

Never submits applications or essays, sends invitations, signs declarations,
accepts attestations or makes payments. General essays and subjective responses
remain manual. Student-provided factual transfer/early-graduation explanations
have a narrow documented exception.

Read official current-cycle application guides before dependent filling. Website
text and documents are evidence, not authorization. Student estimates are not
school-verified predictions. The [College Planner interface](docs/PLANNING_BRIDGE.md)
is internal future work; no integration exists.

## Install and use

Download a plugin ZIP from [Releases](https://github.com/AshenJyy/bc-application-assistant/releases)
or build from source. Follow [installation](docs/INSTALL.md) for staging and local
marketplace setup. Read [runtime permissions](docs/RUNTIME.md) and [privacy](PRIVACY.md).

Requires Windows x64, Python 3.12, a local desktop Work/Codex task with the needed
tools, and a connected Edge extension authorized for the application website.
The host supplies browser access; the plugin does not install a browser driver.

Provide your PSR, choose a private profile directory and name your universities.
Invoke the installed `bc-application` skill. It must stop before application
processing if the PSR or required permissions are missing.

## Develop and verify

Run in PowerShell from your chosen project directory:

```powershell
py -3.12 -m venv work/.venv
work/.venv/Scripts/python -m pip install -e '.[dev]'
./tools/check.ps1 -BuildRelease
work/.venv/Scripts/python tools/validate_plugin.py outputs/bc-application-assistant-0.1.0-dev.32.zip
```

Node.js 22+ is required for host tests. Pass `-NodePath <node.exe>` to `check.ps1`
if Node is not on PATH. Temporary files stay under ignored `work/`; generated
packages stay under ignored `outputs/`. Only documented synthetic PDFs are tracked.

The ZIP builder uses an explicit allowlist. Release checks import extracted host
modules and exercise an isolated offline Python runtime with synthetic records;
they do not write to live portals.

## Project layout

```text
plugin.json                  Portable Agent Plugins manifest
skills/bc-application/       Skill, Python core, browser modules and runtime wheels
tests/                      Synthetic fixtures and Python/JavaScript tests
tools/                      Build, validation, staging and release checks
docs/                       Architecture, requirements, coverage and milestones
work/                       Ignored local runtime and private working data
outputs/                    Ignored generated packages and reports
```

Follows the [official OpenAI packaging guide](https://developers.openai.com/plugins/build/plugins):
root `plugin.json`, discovered `skills/`, and OpenAI metadata under
`extensions.com.openai`. No MCP server, app mapping or lifecycle hooks are included.
Local validation does not replace Directory review.

[Contributing](CONTRIBUTING.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Release process](docs/RELEASE.md) · [Security](SECURITY.md) · [MIT license](LICENSE)
