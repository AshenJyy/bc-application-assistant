# College Planner extension seam

OpenAI's 2026-10-07 announcement describes a student-selected college list,
application requirements, deadlines, tasks/progress, financial-aid steps,
scholarships and fee waivers:
https://openai.com/index/teens-learn-and-plan/

The reviewed announcement provides product capabilities, not an integration API
contract. BC availability and API access are not established by that announcement.
This plugin is not connected to College Planner and has no network client for it.

The internal `planning.py` protocol is our inferred future seam, not an OpenAI API:

| Announced capability | Reserved internal exchange |
| --- | --- |
| Student's college list | Canonical target IDs; student selects schools/programs |
| Application requirements | Sourced planning items referring to canonical field IDs |
| Deadlines/timeline | Original deadline text and explicit timezone; no guessed dates |
| Tasks/progress | References to local checkpoint IDs and proposed status updates |
| Financial aid | Sourced aid-step requirements; no eligibility judgments or payments |
| Scholarships/fee waivers | Informational planning items; student decides what applies |

Each call refers to a profile ID and revision, not a second applicant JSON.
M2 will own persistence, target/field IDs, conflict detection and confirmed updates.
Provider responses are evidence/suggestions; they cannot overwrite academic facts,
fill subjective answers, submit applications or waive the student's checkpoints.
External writes will require explicit authorization and a documented implementation.
The default provider advertises no capabilities and raises an unavailable error.

Single-source storage: one authoritative profile, source PDF paths/hashes instead
of copied PDFs, centralized executable package used by CLI and future adapters,
no duplicate university-specific applicant data. Plugin host installation caches
and dependency files are operational copies, not extra personal profiles.
