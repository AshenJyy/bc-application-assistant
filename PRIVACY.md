# Privacy and data handling

The plugin has no developer-operated backend, telemetry, analytics, or credential
store. The host's model service may receive PSR excerpts, student answers, browser
content, screenshots, and tool results needed for the task. Local execution is
not offline model inference. Host/provider policies and retention settings apply.

The applicant chooses a local directory. The plugin stores one complete applicant JSON
there, including facts, evidence references, verification states, and checkpoints.
Before filling, the same JSON temporarily retains the original page values as a
rollback journal, including untouched fields that a website might normalize. It
is cleared after verified restoration; it is not a second applicant file.
Host-relay stdout may contain personal field values and is private task content,
not a public log or issue report. Do not retain separate observation/plan JSONs
for a real applicant. Synthetic browser test artifacts contain invented values.
The JSON is plaintext, not encrypted by this plugin. Source PDFs remain in their
existing locations. Do not store passwords, OTPs, payment details, cookies, or
browser authentication tokens in it. Temporary files are not additional profiles.

For scanned supplemental records, a temporary PNG page may be rendered in the
same private directory for explicit visual inspection. Remove that PNG afterward;
retain only its document hash, page, rectangle and relevant quote in the existing
JSON. Never publish page images or treat rendering as automatic OCR/verification.

PSR and transcript data are read only for the authorized application task. Academic
source references include hashes, pages, and raw text; these are themselves private.
Student statements retain their student-reported status. Prior chats are read only
when authorized and useful; extracted facts require applicant confirmation.

Official application guides and public exam-release schedules are separate public
sources, not proof of personal scores. Reuse a single cached guide and profile
reference across schools. A masked derived-percentage field may require a normal
clipboard paste; the host writer places only that bounded calculated number on
the clipboard and does not read its previous contents.

Application websites receive data entered into their forms, including autosaved
drafts. Never equate a draft write with a local-only action. The plugin requests the
host permissions it needs and never submits, signs, invites, or pays automatically.

Real documents, applicant JSON, credentials, snapshots, private test outputs, and
screenshots must not enter the repository or release ZIP. An explicit release
allowlist is used; a local exclusion check also scans generated packages before
delivery. Tests contain only invented students and schools.

Delete private files through the applicant's chosen file workflow when requested.
Deleting local JSON does not delete host conversations or data stored by universities.
Developers must use synthetic issue reports and redact logs before sharing them.
