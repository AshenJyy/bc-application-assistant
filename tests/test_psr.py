import hashlib
import json
from pathlib import Path

import pytest

from bc_application.cli import main
from bc_application.psr import PSRError, parse_psr
from tools.synthetic_psr import write_fixture

FIXTURES = Path(__file__).parent / "fixtures"


def test_multiple_schools_wrapping_continuation_and_original_grades():
    result = parse_psr(FIXTURES / "synthetic_psr.pdf")
    assert len(result["schools"]) == 2
    assert len(result["contexts"]) == 4
    assert len(result["courses"]) == 7
    assert len(result["assessments"]) == 1
    contexts = {c["context_id"]:c for c in result["contexts"]}
    wrapped = next(c for c in result["courses"] if c["raw_cells"]["course_code"] == "MWRAP11---")
    assert "\n" in wrapped["raw_cells"]["course_description"]
    assert wrapped["evidence"]["page"] == 2
    assert contexts[wrapped["context_id"]]["school_id"] == "99990001"
    assert contexts[wrapped["context_id"]]["school_year_raw"] == "2025"
    proficiency = result["courses"][0]["raw_cells"]
    assert proficiency["school_grade_symbol"] == proficiency["final_result"] == "PRF"
    assert proficiency["school_percent"] == ""
    assert proficiency["credits"] == "0"
    assert result["courses"][2]["raw_cells"]["credits"] == "2"


def test_ap_school_grade_is_not_exam_score_and_unknown_markers_require_evidence():
    result = parse_psr(FIXTURES / "synthetic_psr.pdf")
    ap = next(c for c in result["courses"] if c["raw_cells"]["course_code"] == "ACAL-2A---")
    assert ap["raw_cells"]["school_percent"] == "93"
    assert ap["raw_cells"]["provincial_exam_result"] == ""
    assert ap["raw_cells"]["equivalency_marker"] == "E"
    assert ap["verification"] == "extracted_unreviewed"
    requirement = next(r for r in result["review_requirements"] if r["record_id"] == ap["record_id"])
    assert requirement["required_evidence"] == ["transcript_or_report_card", "student_clarification"]
    assert requirement["oral_clarification_allowed"]


def test_blank_results_and_course_periods_are_not_inferred():
    result = parse_psr(FIXTURES / "synthetic_psr.pdf")
    assert all(c["semester"] is None and c["duration"] is None and c["start_date"] is None for c in result["courses"])
    blank = result["courses"][-1]
    assert blank["raw_cells"]["completion_date"] == blank["raw_cells"]["final_result"] == ""
    assert "result_and_completion_status_require_confirmation" in blank["review_issues"]
    assert "enrollment_status" not in blank


def test_every_academic_record_has_locatable_evidence_and_stable_ids():
    result = parse_psr(FIXTURES / "synthetic_psr.pdf")
    assert result["source"]["sha256"] == hashlib.sha256((FIXTURES / "synthetic_psr.pdf").read_bytes()).hexdigest()
    records = result["courses"] + result["assessments"]
    assert len({r["record_id"] for r in records}) == len(records)
    for record in records:
        ev = record["evidence"]
        assert ev["document_id"] == result["source"]["document_id"]
        assert ev["page"] > 0 and ev["row"] > 0 and ev["table"] > 0
        x0,y0,x1,y1 = ev["bbox"]
        assert x0 < x1 and y0 < y1
    assert parse_psr(FIXTURES / "synthetic_psr.pdf") == result


@pytest.mark.parametrize("file,code", [("synthetic_transcript.pdf", "psr_title_missing"),
    ("synthetic_scan.pdf", "psr_no_text_layer"),
    ("synthetic_unsupported_columns.pdf", "psr_course_columns_unsupported")])
def test_unsupported_documents_stop(file, code):
    with pytest.raises(PSRError, match=code):
        parse_psr(FIXTURES / file)


@pytest.mark.parametrize("option,code", [("orphan", "psr_course_context_missing"),
                                      ("unknown_row", "psr_unrecognized_course_row")])
def test_ambiguous_or_unrecognized_rows_cannot_be_silently_dropped(tmp_path, option, code):
    path = tmp_path / "invented.pdf"
    write_fixture(path, **{option:True})
    with pytest.raises(PSRError, match=code):
        parse_psr(path)


def test_invalid_percent_is_preserved_and_requires_review(tmp_path):
    path = tmp_path / "invented.pdf"
    write_fixture(path, nonnumeric=True)
    record = parse_psr(path)["courses"][1]
    assert record["raw_cells"]["school_percent"] == "NaN"
    assert "school_percent_out_of_range" in record["review_issues"]


def test_repeated_course_codes_keep_both_attempts_and_distinct_evidence(tmp_path):
    path = tmp_path / "repeat.pdf"
    write_fixture(path, repeated=True)
    records = [r for r in parse_psr(path)["courses"] if r["raw_cells"]["course_code"] == "MSPLT10---"]
    assert len(records) == 2
    assert {r["raw_cells"]["school_percent"] for r in records} == {"78", "87"}
    assert len({r["record_id"] for r in records}) == 2


def test_missing_corrupt_and_encrypted_inputs_are_safe(tmp_path):
    with pytest.raises(PSRError, match="psr_pdf_required"):
        parse_psr(tmp_path / "missing.pdf")
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-broken")
    with pytest.raises(PSRError, match="psr_unreadable_or_encrypted"):
        parse_psr(path)
    from reportlab.pdfgen import canvas
    encrypted = tmp_path / "encrypted.pdf"
    c = canvas.Canvas(str(encrypted), encrypt="synthetic-password")
    c.drawString(50,700,"PERMANENT STUDENT RECORD")
    c.save()
    with pytest.raises(PSRError, match="psr_unreadable_or_encrypted"):
        parse_psr(encrypted)


def test_cli_does_not_overwrite_private_output_and_errors_do_not_echo_data(tmp_path, capsys):
    target = tmp_path / "profile.json"
    args = ["parse-psr", str(FIXTURES / "synthetic_psr.pdf"), "--output", str(target)]
    assert main(args) == 0
    original = target.read_bytes()
    assert main(args) == 2
    assert target.read_bytes() == original
    output = capsys.readouterr().out
    assert "Synthetic Cedar" not in output
    assert "output_unwritable_or_already_exists" in output
