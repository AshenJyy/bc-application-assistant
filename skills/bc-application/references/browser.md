# Observed page workflow

The skill orchestrates documented host tools; this package has no MCP server or
independent browser driver. Use the connected Chrome/Edge extension tab selected
by the applicant. Load `scripts/host_browser.mjs` as a local ES module in the host
JavaScript tool, passing that existing tab object. Its functions call only the
advertised `tab.playwright` locators/read-only DOM evaluate, `url`, `goto` and
`reload`. If those APIs or module loading are absent, stop and explain the runtime
limit. Do not substitute private browser endpoints, CDP, cookie extraction or
DOM-mutating evaluate. Consult actual session documentation before any calls.

1. Run `observe(tab)` for the current page. Required signals include observed
   required/aria-required, labels and university question rules. Unknown native
   requirements need applicant information and explicit fact binding. Unknown
   widgets/iframes and subjective controls block. Never infer UC subject areas,
   course honors level, converted grades, residency or school/program choices.
2. Pass `{page, optional_keys}` to `scripts/run.py page-plan --profile <same.json>
   --target <student-selected-target-id>` through stdin. Private stdout returns
   the plan. Inspect blockers and explain recommendations; optional fields need
   an explicit applicant choice. Page questions/validation are the requirement
   evidence; recommendations distinguish official advice from assistant reasoning.
3. Refresh the observation. Pass `{page, context}` to `page-prepare --profile
   <same.json> --checkpoint <id>`. Context comes from actual host inspection:
   `browser_family` chrome/edge, `transport` extension, current `origin`, and
   `access_verified: true`. Request/recheck missing permissions through the host.
   The core does not grant permissions. Synthetic localhost test authorization
   is restricted to port 8765 and is never a production origin exemption.
4. Preparation saves the original page values into that JSON's
   checkpoint. Do not keep a second profile/observation/plan file for real users.
   Verify the persisted checkpoint, then use `applyWrites(tab, plan, context)`
   with `journal_persisted: true`. It rechecks the page fingerprint before writing.
   All factual writes are a single page batch; unexpected new controls or changes
   to other field values stop before
   a draft save. Collect their answers/replan after recovery, not by guessing.
5. `saveAndRead(tab, plan, context)` first checks the full expected value hash and
   clicks only the observed draft-save action,
   then reloads/revisits the original page. Pass its `{page,
   revisited_after_save}` result to `page-verify --profile <same.json> --checkpoint
   <id>`. All values/control structure must match, including untouched fields.
   Errors remain `needs_restore`; don't report success or continue to a new page.
6. For recovery, `page-restore` takes the latest page through stdin and returns
   rollback writes from the same JSON. `restore(tab, plan, writes, context)`
   performs those writes/save/revisit; `page-verify --restoration` checks the full
   original value fingerprint before clearing the journal. Structural drift or
   restoration failure requires a manual handoff; preserve the checkpoint.

Real-account tests require `real_account_test: true` and an established way to
restore **all state**, including completion/status flags. Set
`full_state_restoration_verified` only with evidence, never as a convenience.
The implemented strategy is `restore_completed_native_page` for an already-complete
Common App factual native page. The context must match the observed current-page
key and original state hash; store the original statuses in the same checkpoint.
Only after all original values AND captured visible statuses match may recovery
be cleared. After revisiting, wait for native fields and each captured accessible
status component: Common App hydrates navigation separately. This strategy has
passed a real Personal Information test; it does not establish MIT/UC recovery.
Common App Personal Information radio identities use the stable question IDs in
the observed native option IDs. Only its generated Material group name is omitted
from saved structure comparison; option IDs, labels, values, order and selector
counts remain checked. The complete fresh observation, including the group name,
must still match before any write. A real test starting after in-page navigation
passed even when the group names regenerated during the save/revisit cycle.
Normal applicant
draft filling and reversible developer testing are different task purposes.
No automatic essay entry/submission, declarations, invitations, signing or payments.

Supported controls: unambiguous native text/email/tel/number/date, single select,
radio, factual checkbox, and recognized factual name/address textareas. Unknown
narrative textareas remain manual, except the two observed optional MIT coursework
notes may remain exactly empty and untouched. Existing/required/unknown narratives
and consent/attestation fields block saving in both the core and host bridge.
An optional label combined with a required signal is a website conflict, not a
request to invent an answer. Report `conflicting_required_signals` and stop the
page. MIT's editable record-summary tables carry headers/counts without applicant
row data; `repeatable_record_editors_not_supported` prevents an empty school/test
summary or partially observed coursework page from being treated as complete.
MIT nested record editors and new Common App course/transcript records are not
implemented. The existing Common App course-dialog exception is described below.
The exact empty MIT U.S.-only Classes table has a separate fact-gated exception
through the coursework port below; this is not a general collection bypass.
For a UC field with an incorrect label association, use its observed `.field-wrapper`
only when it contains one label and one visible control. Keep native option-group
labels so duplicate category names cannot silently choose a classification.
Hidden/inert controls do not count as active visible fields.
Known optional unsupported controls may remain
untouched but cannot be selected for automatic filling. Known UC Personal information names have mappings;
additional factual fields use target bindings to shared fact IDs. Original grade
columns use `bind_record_column`, not a copied/converted grade. Exact observed
option labels/values must match; unmatched grading scales stop. MIT uses visible
question labels/address headers, not question UUIDs. Common App uses its common-section
route and observed section-specific Continue action; arbitrary Continue buttons
are forbidden. No full UC/MIT/Common App coverage claim is made. Common App college
supplements and Writing remain excluded. See [university support](universities.md).

`inspectOptions(tab, field_key)` can inspect a closed observed Material single-select
through its labeled ARIA listbox, then close it with Escape and check that the
complete observation is unchanged. It returns labels/selected/disabled states,
not private component values. Inspection does not enable custom-control filling;
required custom widgets outside the scoped grade port still stop a filling plan.

## MIT factual STEM coursework

Load `mit_coursework.mjs` and inject the existing `host_browser.mjs` exports into
`createMitCoursework(hostBridge)`. This port handles only the observed current
Self-reported coursework form, with eight native STEM selectors, two untouched
empty notes and the one empty Classes table. It does not create/edit class rows.

1. `observe(tab)` reads the complete form, follows its public Review and Home links
   to collect review errors/warnings and the unique unsubmitted First-Year In Progress
   draft, returns to the original URL, and proves read-only inspection preserved
   the whole form. **Never call this on unsaved edits.** It fails on an ambiguous
   application, changed status tables, populated Classes table or other controls.
2. Subject/year associations come from adjacent public question containers and their
   visible labels/options, not UUIDs or assumed select ordering. Require explicit
   `education.subjects.<subject>.status` and `.year`. Year accepts `9th`–`12th` or
   explicitly `not_listed_or_not_taken`; unknown values do not become blank answers.
   A will-not-take status conflicts with a supplied 9th–12th year. Only confirmed
   Canada and non-U.S.-system facts permit leaving the exact empty Classes table.
3. Plan/prepare with the same CLI and optional `reaffirm_keys` for native selects.
   These still require source-backed values and exact observed enabled options.
   Use real-test strategy `restore_mit_coursework`, `page_url` and
   `baseline_state_sha256: digest(page.state_metadata)` only after checking the
   actual complete STEM state and recovery path. Existing coursework review errors
   block the real-test strategy. Persist the journal before input.
4. `apply(tab,plan,context)` observes fresh status before input, writes the native
   factual batch and returns a **local** full observation. Pass that local result to
   `saveAndRead(tab,plan,context,local)`, which checks all values and activates only
   the unique Save and Continue draft button with Enter. It revisits and freshly
   rereads both form and visible review/portal state. Send the result to `page-verify`.
5. `page-restore` returns its persisted plan/context after a restart. Pass its writes
   to `restore(tab,plan,writes,context)` and then `page-verify --restoration`.
   Zero changed values need no extra save; they still require fresh saved-page and
   full original status comparison before clearing recovery. Any mismatch retains
   the journal. Do not fill narrative notes, correct unrelated review errors, or
   press any submission, invitation, declaration or payment action.

The actual eight-answer same-value test passed with ten values, four errors,
two warnings and In Progress state unchanged. This is not a changed-value MIT
recovery test. The simulated changed-value recovery test is recorded separately.

## UC factual Personal information

Load `uc_personal.mjs` and call `createUcPersonal(hostBridge)`. Current scope is
the twelve observed native controls on `/my-application/accountPersonal`, with
explicit No answers to lived name, any former legal name and California public
school attendance. Other conditional configurations, unknown controls or narratives
require a separate scope and are rejected before input.

1. `observe(tab)` follows the actual Review & submit link, expands the review and
   captures seven section completion markers and every child Edit/To do route.
   It reads the unique Fall 2027 Open application marker on Application status,
   reopens that actual term link, then uses Edit Personal information to return.
   Direct form navigation after appStatus was observed to return to appStatus.
   The whole form must match after this read-only inspection. Do not call it on
   unsaved changes. No essays, declaration answers or review values are collected.
2. Supply all factual requirements through the shared profile. No old-name materials
   does not establish that a student never had another legal name. The portal's
   `China, Peoples Republic of` label is a lossless display alias for an explicit
   canonical `China`; it does not change the canonical country. Exact other options
   still apply. No fuzzy matching or nationality inference is permitted.
3. Country selection was observed to clear City even when selecting the same country.
   A prepared whole-page plan therefore appends the already-resolved city after Country
   and the explicit Day after date parents. Missing child facts block the plan;
   a current website value cannot supply evidence. Native reaffirmations are same-value
   tests, not changed-value recovery evidence.
4. For real tests use `restore_uc_personal`, `page_url` and
   `baseline_state_sha256: digest(page.state_metadata)`. Require the current review
   action be Edit Personal information and About you already complete. Persist the
   canonical checkpoint first. `apply(tab,plan,context)` returns a local full-page
   observation; pass it to `saveAndRead(tab,plan,context,local)`. Only the observed
   Save & continue is activated, with documented navigation waiting and a fresh
   saved-page/status revisit. Send the result to `page-verify`.
5. `page-restore` returns persisted plan/context, original metadata/hash and needed
   writes. For saved-state recovery call `restore(tab,plan,writes,context)`.
   If input was stopped **before saving**, repair the local original fields before
   any navigation: call `restore(...,{unsaved:true,original_state_metadata,
   original_values_sha256})` with the canonical bundle. It proves all local values
   match, then revisits saved form/status without a draft save. Both paths require
   `page-verify --restoration`; any mismatch retains the original journal.

The real test reselected four native originals and reapplied the known city,
saved/revisited and verified twelve values, seven sections, 32 child statuses and
the open draft marker. All original values/statuses matched; real changed-value UC
recovery remains unverified. An earlier country reset was stopped before saving and
restored from the journal before saved revisit.

## Existing Common App grade editor

Load `grade_editor.mjs` as a separate local ES module, then call
`createGradeEditor(hostBridge)` with the already loaded `host_browser.mjs` exports.
Dependency injection avoids any host-specific nested-module loading assumption.
The real verified scope is existing 9th–11th Grade editors, with Other/proficiency
and percentage scales and semester/yearly schedules. Other configurations require their
own validation before a real test. Never add/remove courses/transcripts or change
school/year/scale/schedule headers with this port.

1. From the closed current grade page, call `captureParent(tab)`. It captures
   the visible course summary, original reporting checkbox and navigation statuses.
   Require the page already complete and its reporting checkbox already checked
   for developer tests. Missing/unfinished status loading is a stop, not an assumed
   complete state. `openGradeEditor(tab,parent)` opens only the observed Edit action.
2. `observeGradeEditor(tab,parent)` includes only that actual modal's fields and
   its known draft-save, excluding the parent reporting attestation/Continue.
   Term requirements are per course: one applicable grade and credit (or the
   observed Credits not applicable choice). Empty unused periods stay empty;
   nonempty fields require evidence. Subject, level, school year, term placement
   and N/A are explicit student choices, never derived from grades or course names.
   Bind rows/headers using the actual `page_path` (for example `/common/13/55`).
   The same IDs represent different courses in another grade. Global legacy
   bindings are rejected on grade routes; `scope_bindings` explicitly moves
   verified references to one observed page without duplicating facts.
   Original PSR columns remain raw; PDF course-name wrapping is removed only for
   the one-line display. See [Common App's academic record guide, page 8](https://www.commonapp.org/files/webinar_decks/Academic-Record-Reporting.pdf).
3. Before writing a Material field, use `inspectGradeOptions(tab,parent,key)`.
   It reads public option labels/disabled states, sends Escape to the actual open
   listbox and waits for it to close. Refocusing the underlying combobox before
   Escape was observed to close the parent; clicking the modal heading did not
   consistently dismiss the list on another grade page. Keep focus in the listbox.
   Re-observe with the
   returned map as `choice_observations`. Every actual selection reopens and checks
   the exact current list before clicking its observed matching option. Blank
   Material clearing remains handoff-only; never treat "Clear selection" as a grade.
4. Plan and prepare via the same CLI. `{page, optional_keys, reaffirm_keys}` may
   explicitly select a known nonempty Material value again; reaffirmation still
   needs its source and observed options. It must not be described as a changed
   grade. Header changes and filling an initially blank Material control are blocked.
   For real tests use `restoration_strategy.kind: restore_completed_grade_dialog`,
   `current_page_key`, `baseline_state_sha256: digest(parent.state_metadata)` and
   `baseline_parent_sha256: digest(parent)`. Set restoration permission only after
   checking actual completed state, the reversible writes, and recoverability.
5. The same canonical checkpoint persists all original values, the parent,
   preparation plan and observed choices before the first write. Call
   `applyGradeWrites` then `saveGradeAndRead`. Only the dialog's observed
   Continue/Closes dialog is a draft-save. It closes the modal, reloads the parent,
   waits for statuses, captures that fresh parent and reopens the editor. Send its
   result to `page-verify`; full original parent/status state must also match.
6. `page-restore` returns original-value writes and, for a prepared grade dialog,
   its persisted `plan` and `context`. These support recovery after restarting
   the host process. Use `restoreGrade(tab,plan,writes,context)` and
   `page-verify --restoration`; clear temporary recovery data only after all
   original values, parent summary/checkbox and captured statuses match. Leave
   the journal intact on any mismatch. Never recheck an attestation as recovery.

   Activate the uniquely observed modal draft button with Enter on long grids.
   Successful option selection closes its own overlay: wait for removal without
   sending Escape afterward. Re-observe an apparently timed-out closure once;
   proceed only when the public UI shows it closed. A remaining dialog/listbox
   stops the workflow with its journal intact, without another automatic save.

Real tests changed eight/one/two PSR-backed course names in 9th/10th/11th Grade.
Percentage dropdowns reselected the same original scores in 9th/10th. Saved readback
and restoration passed for 98/94/138 values and 13 navigation statuses per page,
with each full parent baseline unchanged. No score changed; changed-score
restoration, remaining grade pages and new records remain unverified.

All JSON pipe input/output uses UTF-8 explicitly, including on Windows locales
with a legacy default encoding. Send UTF-8 bytes and decode the stdout stream as
UTF-8; no second observation or operation file is needed.

Repeated native element IDs use the observed selector match count and index in
each field's identity. Accessible labels take precedence over ambiguous repeated
HTML label associations. Before filling, the host checks the match count again
and addresses the observed position through the documented locator API. These
positions are observation-specific; never reuse them after the page changes.
This resolves native control ambiguity, not custom dropdown support. Completion
checkboxes such as reporting all courses are attestations and remain manual.


## Existing UC course editors

Use `createUcCourses(host)` from `scripts/uc_courses.mjs`. This port handles an
existing native school/year course editor, not school configuration or new rows.
Start at the actual grade summary, call `open(tab)`, then `observe(tab)` on a saved
baseline. Observation cancels/reopens the editor and visits Additional information
and the review/draft pages; never use it to inspect unsaved edits.

Require `page_path` bindings for every observed row/control; global course-row
bindings cannot be reused. Bind names/marks directly to raw PSR columns. Retained
subject/honor/scale/NO placement needs explicit student confirmation. No annual
mark is duplicated into semesters. Record `education.uc_ap_reporting_term` as
`Full year` only when the student says so; existing Semester AP rows then block
until a supported school-and-course reconfiguration workflow exists.

Preflight must find exactly one empty optional comments textarea and its known
plain draft-save on UC Academic history Additional information. Its structure and
empty-value hashes travel with the same canonical checkpoint. Any existing text,
required/new field or changed action stops before the first course write. The
port never fills this textarea. After course saves, its unchanged empty draft-save
repairs UC's observed completion invalidation; full review/draft comparison remains
mandatory. This exception is confined to this port and preflighted shape.

Use `restore_uc_courses` as the real-test strategy with the actual editor URL,
`baseline_state_sha256: digest(page.state_metadata)` and
`baseline_parent_sha256: digest(page.uc_course_parent)`. Require completed academic
and additional-information states. Persist `page-prepare` first, then call
`apply(tab,plan,context)` and pass its local observation to
`saveAndRead(tab,plan,context,local)`. Verify through `page-verify` after revisit.
Course native Save/Cancel buttons use clicks with explicit navigation waits.

Use `page-restore` to retrieve the persisted plan/context/writes and call
`restore(tab,plan,writes,context)`. Verify original values, summary and all states
with `page-verify --restoration` before clearing recovery. An interrupted connection
needs a fresh tab observation and recovery bundle, not another blind input/save.
For known unsaved changes use the documented port's `unsaved:true` option plus the
bundle's original state metadata/value hash; it repairs originals before leaving.
A dialog or changed structure stops recovery and keeps the journal for resumption.

## UC Full/Semester course refill

When the school already offers both terms, use `createUcCourseRefill(host)` from
`scripts/uc_course_refill.mjs`. This is separate from school availability changes.
Never change a school's term settings through the ordinary course port: UC warns
that doing so resets existing course terms and grades. `uc_term_setup.mjs` only
preflights that form and declines the reset warning; it cannot accept it.

Start on the saved course summary, call `open(tab)` then `observe(tab)`. Observation
captures every existing native field, full saved summary cells, the exactly empty
optional comments baseline, and all visible review/draft states. It cancels and
reopens saved editors; never run it on unsaved edits. The supported selectors are
the actual Full (`F`) / Semester (`S`) options. Full exposes G1 only; Semester
exposes G1/G2. The summary says Full; the internal reporting label is Full year.

Bind every row's observed subject/honors/language/scale and term to explicit
page-scoped student facts. Bind its name and completed grades to the same original
PSR record. Only explicit NO/IP/PL status facts may replace a PSR-grade reference.
Do not infer the off-term from dates. Require the student's AP Full year choice and
retention confirmation; preserve existing names and classifications during refill.

1. `uc-refill-prepare --profile ... --target ...` reads `{bundle,context,reaffirm_term_keys?}` from
   stdin. It checks all sources and future grade references before any term input,
   then persists the complete original in the same canonical JSON. A real test uses
   `restore_uc_course_refill`, complete originals, `page_url`, `baseline_state_sha256`
   and `baseline_parent_sha256: digest(bundle.summary.parent)`.
2. Add `journal_persisted:true` to the established context. Run
   `applyTerms(tab,plan,context)`. Send its fresh native page to
   `uc-refill-grades --profile ... --checkpoint ...` as `{page}`. This persists the
   second plan only after checking the newly exposed controls, exact current
   options, unchanged retained fields and complete grade bindings. Unknown fields
   stop before a save; cancel unsaved edits or retain the journal for recovery.
3. Run `applyGrades(tab,gradePlan,context,originalBundle)` and
   `saveAndRead(tab,gradePlan,context,originalBundle)`. The entire page is checked
   before Save. Saved summary cells and all native values are checked after reopening.
   For an ordinary incomplete-grade refill, the grade's plain Continue may record
   completion. Only the preflighted empty comments draft is saved unchanged to repair
   completion. No Review attestation or application submission is performed.
4. Pass the returned bundle/revisit flag to `uc-refill-verify`. An ordinary intended
   refill clears its journal only after saved verification. Real tests retain it
   until exact original values, structure, summary and full state are restored.
5. After an interruption, `uc-refill-recover` returns the persisted plan, context,
   original bundle and original term writes without changing the JSON. Use
   `restoreTerms(tab,recovery,{unsaved:true})` to cancel unsaved edits without Save.
   For a saved complete original, call `restoreTerms(tab,recovery)`, then
   `uc-refill-grades --restoration`, `applyGrades`, `saveAndRead` and
   `uc-refill-verify --restoration`. An originally incomplete/reset draft cannot
   be claimed restored by saving blank grades; retain its journal and resume the
   intended source-backed refill instead. Generic `page-verify` cannot clear it.

## UC fixed factual pages and current IELTS

Load `uc_factual.mjs` and call `createUcFactual(host,kind)`. Kinds are
`citizenship_residency`, `background`, `grade78`, `level`, and `ielts`. These
contracts cover only the exact observed public field shape in
`bc_application/data/uc_native_forms.json`; they do not accept arbitrary nested
record editors. `open(tab)` starts from the actual expanded UC review route.
`observe(tab)` navigates away to collect all review/draft states, so call it only
on a saved baseline. A record-specific review href avoids ambiguous repeated
"Edit Reported test" labels.

Use the ordinary `page-plan`, `page-prepare`, `page-verify` and `page-restore`
commands with this port's `apply`, `saveAndRead`, and `restore`. Native Save is
clicked; Enter on the actual IELTS submit button returned without persisting,
and saved readback caught that failure. Require fresh all-field equality after
the actual save, review navigation and reopening. A recovery journal remains on
failure. Ordinary successful requested updates clear temporary old-value data;
real tests retain it until original verification. Test context uses
`restore_uc_factual` with the exact `page_url`, `baseline_state_sha256`,
`review_label` and `section` from the selected contract. The original current page
and its section must be complete before any real test. Compare all original
field values and all review/draft states before clearing the test journal.

IELTS binds only when there is one canonical `IELTS` / `IELTS Academic` record.
Its date/components resolve to that exam's fact IDs, never another editor's
reused native date/score IDs. Optional `i:ieltsFormNumber` requires an explicit
source and selection through `optional_keys`. The full date remains in the
profile, while UC receives only its observed month/year controls. Do not carry
an old report number into new scores. Completed, score received and retaking
answers require facts; a retake plan cannot be inferred from the score.
Creating or deleting exam records is outside this fixed editor contract.

Background only fills the confirmed language controls; unknown optional household
and military answers stay untouched. A citizenship question that literally asks
about the submission date is factual, not authorization to submit. Contact/parent
pages contain actual authorization checkboxes; these block automatic page saves.

## Common App fixed IELTS page

Load `common_ielts.mjs` and use `createCommonIelts(host)`. `inspect(tab)` reads
the actual twelve required fields and opens/closes six associated input listboxes
without selecting options. The shared public JSON contract includes labels, widget
metadata and normalized visible-content hash; unknown controls/notices stop.
The reused `choice_controls.mjs` helper also serves the existing grade port, but
these whole-page INPUT/NG-SELECT menus have a different documented public ARIA
association and Escape target from MAT-SELECT dialogs. Never type arbitrary labels.

Require one canonical IELTS Academic exam with full ISO date, its four components
and overall score, `exams.ielts.highest_scores_confirmed: true`, an explicit integer
`exams.ielts.taken_count` (currently observed 1–5 supported), and explicit
`exams.ielts.retake_planned: false`. Retaining only the newest result does not supply
the count. Existing website answers are not evidence. Other retake/highest-date
configurations need a newly observed contract; do not infer them.

Use `page-plan`, `page-prepare`, `apply`, `saveAndRead`, then `page-verify` with
the returned page/revisit flag. Persist the whole original in the canonical JSON
before input. Save uses the observed Continue draft action, waits for navigation,
reopens IELTS and waits for every captured navigation status to hydrate. Verification
requires all twelve values, valid fields, IELTS Complete, the correctly computed
Testing status and exact equality of unrelated visible navigation statuses. A normal
successful requested update clears its temporary original; no old IELTS attempt is
added to the profile. Actual evidence covers this fixed draft update, not test-record
creation or real changed-value original recovery.

On interruption, `page-restore` returns the persisted plan/context/original writes.
For edits definitely not saved, `restore(tab,recovery,{unsaved:true})` reloads without
saving blanks, then `page-verify --restoration` must match all original values,
invalid-field flags and statuses before clearing recovery. For a saved complete
original, `restore(tab,recovery)` replays exact native choices/dates and saves/revisits;
real-test contexts require the already-complete original native-page strategy.
An incomplete original cannot be replayed as a valid blank save. Keep the journal
and use `common-ielts-resume --profile ... --checkpoint ...` with a fresh `{page}`.
It rechecks sources, expected complete values, shape and unrelated states, refreshes
only the remaining-write plan and preserves the original journal. Reinspect options
after reconnecting; do not reuse an in-memory plan across a browser interruption.

## Shared collection agenda and next supported pages

`collection-agenda --profile ...` reads `{requests:[{target_id,pages,routes},...]}`
from stdin. Supply fresh observations/routes for the selected targets. It combines
required mapped facts across systems into one question per missing/conflicted
canonical fact, with related question groups and the pages that need each answer.
Known facts are omitted from questions. It never promotes website values into facts
or copies answers into its output. Source/academic reviews, manual pages, structural
gaps and other blockers stay separate. Uninspected routes remain explicit. An active
transaction defers inspection and reports its recovery metadata first.

The result is bound to profile revision/hash and observation hashes. Recompute it
after collecting answers or changing browser pages; do not persist a second applicant
profile. Save actual answers through ordinary `profile-update` operations. A supported
source-ready complete page with zero differences is listed under `already_matching_pages`;
skip its Save. Other ready pages still require the normal persisted checkpoint and
browser-permission workflow. The user's existing authorized scope remains in effect;
this report does not create a separate per-page approval step.
Every matching entry sets `saved_revisit_required:true`; the agenda always returns
`execution_verified:false`. Its `complete` flag means supplied requirements are
source-ready, never that all answers persisted. Independently reopen the saved
draft and compare all values/statuses before reporting completion. If the current
page may contain unsaved user edits, use a separate working tab at the observed
URL; do not refresh or discard the user's current page.

For a supported Common App native matching page, use `page-verify-matching
--profile ... --target ...` with `{baseline,page,context,revisited_saved_draft:true}`.
`baseline` is the current observed page; `page` comes from an independently opened
saved draft. Supply fresh choice observations on both. The command requires valid
browser permission, complete matching visible states, identical structure/options/
all values and zero source-backed writes in both plans. It records only a successful
verification receipt in the same canonical checkpoint, with no rollback journal.
Failed matching leaves the profile unchanged and performs no browser action. Do
not use `page-verify` to verify this receipt; a later fill starts a fresh ordinary
plan. Existing scoped grade dialogs and other systems still use their dedicated
verification workflows.

For Common App `Household` and `Language`, load `common_factual.mjs` and call
`createCommonFactual(host,kind)`. `inspect(tab)` discovers fresh options and returns
the tagged observation. Use ordinary `page-plan`, `page-prepare`, `apply`,
`saveAndRead` and `page-verify`, with the same complete-native-page real-test strategy.
The shared `common_page.mjs` lifecycle also serves IELTS. `common-page-resume` accepts
fresh `{page}` after interruption and retains the original while rechecking sources.
The older `common-ielts-resume` remains IELTS-specific. Incomplete original recovery
cancels unsaved edits or resumes the intended factual fill; it never saves invalid
blank originals. A real test must verify every original value and visible status.

Household uses `family.independence_statuses_apply: false`, the existing shared
`family.parents.marital_status`, and `family.permanent_home`. Optional children answers
stay untouched unless explicitly supplied/selected. The independent-status Yes
branch needs separate observation; do not classify eligibility for the student.

Language uses `personal.languages.order` with explicit unique local IDs, and
`personal.languages.<id>.<label|first_language|speak|read|write|spoken_at_home>` facts.
The count is the length of that explicitly supplied list. All five boolean answers
must be explicit for each language; neither blank checkboxes nor an exam establish
ability. Existing visible rows (1–5) must already match the list. The port associates
each picker with its next visible proficiency group through public DOM structure,
then locates checks by the group's legend and observed input value. Generated
checkbox IDs/group names are transient. Unknown controls, labels, pairings or Other
language explanations stop. Reselecting a language can reset abilities: append all
five source-backed flags afterward, and replay all original flags during recovery.

## Staged Common App language row creation

Use `createCommonLanguage(host)` from `common_language.mjs` when the language count
is blank or differs from the explicit ordered language list. The fixed-shape port
still requires matching existing rows. This staged workflow is for an intended
factual draft update, not a real-account changed-count restoration test.

1. Call `inspect(tab)`. An empty language page must expose exactly its known count
   radio group, five observed options and no extra inputs. Every nonempty page must
   have the selected count's actual number of publicly associated language groups.
   Initial empty-page coverage is synthetic; actual first-use layout is unverified.
2. Send `{page}` to `common-language-preview --profile ... --target ...`. This is
   read-only. It checks the PSR, the entire explicit language list and all six facts
   for every requested row, including rows not yet visible. Resolve missing facts,
   conflicts or unsupported Other names before count input. No ability is inferred.
3. Send `{page,context}` to `common-language-prepare` with the same arguments and
   persist its journal in the one canonical profile before input. After it succeeds,
   pass its `plan` and current context plus `journal_persisted:true` to
   `changeCount(tab,plan,context)`. It selects only the exact observed count option,
   waits for the generated controls, inspects fresh choices, and never saves.
4. Send its returned `{page}` to `common-language-rows --profile ... --checkpoint ...`.
   This rechecks all sources and produces/persists a fresh `stage:fields` plan from
   the actual controls. Pass that returned `plan` to `apply` and `saveAndRead`.
   Do not pass a count plan to the whole-page writer or reuse old row selectors.
5. Send the returned `{page,revisited_after_save:true}` to `common-language-verify`
   with the same profile/checkpoint. It verifies every value, shape, fresh options,
   required validity and visible statuses; only success clears temporary originals.

After an interruption, inspect the current page and use `common-language-resume`
with `{page}`. It preserves the original journal and checks all fact/source versions.
The returned stage chooses count selection or a fresh remaining-field plan. A saved
interruption continues the intended update; never attempt to save invalid blank
originals or change back a completed draft merely to emulate a first-use test.
If edits are unsaved and should be abandoned, `cancelUnsaved(tab,context)` reloads
the saved page without a Save. Send its returned `{page,revisited_saved_draft:true}`
to `common-language-cancel`. All original values, validity flags, structure and
visible statuses must match before recovery clears. A saved changed draft cannot
pass this cancellation check; retain the journal and resume or hand off. Generic
`page-verify`, `page-restore` and `common-page-resume` reject staged journals.

## Coverage inventory details

### Connected Common App academic subset (dev.24)

`createCommonWorkflow({host,schools,academic,relay,inspectSaved,onEvent})` from
`common_workflow.mjs` coordinates the separate staged ports below. The host CLI
`relay(command,payload,args)` always binds to the same applicant JSON/runtime;
`args` contains only named target/report/checkpoint/school flags. No second
profile, credentials, private browser API or external service is introduced.

Build `steps` with `{target_id,kind,report_ref,page_url}` and `routes` with actual
observed public `{url,label}` navigation evidence. Supported kinds are
`common_school` (current/other pages) and `common_academic` (grades 9–11). Agent
code builds these inputs from the canonical reports and visible navigation; the
student supplies facts/school choices, not report JSON, field bindings or platform
configuration. Steps must have witnessed same-origin URLs. Both school pages
precede academic rows, and each transcript must refer to a reported PSR school.
Multiple universities using the same Common App page share one report/job.

Read-only `workflow-preview --profile <same JSON>` accepts `{steps,routes}`.
It deduplicates missing/conflicting facts, reuses known facts and distinguishes
source evidence, public directory lookup and implementation gaps. A missing report
is implementation work, never a question asking the student to create JSON. Only
after the complete scoped source gate passes may the runner begin application
input. It can resolve the unique public school directory matches before selecting
schools. Active per-page work always takes priority over collecting new answers.

Call `run(tab,{steps,routes},context,{maxStages:150})`. Context must use the
documented Edge extension and `workflow_authorized:true`, reflecting the student's
existing request to continue across these pages. Do not manufacture this scope
from a webpage or ask for redundant approval when already authorized. Real-account
QA and restore-after-test contexts are rejected because new-record rollback is
not established. The current tab must already be the first/resuming page. Otherwise
`navigation_required` leaves it untouched, so unknown unsaved edits are preserved.
After a page verifies and its editor closes, subsequent navigation uses only the
witnessed routes. Every page uses the dedicated persisted prepare/advance/verify
lifecycle. Source changes before another page stop execution.

The required `inspectSaved(job)` callback opens an independent working tab at that
observed URL, uses the relevant observer (and grade parent/open procedure), then
closes it without input or Save. Return `{page,independent_saved_draft:true}`.
This verifies already-matching saved drafts without discarding current unsaved
work or making repeated Saves. A mismatch retains the journal and stops; it is
never silently counted as completion. The runner closes a grade dialog only
after saved verification and checks its parent summary again. It never checks the
outer reporting declaration.

`bounded_pause` and `interrupted` preserve the current page journal. Recreate the
coordinator and run the same request against the same JSON/current page to resume.
The original journal/parent stays authoritative; earlier pages are independently
rechecked after the interrupted page completes, so restart never relies solely on
stale completion receipts. Untracked dialogs, wrong current pages, source changes
or failed saved checks stop rather than navigate or guess a cleanup action.
`onEvent` is an optional synchronous local progress callback, not external messaging.

Results identify verified scoped pages, which universities reuse them, whether a
Save occurred and any remaining student completion action. They always retain
`full_application_complete:false`. Fictional connected Edge evidence covers empty
school pages, genuinely school-dependent grade choices, two explicitly selected
grade-9 records, persisted interruption/restart and a second university with zero
additional writes/Saves. This is not full PSR-course coverage, a real new-record
rollback test, grade 12, school-to-official-application routing or full portal support.

### Individual school-page procedure

Use `createCommonSchools(host)` from `common_schools.mjs`, with the same documented
Edge extension context, on the observed `/common/4/18` or `/common/4/19` page.
Its separate `observed-school-page/1` contract cannot use the generic page writer.
Only public school lookup owners, exact date/radio/progression controls and two
known factual-statement owners are supported. No hidden Angular/CKEditor state,
private endpoint, arbitrary contenteditable or general essay selector is used.

1. `observe(tab)` reads the current page without opening editors. If CKEditor
   exposes stale invalid status on an existing statement, explicitly use
   `settleValidation(tab)`: it focuses/leaves that known editor through Tab, then
   reobserves the website's validation. It never overrides invalid attributes or
   changes text. Any value/format/structure change stops; real validation errors
   remain blockers. Navigation states are verified by the persisted checkpoint.
2. Before application input, compile the school report via read-only
   `common-school-preview --profile <same JSON> --target <id> --report-ref <fact>`
   with `{page}`. Resolve all factual/evidence gaps first. `lookups_needed` is
   implementation discovery, not a repeated personal-information question.
3. For each uncached PSR school, `lookup(tab,observedQuestionId,PSRName,context)`
   opens its public Find/Change dialog, searches by High School Name, reads the
   complete results and closes without selecting. The parent values/statuses
   must be unchanged. It may search another school using the visible current
   school slot before the other-school count is set. Send `{lookup,context}` to
   `school-lookup-remember --profile <same JSON> --school <original PSR id>`.
   `school-lookup-resolve` is the read-only variant. Incomplete/ambiguous results,
   manual/not-found options and conflicting cached identities stop selection.
4. `common-school-prepare` uses the same preview arguments and `{page,context}`.
   It persists one original journal, source fingerprint, structure and all visible
   statuses. Only then call `applyStep(tab,result.plan,{...context,
   journal_persisted:true})`. Intermediate stages select count, a freshly matched
   school or explicit graduate/progression options. They do not save the page.
5. Reobserve after each stage and call `common-school-advance --profile <same JSON>
   --checkpoint <id>` with `{page}`. It rechecks sources/identities and fills only
   missing intended data. Conflicting existing schools stop before replacement.
   At `stage:fields`, apply all remaining dates/boarding/scoped factual text, then
   `saveAndRead`. This clicks only the observed outer draft Continue, revisits,
   settles the known editor validation and reads the entire saved page.
   For the two known statement editors, Windows select-all/Backspace must expose
   empty text before insertion; a contenteditable fill alone can append to the
   editor's old model text. Failed deletion or whole-page mismatch stops Save.
6. Send the returned `{page,revisited_after_save:true}` to `common-school-verify`
   with profile/checkpoint. All values, school identities, statement format,
   shape, validity and navigation statuses must pass. Success clears temporary
   originals for intended updates; real tests keep them until exact restoration.

`common-school-advance` resumes from a fresh observation after interruption without
overwriting the original journal. For unsaved cancellation, use
`cancelUnsaved(tab,context)` then `common-school-cancel` with its returned
`{page,revisited_saved_draft:true}`. Invalid blank originals must not be saved.
For an existing complete, same-shape real test, `common-school-recover` with
`{page}` returns a restoration plan. Apply/save/read it, then run
`common-school-verify --restoration`. Recovery checks every original value/format
and status. Rich originals, changed record counts/identities and real new-record
rollback have no established restoration path and are excluded from real QA.

The factual-text exception is limited to the observed transfer and school-
progression questions. Ask for absent student facts; reuse authorized existing
details and polish without adding motives, circumstances or achievements. The
contract rejects all other narrative owners. General essays and final actions
remain manual. Synthetic Edge tests cover first-use current/other school creation;
actual evidence covers changed dates/text on existing records and full restoration.

### Common App first-use academic records

Use `createCommonAcademic(host)` from `common_academic.mjs` on observed 9th–11th
grade dialogs. It supports Other (original symbols), 1-100 (original percentages),
Semesters and Yearly. School choices must already exist in Education; use the
dedicated school procedure above first when absent. Grade 12 and other layouts
remain unfinished. Never click the outer
"I have reported all of my courses for this grade" declaration.

Store an `academic-report/1` factual value, e.g. `education.reporting.grade_9`, in
the single profile. It has `grade` and `transcripts`. A transcript has a unique
`key`, original `psr_school_id`, `header_refs` (`school_name`, `school_year`, `grading_scale`, `schedule`) and
`courses`. Each course has original `record_id`, explicit `subject_ref`, `level_ref`,
`credits_na_ref`, `grade_terms`, `credit_terms`. Metadata references are existing
`education.*`/`schedules.*` facts. Terms are `semester_1`, `semester_2`, `final`;
Yearly uses only `final`. Grade references must be `psr:<same record_id>:school_percent`
or `:school_grade_symbol`, consistent with the transcript's original scale. Credits
reference original `:credits` or a separately evidenced fact. N/A means empty credit
terms. Names come from the PSR with only whitespace formatting. Do not copy names/
marks into the report, convert grades, guess classifications or substitute exams.
Each course must belong to that PSR school and the report's original grade; a
transcript cannot merge different original PSR school years. Website school-name
aliases and school-year formatting still require the explicit referenced facts.

1. `captureParent(tab)` reads the saved summary/counts, checkbox and all visible
   statuses. `open(tab,parent)` reads the scoped editor, pending rows and public
   DOM action owners. Retain that original parent throughout unsaved steps.
2. Send `{page}` to `common-academic-preview --profile ... --target ... --report-ref
   ...`. Require all source/fact gates before creation. For requested `choice_keys`,
   call `inspectChoices(tab,parent,keys)` and preview again. This is read-only.
3. Send `{page,context}` to `common-academic-prepare` with the same arguments.
   Persist its successful journal before `applyStep(tab,plan,context,parent)`, adding
   `journal_persisted:true`. Real-account QA/restore flags are rejected.
4. After every stage, send its fresh `{page}` to `common-academic-advance --profile
   ... --checkpoint ...`; inspect requested choices and advance again as needed.
   Header/count/N/A stages never save. Only an entirely blank trailing placeholder
   may be removed; conflicting populated records stop before Add/header actions.
5. A fresh `stage:fields` plan covers the whole editor. `applyStep` checks complete
   values/validity before `saveAndRead` saves the modal draft, reloads and reopens.
   Send its returned payload to `common-academic-verify` with the same checkpoint.
   Every value, school/year/scale/term attribution, count and unrelated status must
   agree. The outer completion declaration remains a student action.

Resume with `common-academic-advance` and the current observation. It preserves the
original journal and rechecks sources/protected fields. A stage with no observed
effect stops; never blindly repeat Add. To abandon unsaved changes, call
`cancelUnsaved(tab,context,parent)` and send its independently revisited saved page
to `common-academic-cancel`. Exact original values, shape, validity, parent and
statuses must match. Saved interruptions resume toward confirmed facts, never by
saving invalid blank originals. Generic page filling/verification/recovery rejects
these transactions.

Evidence: actual 98-field ninth-grade/Add-transcript/header layouts were inspected
with unsaved cancellation and full original checks. Two fictional schools, mixed
symbol/percentage scales and semester/yearly terms passed creation, Save, reload/
reopen and full readback in Edge. Actual new-record Save/rollback and the entire
fresh-student application remain unverified.

### Current/most recent year courses and grade-12 status

`common_current.mjs` exports `createCommonCurrent(host)`. Use its `inspect(tab)`
on the observed `/common/4/24` page. It reads visible count/scheduling/row owners,
fresh single-select options, and the actual multi-select term chips/listbox.
Hidden preallocated rows are excluded. Only these observed course-name textareas
are writable; generic narrative controls remain excluded.

The agent assembles a `current-study-report/1` fact in the existing JSON from
confirmed facts and PSR references; do not ask the student to author configuration.
It has `enrollment_ref`, `scheduling_ref` and `courses`. Each course contains a
unique `key`, original `record_ids`, `subject_ref`, `level_ref`, `terms_ref`,
`label_ref`, `grouping_ref`. Enrollment is the explicit complete original-record
list. Scheduling is an explicit Semester/Trimester/Quarter/Yearly fact. One-record
courses set both optional refs to null and use the PSR name. A grouped course
requires a student statement scoped to every original record, explicit display
label and matching ordered grouping list. Terms reference an explicit label list,
such as `["First Semester"]`; do not infer from PSR completion dates or credits.
All selected records must have the same original school year. No grade or credit
is summed, replaced or averaged, and unresolved missing marks do not block a clear
name-only reference. Genuine name/context ambiguity still blocks it.

Send `{page}` to `common-current-preview --profile ... --target ... --report-ref
...`. Read-only preview leaves profile bytes unchanged. After all gates pass,
send `{page,context}` to `common-current-prepare` with the same arguments. Persist
its journal before `apply(tab,plan,{...context,journal_persisted:true})`. Count and
scheduling steps return fresh inspected pages; send each to `common-current-advance
--profile ... --checkpoint ...` before further input. Changing an already populated
count/scheduling system is blocked. The final `fields` plan covers every course.
After apply, call `saveAndRead` and send its full result to `common-current-verify`.
Only a revisited saved page with all expected values/shape/statuses verifies.
No extra row is added when existing count and source values already match.

Resume the same checkpoint with `common-current-advance`; never overwrite an
active journal. For unsaved cancellation, `cancelUnsaved` reloads the original
saved draft; pass its returned payload to `common-current-cancel`. Saved existing-
shape QA recovery uses `common-current-recover`, then apply/save its restoration
plan and `common-current-verify --restoration`. Real count/scheduling changes and
invalid originals are excluded from this QA strategy. Exact original values,
selected term sets, shape and every captured status must match before clearing.

The multi-select's required search input is empty even with selected terms.
Only this recognized chip widget uses its explicit public `aria-invalid`/owner
state and selected-chip count for semantic validity. Actual site errors remain
invalid; native search-text `valueMissing` must not erase already selected terms.
Fresh popup ownership/options and whole-page verification still apply.

`createCommonFactual(host,'grade12_status')` uses the standard page-plan/prepare/
verify/recovery lifecycle on `/common/13/58`. It supports blank/No observations
only, with the explicit false fact above. An existing Yes or extra grade controls
are rejected. Official grade-12 transcript creation remains unsupported. Actual
No-page inspection is read-only until the student confirms that particular fact.
These ports currently execute separately from `createCommonWorkflow`.

### Inventory relay

`coverage-inventory --profile ... --target ...` reads `{pages,routes}` through
stdin. Supply fresh actual page observations and observed navigation routes
`{url,label}`. It reports uninspected routes, required missing/conflicted facts,
academic reviews, nested collections, manual fields and sourced optional
recommendations without changing the JSON. Its completion claim is limited to
those supplied observed routes. Inspect conditional branches independently;
never treat an empty summary, unvisited page or hidden branch as covered.

Rejected observations remain separate inventory diagnostics and cannot authorize
fills. One invalid page must not erase the gaps on all other supplied routes.
Counts distinguish captured, accepted and rejected observations. Actual UC Contact
information returned masked duplicate radio-option values through this host; it
remains rejected and requires review, independently of its authorization controls.
Production UC pages without a supported observed contract are blocked in both
the planner and host guard, even when they expose a Save button and zero required
native fields. An empty or optional-only plan does not establish page coverage.
The same rule applies to production Common App beyond its supported Personal
Information page, tagged IELTS/Household/Language contracts and scoped grade dialogs. In particular,
the Responsibilities/circumstances checkbox group's missing native required flags
must not turn into an empty ready plan or an inferred negative answer.
