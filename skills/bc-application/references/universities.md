# University adapter support

All adapters require PSR/source/data gates, observed fields, an explicit student
target, documented browser permission, a journal before writing and saved-state
readback. Required fields for the selected school/program must be discovered on
the actual current page. This is a development preview, not a promise that every
page/control in the three applications has passed end-to-end validation.

| System | Observed mappings and supported extension | Boundaries |
|---|---|---|
| UC | Personal information names, birth fields and explicit factual questions; same-value native selection/save/revisit and full visible status comparison passed | No inferred A-G subjects, honors, residency, schedules or grade conversions; unknown widgets and conditional personal-history variants stop; real changed-value Personal recovery and AP term reconfiguration remain unverified |
| MIT First-Year | Visible legal/preferred name labels, permanent/mailing address headers, email/mobile, birth data, citizenship and explicitly reported legal sex/communication-name choice | No identity/visa/major choice made by the assistant; unrecognized required fields need binding/answers; narrative textareas and certification stop |
| Common App | Automatic student-identity labels are limited to Personal Information; other allowed common sections require explicit factual bindings. Personal information and existing 9th–11th Grade editors passed real saved readback/restoration | Parent names must not reuse student labels. Writing, college-specific questions/supplements, invitations, fee-waiver attestations, signature, payment and submission excluded; new records and custom controls outside the scoped grade port remain unsupported |

Only automatically mapped fields on the observed pages are claimed as tested.
Other factual fields need an observed key bound to a shared canonical fact; any
unknown mandatory field blocks the entire page. Activities descriptions are not
generated or entered; the beta may handle factual names/counts/hours only when
the corresponding fields are supported and explicitly supplied.

Store a single explicit ISO `personal.birth_date`, then format it for the observed
date controls (UC/MIT options or Common App's displayed date string). This does
not infer an unknown date. Inconsistent older date fragments block until resolved.
Never merge student-reported test scores with school-course percentages. Preserve
the original grade scale; no exact option match means stop, not convert.

Official references checked 2026-10-13:

- [UC international application records](https://admission.universityofcalifornia.edu/admission-requirements/international-applicants/applying-for-admission/)
- [MIT application portal](https://apply.mitadmissions.org/portal/apply)
- [Common App first-year guide](https://www.commonapp.org/apply/first-year-students/)

School-specific testing/writing/deadline requirements may differ and change; obtain
them from the current school's official information and active application page.
No obsolete requirements grid is bundled as Fall 2027 policy. Recommendation
entries link a source, explain the benefit and identify assistant reasoning.

## Academic-page verification (2026-10-14)

| Observed page | Actual control/requirement evidence | Preview result |
|---|---|---|
| MIT Self-reported coursework | An empty U.S.-only Classes table; four subject status/year pairs required of all students; two optional narrative notes | Actual eight-answer same-value selection/save/revisit/readback passed, including ten controls and visible review/draft state. Require explicit status, year and Canadian/non-U.S.-system facts; leave the known notes exactly empty. Nonempty/other record tables and changed-value MIT recovery remain unverified |
| Common App existing 9th–11th Grade editors | Custom school/year/scale/schedule/subject/level dropdowns, repeated native grade IDs and an outer completion attestation | Changed-name saves/readback/restoration passed for 98/94/138 controls, 13 statuses and parent state per page. Grade values were unchanged. The scoped grade port supports observed Material selections; headers, new records, clearing Material values, other grade pages and outer attestations remain excluded |
| UC academic history | The existing authenticated tab exposed high-school summary/edit actions and native course category/name/honor/grading-system/grade controls. Some labels have incorrect associations | Scoped wrapper labels and option groups are preserved; synthetic Chrome native course controls passed save/revisit/restoration. Course classification, honor and periods need explicit evidence/answers. Existing 9th/10th whole editors passed actual PSR-name changes/save/revisit/full restoration (36/42 controls, original summaries and full visible status). Original grade values stayed unchanged; AP term reconfiguration, new records and full coverage remain unverified |

Fixtures contain fictional applicant answers; public field labels/layout are based
on the observed portals. Inspection, synthetic tests, same-value saves and changed-value
recovery are recorded separately in FIELD_COVERAGE.md. Required course schedule/classification/grade evidence must
still come from the applicant and appropriate records, not the website's current
answers. Do not automatically tick a statement that all courses have been reported.
