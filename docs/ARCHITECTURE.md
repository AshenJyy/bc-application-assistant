# Architecture decisions

The final product goal and current boundaries are in [REQUIREMENTS](REQUIREMENTS.md).
The recorded development evidence below does not establish complete student-led
application coverage.

## ADR-001: Portable skills-only package (M0)

Use the Agent Plugins 1.0.0 root manifest with `requires_local_executor: true`.
The Python core lives in the skill's scripts directory so installed skill resources
resolve without the development checkout. Setuptools discovers the same package.
No MCP, hooks, `.app.json`, or compatibility manifest is necessary.

## ADR-002: Separate core and browser host (M0)

Academic parsing and future canonical models must not import host browser internals.
The skill uses the host's exposed documented Chrome/Edge capability at runtime.
Python preflight checks only Python-visible facts and cannot certify browser access.
University adapters and page verification will be implemented in M3/M4; M0 does
not ship placeholder adapters that appear functional. Future MCP interfaces stay internal.

## ADR-003: Release by explicit allowlist (M0)

Ship only enumerated runtime/resources/docs. Never recursively zip the checkout.
Validate the official manifest JSON Schema plus published ZIP rules. The validator
is a local conformance check, not OpenAI's private portal security/review scans.
Use reproducible ZIP timestamps; reject symlinks, traversal and case collisions.

## ADR-004: Evidence before convenience (M0)

Preserve source rows and unknowns, not guessed semesters or converted grades.
Student-reported facts and document extraction are distinct verification states.
Writing a whole page requires observed fields and explicit factual answers; manual
fields and final actions remain student-controlled. Real-account tests must restore.

## ADR-005: One private profile (M2)

One JSON holds canonical data plus per-application progress. Source documents
remain external. Temporary atomic writes are allowed but do not become a second
retained profile. Revision/checkpoint controls must prevent stale overwrites.

## ADR-006: College Planner seam without invented integration (M0)

Use capability discovery and profile/target/checkpoint references for an internal
planning provider. Model requirements, deadlines, task progress, aid, scholarships,
and fee waivers from the announced product capabilities. There is no API client;
the default is unavailable. Details and official source: [planning bridge](PLANNING_BRIDGE.md).

## ADR-007: Raw columns and structural continuation (M1)

Recognize the observed ten-column ruled PSR header, then accept continuation
tables only with matching grid geometry and a known school/year context.
Store source metadata and contexts once; courses reference them and retain raw
cell values plus page/table/row/bbox evidence. Blank values and course periods stay
unknown. Extracted records require human review, never automatic verification.
Unexplained markers/results require a transcript and student clarification.
Scanned or unsupported layouts stop; no untested OCR guessing is enabled.

## ADR-008: Offline Windows PDF runtime (M1)

Bundle one locked set of Windows x64/Python 3.12 dependency wheels, with hashes and
upstream distribution licenses. Bootstrap uses `--no-index --require-hashes` in
a separate chosen runtime directory. Python is an explicit host prerequisite.
Stage local installs from the validated release ZIP, excluding the private workspace.

## ADR-009: Explicit, scoped student interpretations (M2)

The parser continues to preserve unexplained markers. The profile accepts a
student statement linked to specific records, keeping pending clarification and
pending transcript review separate. No global E-to-credit/exam rule is introduced.
Explicit exam scores are separate facts with their own scale/source; student
reports never become document-verified through inference or marker explanation.

## ADR-010: Single-file transactions and resume (M2)

Use one versioned canonical JSON, immutable PSR payload/digest, atomic replacement,
loaded-file hash plus revision checks and a Windows named mutex. Cross-process
contention fails safely, stale snapshots cannot overwrite newer/manual edits,
failed replacement preserves the previous file, and source documents remain
external hash/path references. M1 extraction migrates in place; future schemas fail.

## ADR-011: Page data gate and shared target references (M2)

Three systems bind observed field keys to shared fact IDs. Missing data blocks
only the affected page; conflicts, changed sources, unresolved academic reviews
and manual fields remain blockers. New conditional requirements reopen a checkpoint.
Data readiness never claims host authorization or page save/readback. Browser
states/actions are reserved for M3/M4, not fabricated by the core model.

## ADR-012: Host-tool relay and observed controls (M3)

The JS bridge receives a documented extension tab, observes visible DOM controls,
and writes through supported locators. Python processes serializable observations
and persists checkpoints without importing browser internals. No independent
browser driver, CDP, endpoint calls or framework state is used. Unknown controls,
manual fields and non-unique draft-save actions fail closed. Native options use
exact matches; academic columns retain original values and course review gates.

## ADR-013: Durable rollback and saved readback (M3)

Persist changed fields' original values in the same canonical JSON before typing.
Hash the entire page values/control structure; save, revisit, and compare all
values before marking verified. Interruptions retain `needs_restore`; factual
edits are blocked during an active browser transaction. Restore tests verify the
full original value hash before clearing the journal. If completion metadata
cannot be restored, real-account mutation tests are blocked rather than claimed.

## ADR-014: Three adapters with shared factual references (M4)

UC names, MIT visible labels/address headers and Common App common-section routes
bind to the same canonical facts. A single explicit ISO birth date is losslessly
formatted for each observed control; inconsistent legacy fragments block. Only
recognized factual name/address textareas are editable. Unknown narratives and
custom controls fail closed. A Common App Continue action must match the actual
common-section ID; college supplements and Writing remain outside automatic filling.

## ADR-015: Snapshot all page values and check before saving (M5 verification)

Supersede ADR-013's delta-only journal: a website can normalize an untouched field
when another field changes. Keep the original page values temporarily in the same
canonical JSON, check the entire expected value hash before saving, and retain
saved readback afterward. Unexpected side effects stop before a draft save;
restoration has the original values available. This is necessary rollback data,
not an additional applicant file. Clear it only after verified restoration.

## ADR-016: Recovery precedes changed page requirements (M5 verification)

Detect an active browser transaction before changing any checkpoint requirements
or planning another page. Conditional questions, manual fields and optional
choices must not reset a pending checkpoint to collecting and discard its journal.
The standalone checkpoint API applies the same guard; persisted factual-edit
protection uses the shared active-state definition. Verified real-account tests
remain active until restoration clears their journal.

## ADR-017: Check documentary quotes at evidence entry (M5 verification)

When adding documentary facts or resolving academic reviews, verify the original
document hash and find the supplied quote on its specified page. Normalize only
Unicode and layout whitespace; do not interpret grades or promote student reports.
The host still inspects relevance. Image-only evidence remains unresolved instead
of inventing OCR. Keep structural validation independent of file availability so
resuming/relinking a missing source remains possible; page gates check source hashes.

## ADR-018: Observed positions for repeated native IDs (M5 verification)

Common App's actual course dialog reuses IDs across semester/final inputs. Record
the selector match count and observed index, prefer accessible labels, reject
duplicate identities, and recheck the count before using a documented locator's
position. Page fingerprints make this identity observation-specific. Native
selector support does not imply support for custom dropdowns or dialog saves.
Course-completion attestations remain manual even with explicit fact bindings.

## ADR-019: Trust explicit PSR columns; scope supplemental gates (M5 clarification)

Record each page's original course columns as checkpoint requirements. After an
applicant explains a marker for specific records, their explicit original grades,
credits and other PSR columns need no redundant transcript confirmation. Preserve
the raw evidence/status and unresolved supplemental review for later questions;
missing grades, invalid results and supplemental schedules still block. A course
name binds to the actual `course_description` cell, with `description` retained as
a lossless compatibility alias. Do not create a copied grade/name fact.

## ADR-020: Manual review of scanned supplements (M5 verification)

Extend ADR-017 with an explicit visual-review method for registered supplemental
PDFs. Render one bounded temporary page beside the private profile, inspect it
through the host image viewer, and retain only hash/page/rectangle/relevant quote
in the same JSON. Validate source bytes and locator bounds, require the scoped
student statement, and declare the method as manual; do not pretend a pixel view
was automatic OCR or let it promote an oral fact to document extraction. Delete
the temporary page image after inspection. The PSR parser's text-layer requirement
is unchanged. Original-column page gates ignore unneeded schedule reviews and
their documents, so a missing unrelated supplement cannot invalidate a clear PSR grade.

## ADR-021: Explicit MIT subject status and untouched empty notes (M5 verification)

Bind the four observed subject selectors to explicit student-reported canonical
statuses. Do not derive them, subject classification or Year from PSR names or
website answers. Restrict the empty-note exception to the two observed optional
coursework textareas on this MIT page. Required, selected, edited, nonempty and
unknown narratives still block a page save. The host checks this again before
saving, including untouched consent/attestation fields, so a matching fabricated
plan cannot transmit manual answers. This does not implement the course table.

## ADR-022: Visible UC wrapper labels and native option groups (M5 verification)

The actual UC course editor includes incorrect label-for associations. When direct
accessible/native labels are absent, read a field wrapper only if it contains
one label and exactly one visible control. Exclude hidden, collapsed and inert
controls. Retain native optgroup labels: duplicate Computer Science labels must
not silently choose a category. Exact option matching continues to reject an
ambiguous label; category/honor/period choices remain applicant decisions.
Chrome synthetic whole-page saves/readback/restoration now complement Edge tests.
Real-account inspection made no saved changes and returned to its starting page.

## ADR-023: Distinct identity questions and page-specific mappings (M5 live test)

Common App asks about materials under a former legal name; UC asks about a past
legal name. Keep those booleans separate. A changed name without old-name materials
can produce different answers. Restrict Common App's automatic student-identity
mappings to the observed Personal Information section; parent/family questions
with the same labels require explicit factual bindings.

## ADR-024: Restore observed values and visible navigation states (M5 live test)

For an already-complete factual Common App native page, record its original
controls and all exposed navigation statuses in the same checkpoint before a
write. Require an observed current-page key and matching baseline state hash,
not a boolean alone. Check all original statuses as well as values on restoration,
retaining recovery when either differs. Status drift may not prevent generating
or applying original-value recovery. Clear temporary snapshots only after verified
restoration. This covers observed user-facing state, not invisible backend audit
timestamps, and does not establish a recovery method for MIT/UC or custom dialogs.

## ADR-025: Wait for separately loaded status components (M5 live test)

The first real Common App test returned native controls before navigation statuses
had hydrated, causing a verification failure. Original values and statuses were
restored and verified from a fresh read. After fixing the wait, a second real test
passed changed-value save/revisit/readback and complete restoration. Wait for the
known native anchor and each original accessible status component after navigation;
do not replace a missing status with an assumed value or poll with fixed sleeps.

## ADR-026: Read custom choices without promoting filling support (M5 inspection)

Inspect an observed closed Material single-select through its uniquely labeled
ARIA listbox. Read option labels and selected/disabled state, close with Escape,
and verify the whole observation is unchanged. Never read private component state.
Keep required custom fields unsupported until their binding, filling, draft save,
reopening and restoration contracts are implemented and verified. Send factual
operation batches over stdin instead of creating another personal-data file.

## ADR-027: Stable observed radio question identity (M5 live regression)

Common App's SPA regenerates `mat-radio-group` names after navigation. On the
Personal Information route only, use the shared question ID from actually observed
native option IDs as the logical radio key. Require matching option question IDs,
unique locators and a labeled group; reject duplicate question identities. Retain
all selectors, option labels/values/order and multiplicity. Omit only the generated
group name from saved-structure comparison. The complete observation fingerprint
still includes that name, so a stale pre-write page cannot pass. Python validates
the explicit identity kind before normalization. A real changed-value workflow
started after SPA navigation and passed save/readback/full restoration across name
regeneration. Restrict synthetic restoration exemptions to loopback port 8765 in
both host and data layers; a flag cannot authorize a real MIT/UC test.

## ADR-028: UTF-8 host relay and conflicting requirement evidence (M5 inspection)

Real MIT text contains typographic punctuation. The Windows legacy pipe decoder
introduced surrogate characters and prevented planning; configure CLI stdin/stdout
as strict UTF-8 before JSON handling. A subprocess test forces legacy pipe defaults
and preserves accented names, Chinese and smart punctuation in one canonical file.
Treat an observed optional label plus a required signal as a conflict. Do not ask
for an invented preferred surname or ignore either signal. Block planning and host
save even when a supplied/fabricated value would satisfy native validation.

## ADR-029: Detect editable record collections without copying row data (M5 inspection)

Actual MIT school and test summaries have editor links but no input fields; the
coursework page has native subject-status controls alongside an unimplemented
course table. Observe visible table headers, row counts and known edit-link counts
through the public DOM. Store no row contents or person names in this metadata.
Validate the collection contract and retain it in the structural fingerprint.
The core and host both block writes/saves until nested editors and their recovery
are implemented. An empty field array cannot imply complete school/test coverage.

## ADR-030: Scope the existing Common App grade dialog and its term rules

The observed modal mixes proficiency text inputs, percentage Material selects and
unused required-looking term cells. An explicit known-origin/route/modal scope
promotes only public MAT-SELECT single selects and excludes the parent's reporting
attestation. Group term controls by observed Transcript/Course ARIA labels; require
one applicable grade and credit per course, or its explicit N/A checkbox. Suppress
only native valueMissing for unused blank periods, never aria-invalid or malformed
nonempty values. Python validates row/label/control/group correspondence. Every
nonempty grade/credit binds directly to its original PSR column; classification,
year, period placement and N/A require explicit student confirmation. Preserve
raw names and unwrap PDF layout only for one-line course-name display. The official
[Common App reporting guide](https://www.commonapp.org/files/webinar_decks/Academic-Record-Reporting.pdf)
and the live current editor establish the term rule.

## ADR-031: Persist modal recovery and verify its freshly reopened parent

Existing-course edits use a separate injected host port. Read all choices from a
uniquely labeled public listbox, compare them freshly before selection and require
an exact enabled label. No private component value or undocumented browser API is
used. Selecting the same source-backed nonempty value is explicit reaffirmation,
not a changed-score test. Block header reconfiguration, new rows and initially
blank Material writes/clearing. Persist plan/choice cache, every original value,
parent summary/checkbox and navigation states in the one checkpoint before writes.
Recovery can resume after a process restart using only that profile and fresh UI.

Save only the known modal draft button. Reload/reopen to verify the entire dialog
and fresh parent, retaining the journal if either differs. Never accept the outer
reporting attestation during filling or recovery. Actual testing exposed Escape
from a refocused combobox closing the parent asynchronously; clicking the modal
heading also failed to dismiss a list on another grade page. Send Escape to the
actual open listbox, which handles its own keyboard event, and wait for closure.
These interrupted inspections had no value changes; original values were checked
before continuing.

The real 9th Grade test changed eight PSR-backed course names, reselected the same
original percentage and saved/reopened successfully. All 98 original values,
13 visible statuses and full parent baseline were then restored and verified.
This does not establish new-record, changed-score, other-grade or MIT/UC recovery.

## ADR-032: Bind repeated record IDs to the actual page

Real 10th/11th Grade inspection showed the same `courseNameControl_T1C1` and
term/header IDs represent different courses in every grade. Add optional
`page_path` to factual/raw-record binding operations and keep references in the
existing target's `page_field_bindings`. Do not duplicate canonical facts, school
profiles or PSR records. Common App grade routes reject legacy global bindings;
explicit legacy scoping moves selected references with conflict checks. Other
adapters can also use page-specific overrides. Validate paths and referenced
records/facts on every profile load/save.

Cross-grade tests prove a ready 9th Grade binding set cannot write 10th Grade,
even if legacy flat bindings remain. Real 10th/11th observations likewise produced
zero-write blocked plans before their own confirmed references were supplied.
The student then confirmed their existing metadata separately. Changed-name saves
and restoration passed for 94 and 138 controls, 13 statuses per page, including
mixed semester/yearly AP records in 11th Grade. Successful dropdown selection
never sends a second Escape during its asynchronous closure. Keyboard activation
targets only the known modal draft button on long grids. A delayed closure keeps
recovery intact; the corrected full 11th Grade flow passed.

## ADR-033: Model the MIT conditional coursework requirement explicitly

Observe the literal Classes/STEM instructions and the public adjacent subject/year
question pairs. Require all eight explicit student facts, including an explicit
unlisted/not-taken reason for a blank year. Never infer Year from PSR course levels,
completion dates, AP equivalency credits or current website answers. A will-not-take
status and 9th–12th year conflict and stop the page. Associate Year semantically,
not by generated Slate UUID or selector order.

The collection exception is limited to the exact empty U.S.-only Classes table,
with one Add New control and confirmed Canada/non-U.S.-system facts. Both facts and
their source/conflict checks enter the normal checkpoint data gate. Populated,
additional or differently labeled tables remain blocked. The generic host port
continues to reject collections; only the dedicated coursework port uses this
prepared policy. Whole structures include instructions/pair metadata and the full
URL, so a different query-based MIT form cannot reuse the prepared observation.

## ADR-034: Verify MIT review and draft state through public pages

MIT exposes no Common App-style completion badges. The coursework port captures
every visible review error/warning plus the unique First-Year In Progress draft
and blank submitted cell. It returns to the current form and proves read-only
navigation left all controls unchanged. Status collection must never navigate away
from an unsaved draft: after the batch, a local observation is passed to the unique
draft-save. Saved revisit then recaptures review/portal state. Only section/message/
route labels are kept, not review answers, credentials or an extra applicant file.

Persist the plan and original values/status in the existing canonical checkpoint
for restart recovery. A zero-change test needs no second restoration save, but
clears recovery only after full original values AND status comparison. Missing,
changed or ambiguous evidence stops with the journal retained. An actual eight-value
same-value selection/save/revisit passed for ten controls, four errors, two warnings
and In Progress draft state. Simulated changed-value restoration passed; real
changed-value MIT recovery remains unverified and is not claimed.

## ADR-035: Preserve UC review state using visible application navigation

The dedicated UC Personal information port captures the complete seven-section
review and every Edit/To do route, plus the unique Fall 2027 Open application marker.
Only public labels/routes are kept, without copying applicant answers. After
Application status, reopen the actual term link and use the actual Edit control:
direct form URLs were observed to bounce back to the status page. Read-only status
inspection must prove the whole original form unchanged. Never navigate away from
unsaved edits to collect status. The port requires the twelve observed factual
controls and explicit No answers for the tested conditional questions; other
configurations and new controls stop. An exact China display alias preserves the
shared country fact. Real same-value saved revisit passed; changed-value recovery
on the real UC account remains unverified.

## ADR-036: Reapply source-backed dependent controls after their parents

Actual UC testing showed selecting the same birth country clears City. Whole-page
validation caught the unexpected blank before draft save. The original city was
restored locally from the canonical journal and the unchanged saved form/status
were verified before clearing recovery. A parent write therefore schedules its
already-resolved child after the parent: City after Country, Day after date parents.
This never extracts evidence from current website values or creates missing facts.
Unresolved children stop the plan. The corrected full native selection/reapplication
batch passed actual saved revisit of all twelve values and 39 visible states.

Unsaved abort recovery receives the persisted original metadata/hash, restores
local originals before navigation, then rereads the saved form/status. It cannot
clear recovery on a matching local screen alone, nor perform a second save merely
to clear a zero-change journal. Synthetic tests model the actual clearing behavior,
unexpected reset, dependent order, missing evidence and restart/status drift.

## ADR-037: Prioritize Edge for the first beta

Product scope now prioritizes Edge on Windows. Skill preflight and browser selection
use Edge; Chrome real-portal validation is deferred. Keep the generic browser
interface and earlier synthetic regressions for reuse, without presenting them as
current Chrome beta support. A missing Edge connection requires reconnection rather
than switching browser families or falling back to the in-app browser. Development
checks accept an explicit existing host Node executable when it is absent from PATH.

## ADR-038: Bind UC existing course rows to their actual year and summary

UC reuses row IDs across grade editors. Require exact page-path bindings with no
global fallback, explicit retained classifications/NO placements and direct PSR
name/mark references. Read summary columns by their visible headers: 9th/10th have
a grading-system column while the observed 11th does not. A school/year/context
fingerprint, original summary hash and all native control values enter the same
checkpoint. Normal saved summaries may reflect factual name changes; restoration
must match the entire original summary and every original field/status.

Unknown rows, controls, selectors, narratives and reconfiguration stop. The explicit
student AP Yearly choice blocks AP rows still configured as Semester. Enabling
Full year at school level and changing term/grade controls need a further workflow;
the current existing-course port must not perform those changes.

## ADR-039: Recover UC course-save completion effects without narrative input

Actual course-name saves cleared Academic history and Additional information
completion and exposed a To do Review entry. Restoring course values alone did not
restore those states. The observed Additional information page contains one empty
optional comments textarea and a plain Save & continue, without an attestation.
Saving it unchanged restored the original completion matrix. No Review Continue,
declaration, certification or application submission is required.

Preflight this exact empty auxiliary page before any further course write. Store
only its structure/value hashes in the same canonical checkpoint, and recheck the
whole shape and blank value before its draft-save. Any text, required/unknown field,
changed action or structure stops. After a course save/restoration, recover this
known completion effect and recapture all seven sections, child routes and draft
marker; clearing recovery still requires full original comparison. This narrow
empty-page recovery is not permission to write or transmit a narrative.

Share UC visible-status collection between personal and course ports. Course native
buttons use clicks and explicit navigation/heading waits. Interruptions, including
observed leave-page prompts or lost browser access, retain the journal; reconnect,
reread saved values and generate recovery from that journal before doing more work.
## ADR-040: Conditional UC course terms and original-state recovery

UC's actual school term warning states that changing availability requires
re-entering grades. The school preflight port therefore declines that warning;
it does not represent a school change as a harmless checkbox save. Warning
cancellation may require a fresh host call, bounded to two grounded No actions.
School identity, all school controls, related course snapshots and visible draft
state remain in the same canonical checkpoint until original verification.

After the student enables Full year, course rows expose native Full/Semester
selectors. A term change reconstructs grade fields. A separate refill transaction
validates all source references first, persists the original, selects terms,
reobserves the conditional controls, and persists a second exact-option grade plan
before grades are entered. Names, categories, honors, languages and scales are
retained. Completed grades refer to the same raw PSR record as the name; NO/IP/PL
require explicit student facts. Full has one grade, never duplicated into semesters.

Save verification checks every native field and actual summary cells after
reopening, plus visible review/draft state. Test recovery reselects original terms,
reobserves their original shape, replays original grades and compares the entire
original bundle before clearing recovery. Unsaved edits cancel without another
draft save. An originally reset/incomplete draft is recoverable by resuming the
intended refill; saving blank grades cannot establish original restoration.
Its journal remains until completion or a verified unsaved cancellation.

These contracts are independent of a live browser API. The host uses only
documented native locators. No new applicant JSON, source-PDF copies, hidden
endpoints, school-reset acceptance, declarations or submission actions are added.

## ADR-041: Group-aware choices and requirement coverage evidence

Actual UC native options repeat Computer Science under Mathematics and Science.
A factual select value can therefore be the exact `{label, group}` pair. Encoding
requires a unique enabled observed option with both values. A label-only duplicate
still blocks. Refining a retained choice uses the original student confirmation
and normal explicit conflict-resolution records, preserving student-reported status.

A PSR row with a clear course name but absent results can supply its name alone.
That does not resolve its missing-result review, supply a grade, or establish
completion. Requested result columns keep their original gates, and separate
student facts must supply status/term values.

Coverage is a read-only projection of actual supplied navigation and observed
fields, using isolated planning on an in-memory copy. Unknown pages, editable
record collections, missing facts, narratives and source issues remain explicit.
The inventory never saves website answers as facts, discards recovery, or claims
coverage of unobserved conditional paths. The same canonical profile remains
the only applicant data store.

## ADR-042: Shared fixed factual contracts and current IELTS replacement

Public observed native metadata is stored once in a packaged JSON resource used
by Python validation/binding and the JavaScript browser port. The new fixed-page
factory reuses UC Personal's whole-page save/revisit/recovery engine, with an exact
review href and native Save click. The actual IELTS editor showed that an Enter
activation can navigate without persisting; complete saved readback prevented a
false success, and the corrected native click persisted the requested update.
Unknown conditional fields, authorization controls and repeated record summaries
remain blocked. UC English-test cards are inventoried even without a table.

Exam dates preserve the explicitly supplied month/day precision in their own fact.
IELTS date and component controls resolve to the one canonical named exam, avoiding
cross-test reuse of native date/score IDs. The applicant explicitly requested only
their current IELTS record; the original report is referenced in place and no old
attempt was imported. Normal requested fills clear temporary original-value
journals only after saved verification; real/synthetic recovery tests explicitly
retain originals until restoration. This is not a general record-creation or
history-deletion API. The current actual update and two factual-page same-value
tests do not establish changed-score test recovery or full portal coverage.

## ADR-043: Rejected observations and unsupported page shapes stay explicit

The actual 32-route UC inventory exposed masked duplicate Contact radio values.
Coverage must report that rejected observation and continue listing other gaps;
it cannot promote invalid controls into a plan or copy raw answers into the report.
Captured, accepted and rejected counts are separate. Route origin/uniqueness and
pending-recovery errors still reject the entire request.

Some actual household, campus/major and scholarship/program pages have a Save
button but no native required signals. Their empty plans did not establish that
the questions were covered. Production UC planning and the host permission guard
now require a supported observed page contract. This deliberately keeps unknown
widgets/choices blocked until their actual shape and factual evidence are supported.

## ADR-044: Common App IELTS choices and explicit reporting facts

The actual flat IELTS editor uses input comboboxes inside NG-SELECT, not the
MAT-SELECT controls in grade dialogs. Share exact-option lifecycle code while
checking each public widget dialect and the input's aria-controls/listbox ID
association. Clear icons and calendar buttons are accepted only with exact observed
ownership; stable action identities ignore expected clear-icon insertion. A shared
JSON resource holds public labels/shape/content hash, never applicant answers.

Map the five scores and dates to the unique canonical current IELTS exam. Require
the actual sitting count separately from latest-only retention, explicit historical
highest confirmation and no planned future sitting for this first contract. Preserve
ISO date precision and scale; only display formatting changes. Never promote the
website's prefilled count into a factual source. Bind its generated radio identity
through observed question-option IDs only on the tagged IELTS route.

Whole-page verification checks all values after the actual Continue draft action,
revisit and navigation hydration. IELTS and Testing may become Complete; all unrelated
visible statuses must match. Keep one original journal in the canonical profile and
retain it on failure. An incomplete original is recovered by canceling unsaved edits,
not a blank invalid save. After a saved interruption, refresh a source-gated remaining
plan without replacing the original, changing other sections or creating an old exam.
Completed-original replay is separately synthetic-tested; no actual changed-value
restoration claim is made from an intended update. Clean package verification now
imports every extracted host module to catch omitted helper/JSON resources.

## ADR-045: Common App inventory cannot authorize uncontracted empty plans

Actual read-only inspection captured all 32 current Common App navigation pages.
The Responsibilities and circumstances page exposed optional-looking checkboxes
without the whole question's required signal; the generic planner incorrectly
reported an empty plan ready. This is a missing observed contract, not evidence
that an applicant has no circumstances to report. Production Common App now requires
the supported Personal Information page, scoped grade dialog or tagged IELTS contract
in both core planning and the host guard. Other native pages remain inspectable,
but neither existing answers nor an empty/optional-only plan authorize saving them.
The corrected inventory has 32 accepted observations and two source-ready flat pages;
grade dialogs are separate scopes. Receipts retain counts/routes/categories only.

## ADR-046: One collection agenda from observed targets and canonical facts

Combine supplied observed target inventories before asking questions. Deduplicate
mapped required gaps by canonical fact ID and group related fields. Known facts
are reused; source/academic review, manual work and unsupported fields remain
separate from student questions. An active journal defers collection and reports
recovery metadata. Bind output to the profile revision/hash and observation set;
persist actual answers through the existing one-file transaction model. Never keep
another answer copy in an agenda. Complete supported pages with identical values
are skipped; incomplete zero-difference pages may still need their ordinary draft
workflow. Completeness remains bounded to observed routes, not all unseen branches.
An agenda is readiness information. Matching entries still require independent
saved-draft readback and never set execution-verified; local unsaved values cannot
establish persistence. Use a separate working tab to preserve unsaved current work.
The dedicated `page-verify-matching` operation checks both source-ready zero-write
plans and the independent saved observation, recording only successful evidence
in the canonical checkpoint. A failed read does not create a rollback journal or
change the profile, because the verifier made no website changes to roll back.

## ADR-047: Shared Common App lifecycle and semantic language identities

Household and Language share the IELTS whole-page save/revisit/recovery lifecycle,
state comparison and source-gated resume. Public JSON stores page templates and
normalized content hashes. Repeated language fields bind to the applicant's explicit
ordered language IDs, labels and ability flags rather than one student's languages
or assumed question numbers. Existing counts must match; new rows/count changes are
left for a separate staged workflow. Other-language and independent-status branches
stop before unsupported saves. Optional children answers remain unchanged.

The language picker is paired with its next visible checkbox question through
observed DOM components and labels. Its legend ID plus native input value gives a
stable unique selector while generated checkbox IDs/names change. Reselecting a
language may reset flags; all five explicit abilities are reapplied after the name,
including during journal recovery even when an original flag initially matched.
Never infer language ability from tests. The shared generic bridge refuses these
dedicated contracts, forcing their semantic observer before input or draft saving.

## ADR-048: Language counts are a staged intended update

A changed count creates or removes visible controls, so the fixed-shape write plan
cannot span it. Require the explicit ordered list, each language name and all five
ability flags before selecting a count. Persist one original in the canonical JSON,
select only a known count option, then reobserve all generated groups and options.
Prepare a new whole-page plan from this shape before filling and saving. The normal
shared source gate and exact-option writer remain responsible for the final fields.

The transaction retains original values once, with a fingerprint of every required
fact/source reference. Resume rechecks sources, permissions, current count, public
associations and unrelated statuses; it never replaces the original. Verification
requires a saved revisit and complete whole-page values/statuses. Unsaved work can
be canceled only by independently verifying the original saved draft, including its
validation state. A saved interrupted intended update resumes toward the confirmed
facts; invalid blank originals must not be saved. This does not authorize real-account
changed-count QA or claim original recovery after such a saved test. Synthetic cases
cover empty pages, 1–5 rows, increment/decrement and both interruption stages. Actual
empty layouts and changed-count recovery still need real evidence. Generic fixed-shape
recovery refuses the staged journal so it cannot replay controls from the wrong count.
Common App preallocates hidden unused groups. Count-transition waits therefore use
visibility rather than DOM removal; the following semantic observation remains the
authority for the visible group count. This was corrected from an actual read-only
count-2 check and is enforced by a mounted-hidden-row regression fixture.

## ADR-049: A chat-led application workflow is the product acceptance unit

The student supplies information/documents and selects schools through chat. The
application coordinator should resolve official school routes, observe requirements,
reuse canonical facts, collect deduplicated gaps, create records, fill/save/revisit
whole pages and resume after interruption. The school list is independent of the
initial UC/MIT/Common App adapter set. Portal route discovery must retain official
source/cycle evidence and cannot invent support for a new school or platform.

Academic first-use flows take priority over adding more existing-record page tests.
Acceptance must start with a new synthetic student and empty application records,
then add another school using the same profile. School/year/course creation needs
exact saved attribution and duplicate prevention, in addition to original-grade/
scale preservation. Existing adapters and the read-only collection agenda are
components of this workflow, not its completion proof.

Missing/ambiguous/conflicting facts are the reason to ask an information question.
Persist the answer once with its source and refresh all dependent requirements.
Browser/login handoffs, excluded final actions and implementation gaps are separate
outcomes. Never ask for known data to compensate for a missing mapping. The current
single active journal remains authoritative: recovery precedes further mutation.
These requirements change product priorities; they do not claim a universal portal
runner, native ChatGPT profile integration or College Planner connection exists.

## ADR-050: Source-reference academic reports and staged first-use rows

First release assumes an available BC PSR and the BC curriculum, without inventing
one universal BC grading scale or schedule. The pure `academic.py` core compiles
transcript/course placement references stored as a fact in the single profile.
It reads original names/mark columns from the PSR, keeps exam scores separate, and
requires explicit metadata/term facts. Browser/future planning interfaces consume
references rather than a second copy of grades.
Each transcript also references its original PSR school ID. The core rejects a
course from another PSR school/grade or a group spanning original school years;
explicit portal labels/year formatting remain source-backed facts.

Common App creates term controls after scale/schedule selection and initially adds
two blank course rows. A dedicated observer recognizes public labels, visible DOM
owners and precise input identities. Stages establish headers/counts/N/A before a
fresh whole-page field plan. Each action has an observed postcondition. Restart
fills only missing source-backed data; conflicting existing records stop before
Add/header input. Only entirely blank trailing placeholders may be removed.

Persist one original journal and source fingerprint before input. Resume protects
original nonempty values and unrelated statuses. After reload/reopen, verification
checks every field, attribution, terms and exact summary counts. Never click the
outer completion attestation. Unsaved cancellation must exactly match the original
saved parent/editor; saved interruptions resume the intended update. Actual new-
record QA is excluded until full saved-record rollback is established. Registered
Education schools are a prerequisite; grade 12 remains a distinct unfinished flow.

## ADR-051: PSR school references and public directory identities

School reports reference original PSR school/enrollment IDs and existing canonical
facts. Dates keep original days/scales in the source and render only requested
Month Year components. Missing enrollment dates require supplemental evidence and
student clarification. A single optional school-directory object in the same JSON
stores public CEEB identity/evidence once per PSR school/platform for later targets.
Exact source names, BC/Canada and a complete unique public lookup result are
required. No arbitrary first result, fuzzy school guess or special manual option
is selected automatically. Existing conflicting cards stop before replacement.

Current/other school pages use a separate observer and staged lifecycle: establish
count/school/conditional controls, then reobserve and prepare the whole-page fill.
One journal preserves original fields, selected cards, statement formats, source
fingerprint and navigation states. Saved revisits verify all of them. Saved
interruptions resume intended data; unsaved cancellation verifies the old saved
draft. Real QA excludes record/count/shape changes until rollback is established.
Public checkbox owners/values/selectors remain stable while generated group names
change after navigation. Only those transient names are excluded from structure.

## ADR-052: A narrow user-authorized factual school-text exception

The product manager explicitly authorized collecting, reusing and polishing
student-provided school transfer/progression explanations. Only the two observed
Common App questions are allowlisted, with exact public owners and canonical fact
references. No invented reasons, subjective answers or general essays are covered.
Student-supplied text retains its provenance; the Python core formats whitespace
and verifies sources/limits rather than generating personal claims.

CKEditor can expose stale required-invalid state immediately after loading a
nonempty valid statement. The host uses the public Tab/blur behavior and observes
the website's resulting validation; it never overrides invalid flags. Value,
format and structure changes stop. Navigation loading is checked against the
checkpoint at final verification. Only plain-paragraph originals qualify for
the implemented real test restoration; rich formatting requires another method.
An actual installed-port run found that a contenteditable fill can retain old
CKEditor model text and append the new value. Whole-page verification blocked
Save. The scoped writer now uses public Windows select-all/Backspace, verifies an
empty editor, then inserts and blurs. Failed deletion stops before insertion;
saved full text/format checks and original restoration still apply.
The read-only academic parent observer similarly normalizes only generated
ID/name/selector identity for its single exact outer reporting checkbox. Unknown
labels or additional controls are rejected; all semantic flags remain hashed and
the outer attestation is never entered. This allows normal Education-to-Grades
navigation without treating a regenerated checkbox ID as changed applicant data.

## ADR-053: Derived coordination reuses canonical page transactions

The connected academic subset compiles source-reference school/grade reports into
one read-only agenda. It deduplicates personal questions and shared physical Common
App pages across selected universities. A report/configuration gap is agent
implementation work, not a student's missing fact. Actual observed same-origin
navigation evidence bounds its steps; school/course dependencies and directory
names must agree before execution. It neither discovers official university routes
nor expands the supported page set by assuming a familiar platform.

The host coordinator delegates every input/Save to the existing staged ports and
CLI. It adds no persisted profile object: original journals, fingerprints and saved
verification remain in the existing checkpoints. An active transaction resumes
first; earlier jobs are independently rechecked afterward. Sources are revalidated
between pages. The initial current page is never discarded to start navigation.
After verified close, the next route is drawn from the witnessed set. A local
progress callback is synchronous and sends no external messages.

Already matching pages use an independent saved-draft working tab, then the same
core verifier, with no repeat input/Save. Failure retains the journal and cannot
become a completion receipt. Grade editors close only after verification and a
matching saved parent; the outer declaration stays manual. Real new-record QA is
excluded until rollback exists. Results explicitly report only provided supported
pages and never full-application completion. The initial connected fixture links
Education's actual saved school registry to the course school dropdown, so a
prepopulated fake option cannot conceal a missing school-creation dependency.

## ADR-054: Current studies reference originals; official marks remain a separate fact

A reusable current-study report references PSR records and separately confirmed
enrollment, subject, level and term facts. Its scope is the current/most recent
original school year. Missing grades cannot establish enrollment, course status,
term placement or the answer to the separate official-grade-12 question. Clear
name-only original references do not require unrelated missing-result reviews.
Single records retain PSR names; a multi-record display group requires an explicit
student statement scoped to all records, a display label and matching grouping
list. Raw rows, credits, percentages, symbols and evidence remain independent.

The current-year port has its own bounded public contract and transaction family.
It stages observed count/scheduling changes only when existing course values are
empty, then prepares every visible row. Fresh single-select options and exact
multi-select input/popup/chip ownership precede writing. Selected chips can have
different whitespace presentation; only whitespace within the observed labels is
normalized. Other owner text is rejected. The required empty search input is not
the multi-select's value: semantic validity comes from the explicit public invalid
flags and nonempty selected chips for this recognized widget. A site invalid flag
still blocks Save. Generic textarea filling remains restricted, and the generic
writer now rejects every unrecognized control type.

One journal in the canonical JSON survives count/field stages and restart. Final
saved verification covers values, semantic selected sets, shape and all captured
navigation statuses. Intended count/source mismatches stop before destructive
rewrites of populated rows. Real QA supports only valid existing shape/scheduling;
it restores all original values and statuses. Blank/count-change actual rollback
and connecting this port into the joined school/grade runner remain unfinished.
The separate factual grade-12 No port requires an explicit boolean false; Yes or
additional official-grade controls stop rather than risk deleting their records.

## ADR-055: Semantic form proposals reuse the existing transaction core

The agent reads a fresh native form and proposes exact question-to-source
bindings. This is a runtime decision of the current conversational agent, not a
new model API/client or a site label dictionary. A complete proposal accounts for
every observed field as factual/manual/unsupported/optional-skipped; it includes
the exact observation digest and actual label/group/control evidence. The program
validates sources, original academic column purposes, exact options, permitted
lossless formatting and excluded actions. It cannot prove semantic equivalence
from a model's assertion; the agent must resolve actual meaning before proposing
a binding. Missing/conflicting facts remain questions, capability gaps remain
implementation work, and current website answers never become canonical facts.

One shared semantic adapter enters the existing page planner, source gates,
rollback journal and saved verifier. Optional `application_site` metadata binds a
selected target to its explicitly authorized origin/entry URL. Unregistered sites
use `system:web`. The host checks target-bound authorization independently; a
proposal or page cannot authorize an origin. Generic real-account QA flags are
excluded until full site-state restoration exists. No existing real portal is
silently migrated away from its verified specialized port.

Native fields and exact option meanings have semantic identities independent of
render-generated IDs/names/option codes. Actual live selectors/native values are
still captured in full observations and checked before input. Saved comparisons
strip only these transient identifiers; labels, group, required state, control,
options, selector multiplicity, form destination and non-control instructions
remain part of structure. Ambiguous semantic identities stop. Empty forms, record
buttons and unsupported widgets cannot produce an empty success plan. PSR names
and marks/credits must share their original record/group; marks are never converted.

The generic writer reobserves after each input. Added conditional fields pause
before further input or Save and can extend the same journal with fresh analysis.
Existing meanings, bindings, instructions and source facts remain protected.
The atomic store admits only append-only student answers for explicitly recorded
missing conditional IDs, with associated new statement sources/events. It still
rejects changing known facts, evidence, targets, other records or the journal.
This fixes the previous global edit lock's inability to collect a newly revealed
answer during an active form transaction without weakening its original guards.

Saved interruptions resume through the existing checkpoint. Unsaved cancellation
reloads and verifies original semantic values/validity/shape. Already matching
forms require an independent saved read and source-ready zero-write plans;
verification neither saves the current page nor discards its unsaved work.
Initial evidence is two fictional native forms; custom/complex record controls,
conditional removals/redefinitions, whole-site statuses and generic saved rollback
still require separate capability/recovery work.

## ADR-056: Journal explicit branches and verify visible composite state

Generic branch discovery is a separate sourced, one-controller transaction stage.
It may replace inapplicable questions but cannot Save or pass saved verification.
Whole-page acceptance preserves the original journal and source hashes, validates
the selected controller meaning and scope/destination, then collects missing facts
under the existing append-only store rule. Restart preserves this same original.
Unsaved cancellation clears the stage only after exact original-state comparison.

Native-backed ARIA comboboxes use public ownership, actual enabled native options,
visible popup labels and fresh accessibility option IDs. A selected native value
alone is insufficient: the displayed text must agree. Narrow readonly calendars
use public date metadata and observed year/month/day controls. No DOM mutation,
private framework state, keyboard guessing or fixed website field IDs are used.
Semantic identities use visible layout witnesses when identical labels/options
appear in different sections, and retain that evidence when one branch disappears.

Readonly answers and explicit address-policy refs remain source-gated. Telephone
display splitting is restricted to explicit supported country-code formats;
academic values remain unconverted. A unique stationary Save is preferred over
an additional Save-and-Next. Visible validation prevents reload; asynchronous next
actions wait for the observed form to hide. Same-URL section navigation still
requires public-UI return or an independent saved read for the intended section.

Evidence is a fictional composite/calendar branch in Edge plus actual intended
HKU personal-draft filling and independent verification of 28 controls. The actual
final save used documented UI; automated Save-and-Next and generic saved rollback
remain unverified on that portal. HKU academic record creation, full-site routing
and source completeness remain separate work. No HKU adapter is introduced.

## ADR-057: Reference one canonical record in a public modal

A generic semantic proposal can select a bounded path inside an existing
canonical fact. A separate record descriptor identifies the object being edited;
all same-root fields must stay within that object. Original PSR school names,
complete enrollment dates and grade contexts use read-only metadata references.
The resolver formats complete original dates without generating missing precision
or storing another academic record. Raw PSR bytes, scales and rows remain frozen.

Checkpoint identity adds an optional record-instance key, so identical dialogs
at the same URL cannot overwrite one another. Prepare explicitly reuses its own
analysis, and resume/restart reject a different record descriptor. Existing
platform/nonrecord checkpoint identities remain compatible.

The observer scopes exactly one named public ARIA dialog containing one visible
native form. Save validates the entire editor, waits for closure and returns only
a draft-save receipt. An independent reopen of the exact saved record and the
shared verifier are mandatory before clearing the journal. Reload-based modal
verification/cancellation is refused. Background forms are preserved. The dialog
capability does not implement generic record-list navigation, row identification,
saved deletion/rollback or whole-site completion.

Duplicate displayed native choices are explicitly ambiguous and disabled rather
than silently merged. Date placeholders distinguish From/To controls with the same
visible label. Native event reaffirmation is an explicit sourced branch operation
for an already matching owned select; it checks the observed native handler and
uses documented selectOption. No framework invocation, network request or DOM
mutation is introduced. It has synthetic Edge evidence only.

New student facts can arrive before a website asks for them. An explicit intake
flag allows only newly named student-reported facts and associated statements
during one generic transaction. Existing facts/sources, original journals and all
other applicant data remain frozen inside the atomic store lock. The default
still admits only recorded pending answers. Intake cannot turn curriculum study
into an exam result or document-verified qualification. CLI restart and rejected
mixed edits have regression coverage.

Actual HKU inspection reached the blank previous-study editor. The session then
expired: an independent application read showed login while the old editor
remained visible. Preserve the original journal and require fresh authenticated
access before continuing. No actual school record was saved. Two independently
saved/reopened fictional institution records establish the current modal/restart
evidence; actual record creation remains unverified.


## ADR-058: Source-current child receipts witness parent record summaries

A parent form may include immutable summary rows with Action controls. Observe
all cells and headers, derive a unique public selector and reject editable or
ambiguous tables. Each row references one same-target canonical child checkpoint
and its exact rendered identity. Source fingerprints cover original academic
content, referenced facts/evidence and the shared verified school directory.
Every row must be accounted for; duplicate identities require a future stronger
identity capability. The parent writer never invokes row actions or Add controls.
Directory metadata resolves the existing shared entry instead of copying schools.

Native text/number counts are explicit bounded integers. Ordinary typing and Tab
emit website keyboard/change/blur events; no framework code is invoked. Same-shape
conditional value changes pause the branch, retaining one original journal until
whole-page source readiness. Computed display labels outside observed fields are
not included in saved verification.

## ADR-059: Explicit applicant opt-out records saved drafts without verification

Independent readback remains default. A student-statement-backed false workflow
fact enables generic intended-draft continuation; document text and conflicts
cannot. Prefer a unique observed draft Save-and-Next action. The host checks the
whole prepared page, clicks once, waits for ordinary website validation/navigation
and returns a receipt bound to target, URL, action, structure and expected values.
No independent reopen occurs. The core rechecks sources and records
saved_unverified_user_skipped with verified:false. The retained journal is history,
not an active transaction or automatic rollback capability. Saved child receipts
may witness parent identities only while this explicit policy and sources remain
current. They never acquire verified-source evidence. Unknown Save completion
keeps its active journal and never triggers a blind retry. QA/restoration and
legacy platform contracts retain independent verification requirements.


## ADR-060: Explicit draft-record creation and precision-preserving date parts

An observed exact Add button may commit one named native-form record dialog only
with explicit add_draft semantics, a canonical record descriptor and whole-form
source readiness. The host accepts it only in the non-reloading draft receipt
path, waits for closure/errors and preserves ambiguous transactions without retry.
Other Add captions, row operations and final actions remain unsupported. This is
an intended draft operation, not destructive recovery or a full list coordinator.
Date year/month projections accept explicit ISO year-month/full dates and retain
the original source; no missing day or academic conversion is synthesized. Course
completion, result-release and graduation dates remain different facts.


## ADR-061: Source-backed course metadata, calculations and exam identities

Course descriptors reference original PSR records. Explicit course codes/titles
supply levels; result dates require the applicant's separate policy. Future dates
also require the existing current-course report and enrollment references. A
calendar is a staged controller; disabled Pending outputs must exactly match
those sources. Hidden label stars do not establish visible requiredness.

An explicitly permitted arithmetic mean includes every recorded percentage in
one PSR context and rounds half-up to two decimals. Missing marks, unresolved
reviews, absent permissions or unknown scales cannot be dropped or converted.
It is derived metadata, never a rewritten raw grade or claimed official GPA.
An alternative explicit policy ranks the five highest original percentages by
course-title level 11/12 across academic years. Blank undated current courses are
excluded, incomplete achieved marks still block, and five reviewed results are
required. Selected and eligible record IDs remain available as derived evidence;
no per-school grade copies or calculated GPA facts are stored. Applicant-specific
selection does not establish a university's required averaging formula.
Catalogue aliases retain the original name, separately sourced level and record
identity; the conversational agent must establish equivalent meaning. Ambiguous
or unavailable subjects remain gaps rather than substituted records.

Canonical exam metadata reads existing score/date facts and their scales. Shared
session dates use references instead of copied date facts. An optional editor
view must equal the public dialog name and distinguish multiple editors for one
record; restart cannot silently switch it. Reported absence of school predictions
is a source-data blocker, not an invitation to keep asking or estimate scores.

## ADR-062: Discarded drafts with one inactive checkbox flag

Fresh cancellation normally requires all original values and structure. A narrow
fallback permits only one optional unchecked checkbox changing from enabled to
disabled, with matching values, invalid state, instructions and every other
structure byte. It retains the original journal, marks canceled_ui_drift inactive
and returns restored:false/draft_discarded:true. This is an intended unsaved-draft
cancellation, not saved-account rollback or an exact-restoration claim.

## ADR-063: One same-form transaction across selected qualification views

Public selected-tab names distinguish accordion views. A parent date stage may
declare a bounded set of canonical exam/component children and freeze all their
sources before any child input. One authorized child transaction may coexist with
that parent; completion never clears the parent's journal. Same-form view handover
requires the prior intended values and all sources to match, preserves view history
and retains one active checkpoint. It is available only with explicit no-readback
continuation; it does not promise exact saved-account restoration across history.

Masked derived percentages require documented paste/blur events even for a matching
visible value. No hidden input or framework-state write is allowed. After an
ambiguous navigation wait, a read-only receipt recovery can use the observed new
form and bound success notice; another Save is never used to guess completion.

## ADR-064: Exam release schedules, subscores and qualification grouping

AP exam release dates use observed official College Board evidence rather than
school credit dates. Public schedules are content-addressed sources, separate from
student permission to use them and from evidence of an individual's actual score.
An official search excerpt remains labelled as such when the current page has
rolled over to a new cycle. Match administration years and reject stale PSR-date
policies. Do not hardcode the 2026 calendar as a universal rule.

An AB subscore is a source-backed component of Calculus BC, independent of its main
score. It creates neither another examination nor another course. Student grade at
the exam and original course level are different dimensions. Reporting scope comes
from the destination's actual instructions; the canonical academic data stays full.
Related school results share one qualification even when their per-course dates
differ. Actual free-text group creation and a research-based programme selection
remain agent-operated browser work with separate provenance, not generalized core
automation or a student factual answer. No new subjective-answer permission is
granted to the general factual engine.

## ADR-065: Current-cycle official guides precede form work

The skill requires the agent to locate and read each intended university/system's
official guide for the relevant admission cycle before dependent form work. Check
the cycle inside the document, retain URL/publisher/reviewed sections once in the
canonical JSON, and hash one cached file if needed. Targets sharing the guide
reference that source. The source-file integrity check also checks a cached guide;
guide availability is a skill prerequisite, not a new low-level browser-port gate.
Unavailable current-cycle guidance blocks dependent filling, not independent work.

Reporting scope reconciles the guide, actual dropdown options and explicit student
choices. A Grade 12 hint cannot hide observed Grade 10/11 options. A later student
choice to omit Grade 9 applies to that applicant and does not change the complete
PSR. Shared qualifications combine original schools where the destination permits;
school provenance stays on original records rather than duplicated grade copies.
Different examination systems or grading scales retain distinct representations.
