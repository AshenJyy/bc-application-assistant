# Runtime and permissions

Windows x64 and Python 3.12 are beta prerequisites. Run from a local Work or Codex
task with shell/file access. Model inference remains service-hosted; Python can
execute locally. This plugin has no MCP server, hooks, background service, or API key.

Use the Python runtime exposed by the host when available, otherwise an existing
Python 3.12 installation. Do not hardcode a developer's machine path.
Run `python <installed-skill>/scripts/run.py preflight --psr <file> --profile-dir
<chosen-directory> --browser edge`. The directory must already exist.
The checker briefly creates and deletes one empty permission-probe file there.
PDF dependencies are bundled under `assets/wheels`, with a hash-locked
`runtime-requirements.txt`. Run `python <installed-skill>/scripts/bootstrap.py
--runtime-dir <chosen-runtime-directory>` to prepare an isolated venv offline.
Use its `Scripts/python.exe` for preflight and extraction. Python itself is a
host/runtime prerequisite, not bundled in the portable plugin.

Python preflight cannot inspect host browser authorization. The agent must separately
check the host's available Edge tools, connected browser profile, observed
application origin, site permissions, and login state. Do not declare readiness
until both file/runtime checks and live browser checks pass. Request a missing
permission; pause if it is denied or the host does not expose the needed capability.

Connect Edge through the desktop app's Settings > Computer Use setup and the
official ChatGPT extension. The applicant handles login, passwords, OTPs, and any
unsupported file dialog. Read the host-provided tool documentation before operating
the browser. This package does not import internal host modules or ship browser drivers.

For masked percentage inputs, the host must expose the documented browser
clipboard-write and keyboard APIs. The writer puts only the source-backed derived
percentage on the clipboard, pastes it into the observed field and blurs it. It
does not read clipboard contents, call private framework methods or write hidden
inputs. A normal visible value alone may not satisfy the website's number widget;
the website's validation result remains required.

Host permissions still apply to draft writes. This plugin never overrides them.
Account testing must be reversible and restore saved values. Autosave means typing
can already persist information; capture the initial state before typing.

Current milestone: M5 verification in progress; documented host relay and three-system
Chrome and Edge synthetic tests work. Real Common App Personal Information passed
save/readback/restoration. MIT coursework passed same-value selection/save/revisit
and full visible state comparison; UC Personal information passed the analogous
twelve-control/seven-section/32-page-state same-value test. Real changed-value MIT/UC Personal recovery and complete
coverage remain pending. See the packaged
README and root docs for the implementation status and installation procedure.
