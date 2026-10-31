"""Conservative parser for text-layer, ruled MyEducation BC PSR tables.

Raw cells are the authoritative values. Header/context records are stored once
and referenced by courses. This module makes no browser calls or academic guesses.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

HEADERS = ("COURSE CODE", "COURSE DESCRIPTION", "COMP DATE", "PROV EXAM DATE", "SCHOOL LG",
           "SCHOOL %", "PROV EXAM", "FINAL", "EQU", "CREDIT")
FIELDS = ("course_code", "course_description", "completion_date", "provincial_exam_date",
          "school_grade_symbol", "school_percent", "provincial_exam_result", "final_result",
          "equivalency_marker", "credits")
COURSE_CODE = re.compile(r"[MA][A-Z0-9-]{2,18}\d[A-Z0-9-]*\Z")
MINCODE = re.compile(r"\d{7,8}\Z")


class PSRError(ValueError):
    """Public error codes intentionally omit paths and private PDF text."""


def compact(text: str | None) -> str:
    return " ".join((text or "").split())


def _evidence(document_id: str, page: int, table: int, row: int, bbox: tuple) -> dict:
    return {"document_id": document_id, "page": page, "table": table, "row": row,
            "bbox": [round(v, 3) for v in bbox], "coordinate_system": "pdf_points_top_origin"}


def _row_bbox(row) -> tuple:
    cells = [c for c in row.cells if c is not None]
    return (min(c[0] for c in cells), min(c[1] for c in cells),
            max(c[2] for c in cells), max(c[3] for c in cells))


def _column_edges(table) -> tuple:
    # A continuation must use the same explicit grid geometry as the observed header.
    return tuple(round(c.bbox[0], 2) for c in table.columns) + (round(table.bbox[2], 2),)


def parse_psr(path: Path) -> dict:
    try:
        return _parse_psr(path)
    except PSRError:
        raise
    except Exception as exc:
        raise PSRError("psr_parse_failed") from exc


def _parse_psr(path: Path) -> dict:
    if path.suffix.lower() != ".pdf" or not path.is_file():
        raise PSRError("psr_pdf_required")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PSRError("psr_unreadable") from exc
    if not data.startswith(b"%PDF-") or len(data) > 25 * 1024 * 1024:
        raise PSRError("psr_invalid_or_too_large")
    try:
        import pdfplumber
    except ImportError as exc:
        raise PSRError("pdf_runtime_not_installed") from exc
    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        raise PSRError("psr_unreadable_or_encrypted") from exc
    digest = hashlib.sha256(data).hexdigest()
    result = {
        "schema_version": "psr-extraction/1",
        "source": {"document_id": digest, "sha256": digest, "path": str(path.resolve()),
                   "kind": "bc_psr", "layout": "myeducation-bc-ruled-v1", "page_count": len(pdf.pages)},
        "column_definitions": {"course": dict(zip(FIELDS, HEADERS)),
            "scales": {"school_percent": "percent_as_labeled", "school_grade_symbol": "original_school_symbol",
                       "final_result": "not_explicitly_labeled", "provincial_exam_result": "not_explicitly_labeled"}},
        "schools": [], "contexts": [], "courses": [], "assessments": [],
        "verification": "extracted_unreviewed", "review_requirements": [],
    }
    context_id: str | None = None
    known_columns: tuple | None = None
    schools: dict[str, dict] = {}
    with pdf:
        if not 1 <= len(pdf.pages) <= 30:
            raise PSRError("psr_page_limit")
        for page_no, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise PSRError("psr_no_text_layer")
            if "PERMANENT STUDENT RECORD" not in text.upper():
                raise PSRError("psr_title_missing")
            tables = page.find_tables()
            if not tables:
                raise PSRError("psr_unsupported_layout")
            page_seen: Counter[str] = Counter()
            for table_no, table in enumerate(tables, 1):
                rows = table.extract()
                # School enrollment table: preserve raw entry/exit grades and dates.
                if any(compact(r[0]) == "RECORD OF SCHOOLING" for r in rows):
                    if (len(table.columns) != 7
                            or not any(compact(r[0]) == "MINCODE" and compact(r[1]) == "DISTRICT-SCHOOL NAME" for r in rows)
                            or not any(compact(r[3]) == "ADMIT DATE" for r in rows)
                            or not any(compact(r[5]) == "WDR DATE" for r in rows)):
                        raise PSRError("psr_enrollment_columns_unsupported")
                    for row_no, row in enumerate(rows, 1):
                        if len(row) == 7 and MINCODE.fullmatch(compact(row[0])):
                            school_id = compact(row[0])
                            school = schools.setdefault(school_id, {"school_id": school_id,
                                "mincode_raw": row[0], "district_school_name_raw": row[1], "enrollments": [],
                                "verification": "extracted_unreviewed"})
                            school["enrollments"].append({"raw_cells": dict(zip(
                                ("mincode", "district_school_name", "entry_grade", "admit_date", "exit_grade", "withdrawal_date", "reason"), row)),
                                "evidence": _evidence(digest, page_no, table_no, row_no, _row_bbox(table.rows[row_no-1])),
                                "verification": "extracted_unreviewed"})
                    continue
                # Provincial graduation assessments are not AP exams or courses.
                if len(table.columns) == 5 and any(compact(r[0]) == "GRADUATION ASSESSMENTS" for r in rows):
                    if not any(tuple(compact(c) for c in r) ==
                               ("CODE", "ASSESSMENT NAME", "ASSESSMENT DATE", "PROFICIENCY", "Sp Case") for r in rows):
                        raise PSRError("psr_assessment_columns_unsupported")
                    for row_no, row in enumerate(rows, 1):
                        if row[0] and re.fullmatch(r"[A-Z]{2,8}\d{1,2}", compact(row[0])):
                            result["assessments"].append({"record_id": f"{digest[:16]}:a:{page_no}:{table_no}:{row_no}",
                                "raw_cells": dict(zip(("code", "name", "date", "proficiency", "special_case"), row)),
                                "evidence": _evidence(digest, page_no, table_no, row_no, _row_bbox(table.rows[row_no-1])),
                                "verification": "extracted_unreviewed"})
                    continue
                if len(table.columns) != 10:
                    if any("COURSE CODE" in compact(" ".join(c or "" for c in r)) for r in rows):
                        raise PSRError("psr_course_columns_unsupported")
                    continue
                edges = _column_edges(table)
                for row_no, row in enumerate(rows, 1):
                    values = tuple(compact(c) for c in row)
                    evidence = _evidence(digest, page_no, table_no, row_no, _row_bbox(table.rows[row_no-1]))
                    if values[0] == "COURSE CODE":
                        if values != HEADERS:
                            raise PSRError("psr_course_columns_unsupported")
                        known_columns = edges
                        continue
                    if MINCODE.fullmatch(values[0]):
                        if known_columns is None or any(abs(a-b) > 2 for a,b in zip(edges, known_columns)):
                            raise PSRError("psr_unmatched_continuation_grid")
                        if not re.fullmatch(r"\d{4}", values[2]) or not values[1]:
                            raise PSRError("psr_school_context_ambiguous")
                        school_id = values[0]
                        school = schools.setdefault(school_id, {"school_id": school_id,
                            "mincode_raw": row[0], "district_school_name_raw": row[1], "enrollments": [],
                            "verification": "extracted_unreviewed"})
                        if compact(school["district_school_name_raw"]) != values[1]:
                            raise PSRError("psr_conflicting_school_label")
                        context_id = f"{digest[:16]}:c:{page_no}:{table_no}:{row_no}"
                        result["contexts"].append({"context_id": context_id, "school_id": school_id,
                            "school_year_raw": row[2], "student_grade_raw": row[4], "days_absent_raw": row[9],
                            "evidence": evidence, "verification": "extracted_unreviewed"})
                        continue
                    if COURSE_CODE.fullmatch(values[0]):
                        if known_columns is None or context_id is None:
                            raise PSRError("psr_course_context_missing")
                        if any(abs(a-b) > 2 for a,b in zip(edges, known_columns)):
                            raise PSRError("psr_unmatched_continuation_grid")
                        record_id = f"{digest[:16]}:r:{page_no}:{table_no}:{row_no}"
                        issues = []
                        if not values[1]:
                            issues.append("course_description_missing")
                        if values[8]:
                            issues.append("equivalency_marker_requires_explanation")
                        if not any(values[index] for index in (4,5,6,7)):
                            issues.append("result_and_completion_status_require_confirmation")
                        if values[5]:
                            try:
                                percent = float(values[5])
                                if not 0 <= percent <= 100:
                                    issues.append("school_percent_out_of_range")
                            except ValueError:
                                issues.append("school_percent_not_numeric")
                        result["courses"].append({"record_id": record_id, "context_id": context_id,
                            "raw_cells": dict(zip(FIELDS, row)), "duration": None, "semester": None,
                            "start_date": None, "evidence": evidence, "verification": "extracted_unreviewed",
                            "review_issues": issues})
                        if issues:
                            result["review_requirements"].append({"record_id": record_id, "issues": issues,
                                "required_evidence": ["transcript_or_report_card", "student_clarification"],
                                "oral_clarification_allowed": True})
                        page_seen[values[0]] += 1
                        continue
                    if values[0] and values[0] not in {"ACHIEVEMENT/ATTENDANCE", "MINCODE"}:
                        raise PSRError("psr_unrecognized_course_row")
            # Fail closed if a course-like code in the page's academic region was
            # not captured. Never quietly drop a malformed or detached course row.
            in_courses = False
            text_seen: Counter[str] = Counter()
            for line in text.splitlines():
                if compact(line).startswith("ACHIEVEMENT/ATTENDANCE"):
                    in_courses = True
                if compact(line).startswith("GRADUATION ASSESSMENTS"):
                    in_courses = False
                if in_courses:
                    first = line.split()[0] if line.split() else ""
                    if COURSE_CODE.fullmatch(first):
                        text_seen[first] += 1
            if text_seen != page_seen:
                raise PSRError("psr_course_row_not_captured")
        if not result["courses"] or known_columns is None:
            raise PSRError("psr_no_supported_course_table")
    result["schools"] = list(schools.values())
    return result
