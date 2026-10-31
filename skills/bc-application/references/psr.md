# PSR extraction (M1)

For ordinary use initialize the canonical JSON directly with `profile-init` as
described in [profile](profile.md). `parse-psr --output` remains a diagnostic tool;
it refuses overwrite. An existing M1 extraction can migrate in the same file.
Do not retain it as a second profile or write private output inside skill resources.

Supported input: selectable-text MyEducation BC ruled PSR layout with the explicitly
observed ten course columns. Row continuations across pages and headerless tables
are accepted only when grid geometry matches the observed column header and there
is an existing school/year context. Missing/ambiguous contexts stop the parse.

Every course stores ten raw cells, a context reference and a source locator (hash,
page/table/row/bounding box). School/year contexts and source metadata are stored
once. Enrollment rows and provincial graduation assessments retain their raw cells.
Course/school grade symbols, school percentages, provincial results, final results,
equivalency markers, and credits are distinct columns. Nothing converts to GPA,
guesses AP exam scores, expands unexplained markers, or rounds original grades.

`extracted_unreviewed` means extracted, not independently verified or approved for
writing a website. Blank results do not establish enrollment, planned/in-progress
status, or completion. Duration, semester and start date stay null. Ask for a
transcript/report card and student clarification for flagged unclear records.
Clear original PSR columns remain the primary academic evidence. A scoped student
marker explanation permits those original values without redundant transcript
confirmation; it does not invent a course period/status or document-verify an
exam score. The unresolved supplemental review remains recorded for later needs.
If an application requires scheduling absent from the PSR, collect that evidence
and explanation before filling the affected page. Oral statements retain their
student-reported status; do not overwrite the PSR's raw cells.

Scanned, encrypted, unsupported grids, reordered columns, detached course rows,
mixed/unrecognized course layouts or PDFs over 25 MiB/30 pages fail closed. The
parser does not certify document authenticity, infer graduation, or read unrelated
private information. It cannot guarantee support for every BC school's PSR export.
