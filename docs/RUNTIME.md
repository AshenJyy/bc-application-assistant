# Runtime limitations and permissions

Beta requires Windows x64, Python 3.12, a local desktop task with shell/files,
and a supported connected Edge browser for the first beta. Chrome validation is
deferred. Model inference is hosted;
local script execution and local JSON storage do not imply offline inference.

Preflight distinguishes machine checks from host authorization. M1 checks PSR
title and supported course-table layout in addition to readable PDF bytes. It
does not authenticate the document or verify the facts. Python cannot
verify Chrome/Edge site permission or host UI availability. The skill must check
those using actual host observations, request missing permissions, and pause on denial.

Browser setup: use Settings > Computer Use, install the official ChatGPT extension
for the chosen profile, and verify the browser is connected. Login/OTP is manual.
Never use a private/undocumented browser protocol or hardcoded host tool internals.
Do not open the built-in browser. Not every account/plan exposes every tool.

The host must expose a JavaScript runtime able to import the packaged ES module
and its built-in `node:crypto`, plus documented extension-tab Playwright locators.
The module receives an already connected tab; it never launches a browser or
uses hidden endpoints/framework state. Python exchanges private observations and
plans with the host via stdin/stdout; it cannot independently control a browser.
See the skill's browser workflow for the explicit host-tool relay.

The parser supports specified text-based PSR layouts;
scanned, encrypted, or unfamiliar documents must stop or require clearer evidence.
This PSR parser limit does not require replacement of a scanned supplemental
report card: `evidence-preview` renders a private temporary page with bundled
dependencies for explicit manual review. This needs the host's supported image
viewer and private-directory write access. Manual review remains distinct from
automatic text extraction; documents still need valid hashes/pages and relevant
student clarification. Do not infer missing grades or course schedules from an image.
Essay, subjective answer, invitations, declarations, certification, payments and
submission remain manual even if the website marks them required. Required field
discovery includes validation and conditional fields, not just `*` labels.

UC Personal information has observed mappings; additional factual native controls
require explicit bindings after inspecting the current school/program page.
Custom widgets, embedded frames, selected multiple selects and unknown requirements stop.
Conditional fields must be exposed/collected before saving a page. MIT First-Year
and Common App common-section adapters share the same gates; only recognized factual
name/address textareas are editable. Only the two observed optional MIT coursework
notes may remain exactly empty and untouched; required/nonempty/unknown narratives
still block a save. Explicit student-provided subject statuses bind to native options;
Year and subject classification are never inferred. Known optional
unsupported controls may stay untouched. College supplements and Common App Writing
are excluded. Chrome and Edge synthetic save/revisit/restoration passed for all three;
one real Common App Personal Information workflow also passed. Its before-write
checkpoint captured all seven controls and 14 visible navigation statuses; save
and restoration were verified after revisiting. The completed-page strategy is
bound to observed status evidence, and restoration may repair values when status
drift occurs. Common App existing 9th–11th Grade course editing also passed real
whole-dialog save/reload/reopen and restoration of 98/94/138 values, 13 statuses
per page and each original parent summary/checkbox. Native course names changed
to PSR text; percentage dropdowns reselected the same scores in 9th/10th Grade.
11th Grade mixed semester/yearly schedules passed with grades unchanged. Reused
IDs require page-scoped bindings. New records, header changes,
clearing Material controls and remaining grade pages remain unverified. MIT coursework
passed same-value selection/save/revisit/readback of its eight STEM status/year controls
with full visible review/draft state comparison. UC Personal information passed
same-value selection/save/revisit with twelve controls, seven sections and 32 page
statuses. Real changed-value MIT/UC Personal recovery remains unverified.
UC Full/Semester selectors use a separate two-stage refill transaction: persist
originals, select terms, reobserve rebuilt grade controls, persist their exact
source-backed plan, then save/reopen the complete page. Actual 11th/12th same-term
reconstruction and original grade/status re-entry passed full 87/18-field and
review/draft-state verification. School term-availability changes can reset grades;
the school port declines the observed reset warning and does not accept it.
Exact label plus optgroup may disambiguate a confirmed choice; a duplicate label
alone is never enough. A name-only PSR reference does not assert missing results.
MIT record tables require nested editors and remain unsupported, except the one
observed empty U.S.-only Classes table for explicitly confirmed Canadian/non-U.S.-system
students. Conflicting optional/required signals block the
page rather than manufacture a preference. The UTF-8 host relay handles Windows
legacy locale defaults explicitly. See FIELD_COVERAGE.md for the actual inventory.

Python 3.12 itself must already be exposed by the host or installed. Runtime PDF
dependencies are bundled as hashed Windows x64 wheels; bootstrap installs them
offline in a chosen isolated venv. An ARM64/other Python version needs a future
platform bundle. This runtime is not another applicant profile. Wheel licenses
are retained in their distribution metadata. Development extras are not shipped.

Official sources checked 2026-10-13:

- https://developers.openai.com/plugins/build/plugins
- https://developers.openai.com/plugins/build/skills
- https://developers.openai.com/plugins/deploy/desktop-only
- https://developers.openai.com/plugins/deploy/submission-errors
- https://learn.chatgpt.com/docs/chrome-extension
- https://learn.chatgpt.com/docs/enterprise/chatgpt-work-local-security

Packaging and desktop-only manifest requirements rechecked 2026-10-14 against the
first and third sources. Common App per-course term requirements were checked
against its [academic record reporting guide](https://www.commonapp.org/files/webinar_decks/Academic-Record-Reporting.pdf),
page 8, and the actual current editor. Live labels/validation remain authoritative
for the applicant's selected configuration; never require every unused term cell.

Passing local ZIP checks is not directory approval. Publisher verification,
portal scans, listing completeness, and actual Windows app testing are separate.

Packaging and desktop-only requirements were rechecked 2026-10-18 against the
official package and desktop-only pages above. The first beta now prioritizes Edge;
Chrome real-portal validation is deferred by product scope.

The fixed UC factual port ships one public JSON contract resource shared with
Python. It uses the documented native Save click and exact observed review hrefs;
IELTS's editor can otherwise navigate without saving on Enter. Background and
7th–8th Grade passed real same-value original/status checks, as did Citizenship/
residency. The existing IELTS editor passed an intended current-record update and
full saved readback. Term/level remains read-only/synthetic-tested. New exam creation/deletion and general
nested records remain outside this port. Contact/Parent authorization fields
block automatic saves. Successful requested fills clear temporary original-value
journals after verification; developer tests retain them until full restoration.

The fixed Common App IELTS port ships its own shared public JSON contract. Its
whole-page input comboboxes require exact associated native listbox options; they
cannot use the generic text writer. Actual sitting count, historical-highest
confirmation and no planned future sitting are explicit prerequisites. The saved
current-score update passed all twelve values and complete visible navigation
state. Incomplete original recovery cancels unsaved edits or resumes the intended
source-backed fill; it never saves blank invalid originals. General test-record
creation and real changed-value original recovery remain unverified.

The shared Common App factual port adds Household and Language groups. Its fixed-
shape workflow requires matching existing rows; count changes use the staged port
below. Other-language/independent-status branches remain unimplemented. Its saved
readback/recovery shares the IELTS lifecycle. The read-only collection agenda merges
required factual gaps across observed targets, reuses known answers and identifies
already-matching complete pages. It cannot turn an unsupported page into a fillable
one or authorize unseen conditionals. Address lookup is still a separate nested
editor; masked Contact phone values cannot establish exact readback/restoration.

Dev.21 adds a separate intended-update language workflow that sets a count and then
fills freshly observed rows. It requires the whole explicit language list/abilities
first, keeps one temporary journal and resumes from either stage. Empty-page and
changed-count behavior is synthetic-tested; actual changed-count QA restoration is
unverified and excluded. Unsaved cancellation verifies the old saved draft; saved
interruptions resume the intended factual update. Other-language explanations,
independence-status branches and other new record types remain unsupported.

Dev.22 adds Common App 9th–11th grade transcript/course creation after Education
schools already exist, using Other/1-100 scales and Semesters/Yearly with explicit
term placement. Source-reference reports avoid duplicate names/marks. New Education
schools, grade 12, other layouts and actual new-record Save/rollback are unfinished.
The outer declaration stays manual. First-use Save/revisit passed in Edge with
fictional data; actual inspection was canceled without saving.

Dev.23 adds Common App Current/Other Secondary School flows with a packaged shared
public contract and `common_schools.mjs`. The separate school directory cache lives
inside the same canonical JSON; source documents stay in place. Exact complete
BC/Canada public search matches precede school selection. Dates reference PSR
enrollments, with explicit boarding/graduation/progression facts and student-
provided explanations for the two authorized factual questions. New-school
first-use Save/revisit has fictional Edge evidence; existing actual records passed
changed-date/text saved verification and full original/status restoration. Other
school counts beyond one, first-use actual blank layouts, manual/not-found schools,
non-graduate branches, grade 12 and actual new-record rollback remain unverified.
CKEditor validation is triggered only through public focus/Tab and reobserved;
the plugin cannot suppress website validation. Earlier plugin versions cannot
read profiles after optional school-directory metadata has been added; use dev.23+.

Dev.24 adds `workflow-preview` and a host coordinator for supported Common App
school/grade pages. Callers provide documented ports, one bound CLI relay and an
independent saved-draft observer using a temporary browser tab. The coordinator
does not launch browsers, store another profile or connect to a planning service.
It requires existing whole-workflow user authorization, preserves unknown initial
unsaved work and refuses real-account new-record QA. Connected empty-page/restart
and second-university reuse evidence is fictional Edge only. Other adapters,
grade 12, all PSR-course reporting, official university routing and full application
coverage remain outside this coordinator's completed scope.

Dev.25 packages the shared current-year contract, host port and reusable source
compiler. The `common-current-preview/prepare/advance/verify/recover/cancel` relay
family uses the same JSON and local runtime. Count/scheduling require reobserved
rows before field entry. Native term chips and their public Options popup are
handled by the dedicated port; generic single-select/narrative writers cannot
substitute. The grade-12 confirmed-No contract reuses the factual page lifecycle.
These two ports execute separately from the dev.24 connected coordinator. Actual
current-year existing-shape recovery is verified; actual initial blank layouts,
changed count/scheduling rollback and official grade-12 records are unverified.
Resume current-year transactions with dev.25 or newer.

Dev.26 adds the shared native-form semantic path through `generic_forms.mjs` and
the existing page CLI. Runtime analysis is proposed by the current agent through
stdin; no separate model service, API key or MCP is introduced. See the packaged
generic-form reference for the complete protocol. `generic-preview` is read-only;
`generic-resume/recover/cancel` operate the same canonical transaction. The store
allows append-only answers to recorded pending conditional facts during that one
transaction, while previous data/evidence/journal remain frozen. A generic target
has optional authorized site metadata and may use `system:web`; profiles using
these new targets require dev.26+. Ordinary earlier profiles remain readable.
Generic observation needs one native form; production site-wide status recovery,
custom widgets, repeat-record creation and generic real-account QA are unverified.

Dev.27 supports the specific observed native-backed owned combobox and public
calendar shapes described in the generic-form reference. Other custom widgets
remain unsupported. `generic-stage`, `generic-stage-accept` and
`generic-stage-restart` keep one journal through explicit factual conditional
changes. A staged one-controller plan cannot Save. Only whole-page acceptance
enables the usual draft-save and saved verification. Website validation or a
next-section timeout preserves the current page; same-URL navigation may need a
separate public-UI saved reader. There is no HKU-specific runtime or integration.

Dev.28 adds bounded nested fact paths, read-only PSR school/context references and
separate record checkpoint instances. Its named-dialog port saves a whole ready
native editor, but returns a receipt requiring an independent reopen and saved
verification. It cannot reload/cancel a modal or coordinate a record list for the
caller. These checkpoints require dev.28 or newer to resume. Explicit
`profile-update --append-new-student-facts` permits only new student-reported facts
while a single generic journal is active; existing data stays frozen. Recheck
authenticated access after an answer wait: a stale form can remain visible after
login expiry. See the generic-form reference for the complete protocol and limits.


Dev.29 adds verified shared-directory metadata, read-only parent summaries and
bounded count controllers using documented typing/blur events. A student may
explicitly choose `workflow.saved_page_readback:false`; the generic port then
supports receipt-based saved/unverified continuation and prefers Save-and-Next.
The canonical checkpoint retains its historical journal but does not block the
next page. This cannot acknowledge branch plans, website errors, legacy ports or
real-account QA. New parent/receipt checkpoints require dev.29+; see the packaged
generic reference for schemas and source gates. No additional permission, browser
interface, server, hook or external API is introduced.


Dev.30 adds exact named-dialog draft Add with an explicit canonical record
capability and precision-preserving year/month date projections. Resume these
proposals with dev.30+. It introduces no browser API or external dependency.


Dev.31 adds original PSR course metadata, student-authorized result dates/current
status, explicitly calculated context or course-level Best 5 averages, canonical exam references and
observed editor views. These proposals require dev.31+. School prediction absence
remains blocked data without another prompt. A discarded blank editor may retain
a historical inactive journal marked canceled_ui_drift; it is never verified
restoration. No extra service, browser interface or dependency is introduced.
