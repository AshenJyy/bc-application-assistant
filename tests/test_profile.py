import copy
import json
from pathlib import Path

import pytest

from bc_application.profile import (ProfileError, add_exam, add_statement, add_target, bind_fact,
    check_sources, clarify_marker, clarify_review, create_profile, register_document,
    resolve_conflict, review_requirements, review_with_document, set_course_schedule,
    set_fact, validate_profile, relink_document)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def profile():
    return create_profile(FIXTURES / "synthetic_psr.pdf")


def marked_course(profile):
    return next(r for r in profile["academic"]["courses"] if r["raw_cells"]["equivalency_marker"])


def test_shared_facts_across_three_targets_without_duplicate_profiles(profile):
    source = add_statement(profile, "Invented student states their name and selects three test targets.")
    set_fact(profile, "personal.legal_given_name", "Synthetic", source)
    targets = [add_target(profile,system=s,school=f"Synthetic {s}",program=None,source_id=source)
               for s in ("uc","mit","common_app")]
    for t in targets:
        bind_fact(profile,t,"legal-first-name","personal.legal_given_name")
    assert len(profile["facts"]) == 1
    assert all(t["field_bindings"]["legal-first-name"] == "personal.legal_given_name" for t in profile["targets"].values())
    assert all("profile" not in t and "facts" not in t for t in profile["targets"].values())
    validate_profile(profile)


def test_marker_explanation_is_scoped_and_does_not_infer_exam_or_change_raw_grade(profile):
    record = marked_course(profile)
    raw = copy.deepcopy(record["raw_cells"])
    source = add_statement(profile, "For this invented course only the marker denotes equivalency credit.",scope=[record["record_id"]])
    clarify_marker(profile,[record["record_id"]],meaning="equivalency_credit",statement_source_id=source)
    required = review_requirements(profile,record["record_id"])
    assert len(required) == 1
    assert not required[0]["student_clarification_required"]
    assert required[0]["transcript_or_report_card_review_required"]
    assert record["raw_cells"] == raw
    assert profile["exams"] == {}
    assert profile["marker_explanations"][record["record_id"]]["verification"] == "student_reported"
    # The same parser sees the same E in another applicant; no shared meaning leaks.
    other = create_profile(FIXTURES / "synthetic_psr.pdf")
    assert not other["marker_explanations"]
    assert review_requirements(other,record["record_id"])[0]["student_clarification_required"]


def test_explicit_exam_score_remains_separate_from_school_percentage(profile):
    record = marked_course(profile)
    source = add_statement(profile,"Synthetic student explicitly reports AP score 4 of 5.",scope=[record["record_id"]])
    exam_id = add_exam(profile,name="AP Calculus BC",system="AP",score=4,scale="AP_1_to_5",
                       source_id=source,related_course_ids=[record["record_id"]])
    fact = profile["facts"][profile["exams"][exam_id]["score_fact_id"]]
    assert fact["value"] == 4 and fact["scale"] == "AP_1_to_5"
    assert fact["verification"] == "student_reported"
    assert record["raw_cells"]["school_percent"] == "93"
    assert record["raw_cells"]["provincial_exam_result"] == ""


def test_registered_document_alone_does_not_resolve_review(profile):
    record = marked_course(profile)
    transcript = register_document(profile,FIXTURES/"synthetic_transcript.pdf",kind="transcript")
    review = review_requirements(profile,record["record_id"])[0]
    assert review["transcript_or_report_card_review_required"]
    with pytest.raises(ProfileError,match="student_clarification"):
        review_with_document(profile,review["review_id"],transcript,page=2,quote="AP CALCULUS BC 12A 29-May-2026 A 93 93 E 4")
    statement = add_statement(profile,"Synthetic explanation of this course only.",scope=[record["record_id"]])
    clarify_marker(profile,[record["record_id"]],meaning="school_specific_equivalency",statement_source_id=statement)
    review_with_document(profile,review["review_id"],transcript,page=2,quote="AP CALCULUS BC 12A 29-May-2026 A 93 93 E 4")
    assert not review_requirements(profile,record["record_id"])
    assert profile["marker_explanations"][record["record_id"]]["verification"] == "student_reported"
    validate_profile(profile)


def test_psr_cannot_be_renamed_as_transcript_and_duplicate_documents_are_not_copied(profile,tmp_path):
    with pytest.raises(ProfileError,match="does_not_replace"):
        register_document(profile,FIXTURES/"synthetic_psr.pdf",kind="transcript")
    first = register_document(profile,FIXTURES/"synthetic_transcript.pdf",kind="transcript")
    second_path = tmp_path / "identical.pdf"
    second_path.write_bytes((FIXTURES/"synthetic_transcript.pdf").read_bytes())
    second = register_document(profile,second_path,kind="transcript")
    assert first == second and len(profile["sources"]) == 2


def test_mixed_schedules_are_explicit_and_do_not_replace_psr_dates(profile):
    a,b = profile["academic"]["courses"][:2]
    source = add_statement(profile,"Synthetic timetable states a semester course and a full-year course.",scope=[a["record_id"],b["record_id"]])
    set_course_schedule(profile,a["record_id"],duration="semester",term_label="Semester 1",source_id=source)
    set_course_schedule(profile,b["record_id"],duration="full_year",source_id=source)
    assert profile["facts"][f"schedules.{a['record_id']}.duration"]["value"] == "semester"
    assert profile["facts"][f"schedules.{b['record_id']}.duration"]["value"] == "full_year"
    assert all(c["duration"] is None for c in profile["academic"]["courses"])
    assert not any(key.endswith("start_date") for key in profile["facts"])
    with pytest.raises(ProfileError,match="date_range"):
        set_course_schedule(profile,a["record_id"],duration="semester",source_id=source,start_date="2026-12-01",end_date="2026-01-01")


def test_conflicting_facts_require_explicit_resolution(profile):
    first = add_statement(profile,"Synthetic student says their city is Cedar.")
    second = add_statement(profile,"Synthetic student later says their city is Coast.")
    set_fact(profile,"contact.city","Cedar",first)
    conflict = set_fact(profile,"contact.city","Coast",second)
    assert profile["facts"]["contact.city"]["value"] == "Cedar"
    assert profile["conflicts"][conflict]["status"] == "unresolved"
    resolution = add_statement(profile,"Use Coast as my current city.")
    resolve_conflict(profile,conflict,choose="candidate",confirmation_source_id=resolution)
    assert profile["facts"]["contact.city"]["value"] == "Coast"
    assert profile["facts"]["contact.city"]["verification"] == "student_confirmed"
    assert "candidate" not in profile["conflicts"][conflict]
    assert profile["conflicts"][conflict]["alternative"]["value"] == "Cedar"
    validate_profile(profile)


@pytest.mark.parametrize("field",["academic.grade","personal.password","personal.essay","identity.signature"])
def test_protected_and_excluded_fields_cannot_be_added(profile,field):
    source = add_statement(profile,"Synthetic statement")
    with pytest.raises(ProfileError):
        set_fact(profile,field,"x",source)


def test_unscoped_explanation_and_invalid_evidence_do_not_change_raw_records(profile):
    record = marked_course(profile)
    source = add_statement(profile,"A general statement with no course scope.")
    with pytest.raises(ProfileError,match="does_not_cover"):
        clarify_marker(profile,[record["record_id"]],meaning="transfer_credit",statement_source_id=source)
    assert not profile["marker_explanations"]
    transcript = register_document(profile,FIXTURES/"synthetic_transcript.pdf",kind="transcript")
    with pytest.raises(ProfileError,match="locatable_document"):
        set_fact(profile,"education.school_name","Synthetic",transcript,evidence={"page":999,"quote":"x"})


def test_invalid_references_and_raw_psr_edits_fail_validation(profile):
    profile["academic"]["courses"][0]["raw_cells"]["school_percent"] = "100"
    with pytest.raises(ProfileError,match="raw_psr_data_changed"):
        validate_profile(profile)


def test_document_relink_changes_only_reference_and_requires_identical_bytes(profile,tmp_path):
    path = tmp_path/"relocated.pdf"
    path.write_bytes((FIXTURES/"synthetic_psr.pdf").read_bytes())
    relink_document(profile,profile["psr_source_id"],path)
    assert profile["sources"][profile["psr_source_id"]]["path"] == str(path.resolve())
    assert not check_sources(profile)
    path.write_bytes(b"different")
    assert check_sources(profile)[0]["issue"] == "source_changed"
    with pytest.raises(ProfileError,match="different"):
        relink_document(profile,profile["psr_source_id"],path)


@pytest.mark.parametrize('page,quote', [(1,'AP CALCULUS BC 12A'), (2,'Invented unsupported grade 100')])
def test_document_evidence_requires_the_actual_quote_on_the_claimed_page(profile,page,quote):
    transcript=register_document(profile,FIXTURES/'synthetic_transcript.pdf',kind='transcript')
    before=copy.deepcopy(profile)
    with pytest.raises(ProfileError,match='evidence_quote_not_found_on_page'):
        set_fact(profile,'education.documented_course','Invented',transcript,evidence={'page':page,'quote':quote})
    assert profile==before


def test_real_document_quote_accepts_layout_whitespace_without_promoting_student_report(profile):
    transcript=register_document(profile,FIXTURES/'synthetic_transcript.pdf',kind='transcript')
    set_fact(profile,'education.documented_course','AP CALCULUS BC 12A',transcript,
        evidence={'page':2,'quote':'AP CALCULUS BC 12A\n29-May-2026 A 93 93 E 4'})
    assert profile['facts']['education.documented_course']['verification']=='document_extracted'
    assert not profile['marker_explanations']


@pytest.mark.parametrize('failure', ['changed','missing','scan'])
def test_unverifiable_document_evidence_cannot_resolve_an_academic_review(profile,tmp_path,failure):
    path=tmp_path/'transcript.pdf'
    fixture='synthetic_scan.pdf' if failure=='scan' else 'synthetic_transcript.pdf'
    path.write_bytes((FIXTURES/fixture).read_bytes())
    transcript=register_document(profile,path,kind='transcript')
    record=marked_course(profile)
    source=add_statement(profile,'Synthetic explanation.',scope=[record['record_id']])
    clarify_marker(profile,[record['record_id']],meaning='equivalency_credit',statement_source_id=source)
    review=review_requirements(profile,record['record_id'])[0]
    if failure=='changed': path.write_bytes((FIXTURES/'synthetic_scan.pdf').read_bytes())
    if failure=='missing': path.unlink()
    with pytest.raises(ProfileError,match={'changed':'evidence_document_changed','missing':'evidence_document_unavailable',
            'scan':'evidence_text_layer_missing'}[failure]):
        review_with_document(profile,review['review_id'],transcript,page=1,quote='AP CALCULUS BC 12A')
    assert review_requirements(profile,record['record_id'])[0]['transcript_or_report_card_review_required']
    validate_profile(profile)  # Missing source recovery remains available.
