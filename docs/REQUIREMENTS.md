# Product goal and confirmed scope (updated 2026-10-18)

## Final student experience

The student provides personal information, academic documents and a chosen school
list through conversation in the ChatGPT desktop app. The assistant identifies
the official application route for each school, collects actual requirements,
reuses the one canonical profile, creates required records, fills factual drafts
and verifies the saved results. The student should not need to know which portal
a school uses, translate a transcript into portal rows, or run development tools.
UC, MIT First-Year and Common App are the first beta platforms, not the long-term
limit. Adding a school must reuse the existing profile and source documents.

For information collection, ask only for missing, ambiguous or conflicting facts
needed by the actual selected applications. Group related gaps and ask once per
canonical fact across schools. Persist each answer with its provenance in the same
profile before using it. Clear PSR values and confirmed answers must not be asked
again because another page or school needs them. Required supplemental evidence
for an unclear record is a source gap, not permission to invent an academic value.
Optional recommendations need a reason and never prevent required factual work.

The agent continues across ready pages without routine per-page approval. Detect
conditional requirements after input, ask only for newly needed facts, and resume
from the saved checkpoint after answers arrive. An unsupported widget or mapping
is an implementation gap, not a reason to ask the student to re-enter known data.
Handle it with a documented browser workflow or report the unresolved coverage;
never silently skip it or claim the application complete. Recover pending writes
before beginning another mutation; independent ready pages may proceed only when
there is no unresolved transaction.

Academic completion is the highest implementation priority. Starting from an empty
application, create schools, attendance/academic years and course records where
required; support multiple schools and mixed semester/yearly courses. Map only
observed fields and explicit facts, retain original course names/grades/scales and
evidence, and keep school marks separate from exam results/equivalency explanations.
Collect missing term, status, credit or reporting classification facts once rather
than derive them from a course title. Verify saved record counts, school/year
attribution, terms, original marks and all other entered values, not just a summary
badge. Review an existing matching saved draft without needless rewriting.

This is the intended product experience, not a claim that every current ChatGPT
surface, application system or conditional branch is implemented. Login, MFA,
CAPTCHAs, denied access and student-controlled final actions are separate handoffs;
they must not be presented as missing applicant information. Current supported
runtime and permissions remain documented in [RUNTIME](RUNTIME.md). Existing beta
exclusions below remain in force: the broader filling goal does not authorize
essay entry, subjective answers, declarations, invitations, submission or payment.

Saved readback remains the default. The applicant may explicitly request direct
Save-and-Next without independent reopening. Honor that preference for intended
draft filling, record it once in the canonical JSON and report saved/unverified.
It does not remove source/missing-fact gates, website validation, final-action
boundaries or real-account QA restoration. Legacy ports need a supported
continuation path; do not pretend a skipped read was successful verification.

## Beta scope and operating boundaries

- First release assumes an available BC PSR and the BC curriculum. Reuse explicit
  PSR facts without a redundant curriculum interview. BC does not establish one
  grading scale or term system; multiple schools and mixed schedules remain valid.
- Windows x64 beta; local desktop Work/Codex execution with Edge first. Chrome
  validation is deferred; keep the browser abstraction for later support.
- Fall 2027 first-year UC, MIT, Common App. Common App supplements are not all covered.
- Require a BC Permanent Student Record PDF before application processing begins.
- Check required permissions before starting, request missing access, then recheck.
- Only explicit factual answers. General essays and subjective judgments remain
  excluded. The user authorized collecting/reusing/polishing the two observed
  Common App school explanations (transfer and progression), without adding facts.
- Discover actual required and recommended fields for the student's chosen targets.
- Explain recommended fields and reasons; the student decides whether to include them.
- Gate writes at the current page, not the entire application. Missing required
  factual data pauses that page; manual essay/subjective fields also pause completion.
- Unclear PSR: require a transcript/report card AND student clarification. Oral
  statements may be entered but stay student-reported. Never infer missing facts.
- Preserve original grades/scales and evidence/verification on every academic record.
- Support multiple schools, mixed course durations, and explicit unknown durations.
- One complete applicant JSON in a student-selected directory, shared across systems.
- The student interacts through chat. JSON storage, page plans and runtime commands
  are implementation details; they are not recurring student tasks.
- Whole-page fills followed by saved-state readback and verification.
- Never submit, invite, sign declarations, or make payments automatically.
- Real account testing is authorized only if every edit is restored and restoration
  is verified. Only the scoped factual school explanations may be edited as above;
  general essays, final submissions and payment tests remain excluded.
- Public data: synthetic fixtures only. Exclude all personal data from Git/releases.
- Portable root manifest, skill, Python core, internal modular future interfaces,
  no MCP or hooks in beta. No claimed College Planner integration.
- GitHub upload and publication belong to the product manager after acceptance.
- Reserve internal College Planner interfaces based on announced features without
  claiming a working integration. Avoid duplicated personal documents/profiles.

"All required fields" means discovering and accounting for them, including manual
handoffs. It does not authorize writing excluded fields or forbidden final actions.
Browser/host limitations must produce a clear checkpoint, not a false success.

## End-to-end acceptance for this product goal

- A new synthetic BC student supplies a PSR, explicit supplemental facts and school
  list through a chat-led workflow. No prefilled school/course rows or test-account
  settings may be required to make the happy path work. Start from empty drafts.
- The student is not asked to identify a platform or bind fields. Official school
  application routes and entry cycle are checked; ambiguous school/program identity
  is resolved as a target-information gap. Unimplemented routes remain explicit.
- All supported required academic records are created, filled, saved and revisited
  with exact source-backed marks, scales, terms and school/year attribution. Missing
  or conflicting information blocks only dependent work and is never guessed.
- One answer updates the one profile and removes the corresponding question across
  every affected selected school. Add another school and repeat without recreating
  the profile, copying documents or asking for already confirmed information.
- An interrupted browser or saved draft resumes safely without duplicate schools,
  courses or exams. A verified page requires full saved readback; an explicitly opted-out page is
  saved/unverified. Real-account QA
  retains its original-restoration requirement and cannot use an incomplete draft
  as an excuse to save invalid blank originals.
- The report accounts for every observed required field/record as verified, waiting
  for a specific fact/evidence, excluded/manual, or blocked by an implementation/
  access problem. These categories are never collapsed into a success count.
- Keep beta runtime, actual portal evidence and synthetic-only coverage explicit.
  Passing isolated page tests does not satisfy the fresh-student acceptance above.
