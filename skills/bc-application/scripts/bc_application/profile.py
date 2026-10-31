"""Canonical applicant data, provenance and explicit student statements.

No browser, provider API, automatic subjective answer or academic inference lives here.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = "applicant-profile/1"
FACT_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_:-]+)+\Z")
FORBIDDEN_FACT_PARTS = {"password", "otp", "cookie", "cookies", "token", "cvv", "payment_card",
                        "essay", "signature", "declaration", "subjective"}
SYSTEMS = {"uc", "mit", "common_app", "web"}


class ProfileError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def academic_digest(academic: dict) -> str:
    return hashlib.sha256(json.dumps(academic, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def from_extraction(extraction: dict) -> dict:
    if extraction.get("schema_version") != "psr-extraction/1" or not extraction.get("courses"):
        raise ProfileError("supported_psr_extraction_required")
    raw = copy.deepcopy(extraction)
    document = raw.pop("source")
    if document.get("kind") != "bc_psr":
        raise ProfileError("bc_psr_required")
    raw.pop("schema_version")
    raw.pop("verification", None)
    raw.pop("review_requirements", None)
    result = {"schema_version": SCHEMA_VERSION, "profile_id": identifier("applicant"), "revision": 0,
              "created_at": now(), "updated_at": now(), "application_cycle": "2027-fall",
              "psr_source_id": document["document_id"], "sources": {document["document_id"]: document},
              "academic": raw, "academic_sha256": academic_digest(raw), "facts": {}, "exams": {}, "marker_explanations": {},
              "reviews": {}, "conflicts": {}, "targets": {}, "checkpoints": {}, "events": []}
    for course in raw["courses"]:
        for issue in course["review_issues"]:
            review_id = f"{course['record_id']}:{issue}"
            result["reviews"][review_id] = {"record_id": course["record_id"], "issue": issue,
                "clarification_source_id": None, "document_evidence": None, "status": "unresolved"}
    validate_profile(result)
    return result


def create_profile(psr: Path) -> dict:
    from .psr import parse_psr
    return from_extraction(parse_psr(psr))


def _event(profile: dict, kind: str, refs: list[str]) -> None:
    # IDs and transitions only; don't make a second history copy of personal values.
    profile["events"].append({"id": identifier("event"), "kind": kind, "refs": refs, "at": now()})


def add_statement(profile: dict, text: str, *, origin: str = "student", scope: list[str] | None = None) -> str:
    if not isinstance(text, str) or not text.strip() or origin not in {"student", "previous_chat_confirmed"}:
        raise ProfileError("explicit_student_statement_required")
    scope = scope or []
    signature = hashlib.sha256(json.dumps([text, origin, sorted(scope)], ensure_ascii=False).encode()).hexdigest()
    source_id = f"statement:{signature}"
    profile["sources"].setdefault(source_id, {"kind": "student_statement", "text": text,
        "origin": origin, "scope": list(scope), "verification": "student_reported", "recorded_at": now()})
    return source_id


def validate_exam_release_schedule(source_id: str, source: dict) -> str:
    """A public schedule is evidence of a general opening date, not a student's score."""
    from datetime import date
    from urllib.parse import urlsplit
    fields = {"kind", "exam_system", "year", "release_date", "url", "title", "excerpt", "observation_method"}
    try:
        payload = {k: source[k] for k in fields}
        parsed = urlsplit(source['url'])
        released = date.fromisoformat(source['release_date'])
        months = ('January','February','March','April','May','June','July','August','September','October','November','December')
        if (set(source) != fields | {'recorded_at'} or source['kind'] != 'public_exam_schedule'
                or source['exam_system'] != 'AP' or type(source['year']) is not int
                or not 2000 <= source['year'] <= 2100 or released.year != source['year']
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',source['release_date'])
                or parsed.scheme != 'https' or parsed.hostname not in {'apstudents.collegeboard.org','apcentral.collegeboard.org'}
                or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment
                or source['observation_method'] not in {'official_page','official_search_excerpt'}
                or not isinstance(source['title'], str) or not source['title'].strip()
                or not isinstance(source['excerpt'], str) or len(source['excerpt'].split()) > 25
                or str(source['year']) not in source['excerpt']
                or not re.search(r'\bAP\b.*\bscores?\b',source['excerpt'],re.I)
                or not re.search(r'\b'+months[released.month-1]+r'\s+0?'+str(released.day)+r'\b', source['excerpt'])
                or not isinstance(source['recorded_at'], str)):
            raise ValueError()
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if source_id != 'public-schedule:'+signature:
            raise ValueError()
        return released.isoformat()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProfileError('observed_official_exam_schedule_required') from exc


def register_exam_release_schedule(profile: dict, *, system: str, year: int, release_date: str,
                                   url: str, title: str, excerpt: str, observation_method: str) -> str:
    """Register already-observed public evidence without fetching or copying a report."""
    payload = {'kind':'public_exam_schedule', 'exam_system':system, 'year':year,
               'release_date':release_date, 'url':url, 'title':title, 'excerpt':excerpt,
               'observation_method':observation_method}
    signature = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    source_id = 'public-schedule:'+signature
    source = {**payload, 'recorded_at':now()}
    validate_exam_release_schedule(source_id, source)
    profile['sources'].setdefault(source_id, source)
    _event(profile, 'public_exam_schedule_observed', [source_id])
    return source_id


def register_document(profile: dict, path: Path, *, kind: str) -> str:
    if kind not in {"transcript", "report_card", "ap_score_report", "supporting_document"}:
        raise ProfileError("unsupported_supplement_kind")
    try:
        data = path.read_bytes()
        if not data.startswith(b"%PDF-") or len(data) > 25 * 1024 * 1024:
            raise ProfileError("supplement_pdf_required")
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            if not 1 <= page_count <= 100:
                raise ProfileError("supplement_page_limit")
    except ProfileError:
        raise
    except Exception as exc:
        raise ProfileError("supplement_unreadable_or_encrypted") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest == profile["psr_source_id"]:
        raise ProfileError("psr_does_not_replace_supplemental_transcript")
    if digest in profile["sources"]:
        if profile["sources"][digest]["kind"] != kind:
            raise ProfileError("document_kind_conflict")
        return digest
    profile["sources"][digest] = {"document_id": digest, "sha256": digest, "path": str(path.resolve()),
        "kind": kind, "page_count": page_count, "verification": "registered_unreviewed"}
    _event(profile, "supplement_registered", [digest])
    return digest


def _source(profile: dict, source_id: str) -> dict:
    try:
        return profile["sources"][source_id]
    except KeyError as exc:
        raise ProfileError("source_reference_missing") from exc


def _course(profile: dict, record_id: str) -> dict:
    for record in profile["academic"]["courses"]:
        if record["record_id"] == record_id:
            return record
    raise ProfileError("course_reference_missing")


def _fact_key(field_id: str) -> None:
    if (not isinstance(field_id, str) or not FACT_ID.fullmatch(field_id)
            or field_id.split(".")[0] in {"academic", "sources", "targets", "checkpoints"}
            or any(part in FORBIDDEN_FACT_PARTS for part in field_id.split("."))):
        raise ProfileError("factual_field_id_required")


def set_fact(profile: dict, field_id: str, value, source_id: str, *, scale: str | None = None,
             evidence: dict | None = None, kind: str = "factual") -> str | None:
    _fact_key(field_id)
    if kind != "factual":
        raise ProfileError("beta_excludes_subjective_or_essay_answers")
    source = _source(profile, source_id)
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProfileError("json_value_required") from exc
    if value is None or value == "":
        raise ProfileError("explicit_nonempty_fact_required")
    if source["kind"] == "student_statement":
        verification = "student_reported"
    else:
        if isinstance(evidence,dict) and evidence.get("method") == "visual_review":
            raise ProfileError("manual_review_does_not_establish_automatic_extraction")
        _validate_document_evidence(profile, source_id, evidence, verify_content=True)
        verification = "document_extracted"
    incoming = {"value": copy.deepcopy(value), "scale": scale, "source_refs": [source_id],
                "verification": verification, "evidence": evidence}
    existing = profile["facts"].get(field_id)
    if existing is None:
        profile["facts"][field_id] = incoming
        _event(profile, "fact_added", [field_id, source_id])
        return None
    if (existing["value"], existing["scale"]) == (value, scale):
        if source_id not in existing["source_refs"]:
            existing["source_refs"].append(source_id)
        # A new corroborating source cannot silently promote the verification status.
        return None
    for conflict_id, conflict in profile["conflicts"].items():
        if conflict["field_id"] == field_id and conflict["status"] == "unresolved":
            if conflict["candidate"] == incoming:
                return conflict_id
    conflict_id = identifier("conflict")
    profile["conflicts"][conflict_id] = {"field_id": field_id, "candidate": incoming,
        "status": "unresolved", "resolution_source_id": None}
    _event(profile, "fact_conflict_detected", [field_id, conflict_id])
    return conflict_id


def resolve_conflict(profile: dict, conflict_id: str, *, choose: str, confirmation_source_id: str) -> None:
    confirmation = _source(profile, confirmation_source_id)
    if confirmation["kind"] != "student_statement" or choose not in {"existing", "candidate"}:
        raise ProfileError("explicit_student_conflict_resolution_required")
    conflict = profile["conflicts"].get(conflict_id)
    if not conflict or conflict["status"] != "unresolved":
        raise ProfileError("unresolved_conflict_required")
    if choose == "candidate":
        old = profile["facts"][conflict["field_id"]]
        profile["facts"][conflict["field_id"]] = conflict["candidate"]
        conflict["alternative"] = old
    else:
        conflict["alternative"] = conflict["candidate"]
    del conflict["candidate"]
    profile["facts"][conflict["field_id"]]["verification"] = "student_confirmed"
    conflict["status"] = "resolved"
    conflict["selection"] = choose
    conflict["resolution_source_id"] = confirmation_source_id
    _event(profile, "fact_conflict_resolved", [conflict_id, confirmation_source_id])


def clarify_marker(profile: dict, record_ids: list[str], *, meaning: str, statement_source_id: str) -> None:
    source = _source(profile, statement_source_id)
    if source["kind"] != "student_statement" or not record_ids or not meaning.strip():
        raise ProfileError("record_scoped_student_explanation_required")
    # Validate the entire batch before changing any record.
    for record_id in record_ids:
        record = _course(profile, record_id)
        if not record["raw_cells"]["equivalency_marker"]:
            raise ProfileError("course_has_no_marker")
        if record_id not in source.get("scope", []):
            raise ProfileError("statement_does_not_cover_course")
        existing = profile["marker_explanations"].get(record_id)
        if existing and existing["meaning"] != meaning:
            raise ProfileError("marker_explanation_conflict_requires_resolution")
    for record_id in record_ids:
        profile["marker_explanations"][record_id] = {"meaning": meaning,
            "source_id": statement_source_id, "verification": "student_reported"}
        key = f"{record_id}:equivalency_marker_requires_explanation"
        profile["reviews"][key]["clarification_source_id"] = statement_source_id
    _event(profile, "marker_clarified_by_student", record_ids + [statement_source_id])


def clarify_review(profile: dict, review_id: str, statement_source_id: str) -> None:
    source = _source(profile, statement_source_id)
    review = profile["reviews"].get(review_id)
    if not review or source["kind"] != "student_statement" or review["record_id"] not in source.get("scope", []):
        raise ProfileError("record_scoped_student_explanation_required")
    review["clarification_source_id"] = statement_source_id


def _validate_document_evidence(profile: dict, source_id: str, evidence: dict | None,
                                *, verify_content: bool = False) -> None:
    source = _source(profile, source_id)
    if (source.get("kind") == "student_statement" or not isinstance(evidence, dict)
            or type(evidence.get("page")) is not int
            or not 1 <= evidence["page"] <= source.get("page_count", 0)
            or not isinstance(evidence.get("quote"), str) or not evidence["quote"].strip()):
        raise ProfileError("locatable_document_evidence_required")
    method = evidence.get("method","text_quote")
    if method not in {"text_quote","visual_review"}:
        raise ProfileError("document_evidence_method_unsupported")
    if method == "visual_review":
        if evidence.get("coordinate_system") != "pdf_points_top_origin":
            raise ProfileError("visual_review_coordinate_system_required")
        bbox = evidence.get("bbox")
        if (not isinstance(bbox,list) or len(bbox)!=4 or
                any(type(v) not in {int,float} or not math.isfinite(v) or v<0 for v in bbox) or
                not (bbox[0]<bbox[2] and bbox[1]<bbox[3])):
            raise ProfileError("visual_review_page_rectangle_required")
    if not verify_content:
        return  # Resume remains possible when an external document needs relinking.
    try:
        data = Path(source["path"]).read_bytes()
    except OSError as exc:
        raise ProfileError("evidence_document_unavailable") from exc
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ProfileError("evidence_document_changed")
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            document_page = pdf.pages[evidence["page"]-1]
            if method == "visual_review":
                if evidence["bbox"][2]>document_page.width or evidence["bbox"][3]>document_page.height:
                    raise ProfileError("visual_review_rectangle_outside_page")
                return  # Explicit manual review; never claimed as text extraction.
            extracted = document_page.extract_text() or ""
    except ProfileError:
        raise
    except Exception as exc:
        raise ProfileError("evidence_page_unreadable") from exc
    normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalize(extracted):
        raise ProfileError("evidence_text_layer_missing_manual_review_required")
    if normalize(evidence["quote"]) not in normalize(extracted):
        raise ProfileError("evidence_quote_not_found_on_page")


def review_with_document(profile: dict, review_id: str, source_id: str, *, page: int, quote: str,
                          method: str = "text_quote", bbox: list[float] | None = None) -> None:
    review = profile["reviews"].get(review_id)
    source = _source(profile, source_id)
    evidence = {"source_id": source_id, "page": page, "quote": quote}
    if method != "text_quote":
        evidence.update(method=method,bbox=bbox,coordinate_system="pdf_points_top_origin")
    if not review or source.get("kind") not in {"transcript", "report_card"}:
        raise ProfileError("transcript_or_report_card_review_required")
    _validate_document_evidence(profile, source_id, evidence, verify_content=True)
    if not review["clarification_source_id"]:
        raise ProfileError("student_clarification_still_required")
    review["document_evidence"] = evidence
    review["status"] = "resolved_with_document_and_statement"
    _event(profile, "review_evidence_recorded", [review_id, source_id])


def review_requirements(profile: dict, record_id: str | None = None) -> list[dict]:
    result = []
    for review_id, review in profile["reviews"].items():
        if record_id is not None and review["record_id"] != record_id:
            continue
        if review["status"] == "unresolved":
            result.append({"review_id": review_id, "record_id": review["record_id"], "issue": review["issue"],
                "student_clarification_required": review["clarification_source_id"] is None,
                "transcript_or_report_card_review_required": review["document_evidence"] is None})
    return result


def add_exam(profile: dict, *, name: str, system: str, score, scale: str, source_id: str,
             related_course_ids: list[str] | None = None, evidence: dict | None = None,
             date: str | None = None, date_evidence: dict | None = None) -> str:
    if not name.strip() or not system.strip() or not scale.strip():
        raise ProfileError("explicit_exam_information_required")
    if date is not None:
        validate_exam_date(date)
    for record_id in related_course_ids or []:
        _course(profile, record_id)
    # Score is explicitly supplied; an E or a school percentage never creates an exam.
    exam_id = "exam:" + hashlib.sha256(json.dumps([system,name,related_course_ids or []]).encode()).hexdigest()[:24]
    field_id = f"exams.{exam_id}.score"
    set_fact(profile, field_id, score, source_id, scale=scale, evidence=evidence)
    profile["exams"].setdefault(exam_id, {"exam_id": exam_id, "system": system, "name": name,
        "score_fact_id": field_id, "related_course_ids": list(related_course_ids or []), "date_fact_id": None})
    if date is not None:
        set_exam_date(profile,exam_id,date,source_id,evidence=date_evidence)
    return exam_id


def validate_exam_date(value: str) -> None:
    from datetime import date
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?',value):
        raise ProfileError('explicit_iso_exam_date_required')
    try:date.fromisoformat(value+'-01' if len(value)==7 else value)
    except ValueError as exc:raise ProfileError('explicit_iso_exam_date_required') from exc


def set_exam_date(profile: dict, exam_id: str, value: str, source_id: str, *, evidence: dict | None = None) -> None:
    validate_exam_date(value)
    if exam_id not in profile['exams']:raise ProfileError('exam_reference_missing')
    field_id=f'exams.{exam_id}.date'
    # Preserve supplied precision; the internal calendar validation day is never stored.
    set_fact(profile,field_id,value,source_id,evidence=evidence)
    profile['exams'][exam_id]['date_fact_id']=field_id


def set_course_schedule(profile: dict, record_id: str, *, duration: str, source_id: str,
                        term_label: str | None = None, start_date: str | None = None, end_date: str | None = None) -> None:
    _course(profile, record_id)
    if duration not in {"semester", "full_year", "trimester", "quarter", "other"}:
        raise ProfileError("explicit_course_duration_required")
    from datetime import date
    for value in (start_date, end_date):
        if value is not None:
            try:
                date.fromisoformat(value)
            except (ValueError, TypeError) as exc:
                raise ProfileError("explicit_iso_course_date_required") from exc
    if start_date and end_date and start_date > end_date:
        raise ProfileError("course_date_range_invalid")
    _source(profile, source_id)
    for key,value in {"duration": duration, "term_label":term_label,"start_date":start_date,"end_date":end_date}.items():
        if value is not None:
            set_fact(profile, f"schedules.{record_id}.{key}", value, source_id)
    review_id = f"{record_id}:course_schedule_not_recorded_in_psr"
    profile["reviews"].setdefault(review_id, {"record_id":record_id,"issue":"course_schedule_not_recorded_in_psr",
        "clarification_source_id":source_id,"document_evidence":None,"status":"unresolved"})


def add_target(profile: dict, *, system: str, school: str, program: str | None, source_id: str) -> str:
    if system not in SYSTEMS or not school.strip() or _source(profile, source_id)["kind"] != "student_statement":
        raise ProfileError("student_selected_target_required")
    target_id = "target:" + hashlib.sha256(json.dumps([system,school,program,profile["application_cycle"]]).encode()).hexdigest()[:24]
    profile["targets"].setdefault(target_id, {"target_id": target_id, "system": system, "school": school,
        "program": program, "choice_source_id": source_id, "field_bindings": {}})
    return target_id


def _page_path(page_path: str) -> None:
    if (not isinstance(page_path,str) or not re.fullmatch(r'/[A-Za-z0-9_./-]{1,299}',page_path)
            or '//' in page_path or '..' in page_path):
        raise ProfileError('observed_page_path_required')


def _binding_table(profile: dict,target_id: str,page_path: str | None) -> dict:
    target=profile['targets'][target_id]
    if page_path is None:return target['field_bindings']
    _page_path(page_path)
    return target.setdefault('page_field_bindings',{}).setdefault(page_path,{})


def bind_fact(profile: dict, target_id: str, field_key: str, fact_id: str, *, page_path: str | None = None) -> None:
    if target_id not in profile["targets"] or fact_id not in profile["facts"] or not field_key.strip():
        raise ProfileError("target_and_canonical_fact_required")
    _binding_table(profile,target_id,page_path)[field_key] = fact_id


RAW_BINDABLE_COLUMNS = {"description", "course_description", "school_percent", "school_grade_symbol", "final_result", "credits", "completion_date"}


def bind_record_column(profile: dict, target_id: str, field_key: str, record_id: str, column: str, *, page_path: str | None = None) -> None:
    _course(profile, record_id)
    if target_id not in profile["targets"] or not field_key.strip() or column not in RAW_BINDABLE_COLUMNS:
        raise ProfileError("observed_field_and_original_column_required")
    _binding_table(profile,target_id,page_path)[field_key] = f"psr:{record_id}:{column}"


def scope_bindings(profile: dict,target_id: str,page_path: str,field_keys: list[str]) -> None:
    """Move an explicitly selected legacy binding set, without duplicating facts."""
    if target_id not in profile['targets'] or not isinstance(field_keys,list) or not field_keys or len(set(field_keys))!=len(field_keys):
        raise ProfileError('explicit_legacy_binding_keys_required')
    legacy=profile['targets'][target_id]['field_bindings']
    scoped=_binding_table(profile,target_id,page_path)
    if any(key not in legacy or (key in scoped and scoped[key]!=legacy[key]) for key in field_keys):
        raise ProfileError('legacy_binding_missing_or_scope_conflict')
    for key in field_keys:scoped[key]=legacy.pop(key)
    _event(profile,'field_bindings_scoped_to_observed_page',[target_id,page_path])


def check_sources(profile: dict) -> list[dict]:
    issues = []
    for source_id, source in profile["sources"].items():
        if "path" in source:
            try:
                if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
                    issues.append({"source_id":source_id,"issue":"source_changed"})
            except OSError:
                issues.append({"source_id":source_id,"issue":"source_unavailable"})
    return issues


def relink_document(profile: dict, source_id: str, path: Path) -> None:
    source = _source(profile,source_id)
    if "sha256" not in source:
        raise ProfileError("document_source_required")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ProfileError("document_unavailable") from exc
    if digest != source["sha256"]:
        raise ProfileError("replacement_document_is_different")
    source["path"] = str(path.resolve())
    _event(profile,"document_reference_relinked",[source_id])


def validate_profile(profile: dict) -> None:
    try:
        _validate_profile(profile)
    except ProfileError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProfileError("invalid_profile_structure") from exc


def _validate_profile(profile: dict) -> None:
    required = {"schema_version", "profile_id", "revision", "created_at", "updated_at", "application_cycle",
                "psr_source_id", "sources", "academic", "academic_sha256", "facts", "exams", "marker_explanations", "reviews",
                "conflicts", "targets", "checkpoints", "events"}
    if not isinstance(profile, dict) or set(profile)-{'school_directory'} != required or profile.get("schema_version") != SCHEMA_VERSION:
        raise ProfileError("unsupported_profile_schema")
    if type(profile["revision"]) is not int or profile["revision"] < 0 or not isinstance(profile["profile_id"], str):
        raise ProfileError("invalid_profile_identity_or_revision")
    for key in ("sources","facts","exams","marker_explanations","reviews","conflicts","targets","checkpoints"):
        if not isinstance(profile[key], dict):
            raise ProfileError("invalid_profile_container")
    if not isinstance(profile["events"], list) or not isinstance(profile["academic"], dict):
        raise ProfileError("invalid_profile_container")
    if academic_digest(profile["academic"]) != profile["academic_sha256"]:
        raise ProfileError("raw_psr_data_changed")
    psr = _source(profile, profile["psr_source_id"])
    if psr.get("kind") != "bc_psr":
        raise ProfileError("bc_psr_required")
    for source_id, source in profile['sources'].items():
        if source.get('kind') == 'public_exam_schedule':
            validate_exam_release_schedule(source_id, source)
    courses = profile["academic"].get("courses", [])
    course_ids = {r["record_id"] for r in courses}
    context_ids = {r["context_id"] for r in profile["academic"].get("contexts", [])}
    school_ids = {r["school_id"] for r in profile["academic"].get("schools", [])}
    if not courses or len(course_ids) != len(courses):
        raise ProfileError("unique_academic_records_required")
    for record in courses + profile["academic"].get("assessments", []):
        if record["evidence"]["document_id"] != profile["psr_source_id"]:
            raise ProfileError("academic_source_reference_invalid")
        if "context_id" in record and record["context_id"] not in context_ids:
            raise ProfileError("academic_context_reference_invalid")
    if any(c["school_id"] not in school_ids for c in profile["academic"].get("contexts", [])):
        raise ProfileError("academic_school_reference_invalid")
    if 'school_directory' in profile:
        from .schools import validate_directory
        validate_directory(profile)
    for field_id, fact in profile["facts"].items():
        _fact_key(field_id)
        if not fact.get("source_refs") or fact.get("verification") not in {"student_reported", "student_confirmed", "document_extracted"}:
            raise ProfileError("fact_evidence_or_status_invalid")
        for source_id in fact["source_refs"]:
            _source(profile, source_id)
    for record_id, explanation in profile["marker_explanations"].items():
        if record_id not in course_ids or _source(profile, explanation["source_id"])["kind"] != "student_statement":
            raise ProfileError("marker_explanation_reference_invalid")
    for review in profile["reviews"].values():
        if review["record_id"] not in course_ids:
            raise ProfileError("review_reference_invalid")
        if review["clarification_source_id"]:
            _source(profile, review["clarification_source_id"])
        if review["document_evidence"]:
            _validate_document_evidence(profile, review["document_evidence"]["source_id"], review["document_evidence"])
    for target in profile["targets"].values():
        if target["system"] not in SYSTEMS:
            raise ProfileError("application_system_unsupported")
        _source(profile, target["choice_source_id"])
        if 'application_site' in target:
            from .browser import origin
            site=target['application_site']
            if (set(site)!={'origin','entry_url','source_id'} or origin(site['entry_url'])!=site['origin']
                    or _source(profile,site['source_id'])['kind']!='student_statement'):
                raise ProfileError('authorized_application_site_invalid')
        page_tables=target.get('page_field_bindings',{})
        if not isinstance(page_tables,dict):raise ProfileError('target_page_bindings_invalid')
        for page_path,table in page_tables.items():
            _page_path(page_path)
            if not isinstance(table,dict) or any(not isinstance(key,str) or not key for key in table):
                raise ProfileError('target_page_bindings_invalid')
        for field_id in [ref for table in [target['field_bindings'],*page_tables.values()] for ref in table.values()]:
            if field_id.startswith("psr:"):
                record_id,column = field_id[4:].rsplit(":",1)
                if record_id not in course_ids or column not in RAW_BINDABLE_COLUMNS:
                    raise ProfileError("target_raw_record_reference_invalid")
            elif field_id not in profile["facts"]:
                raise ProfileError("target_fact_reference_invalid")
    for exam in profile["exams"].values():
        if exam["score_fact_id"] not in profile["facts"] or any(r not in course_ids for r in exam["related_course_ids"]):
            raise ProfileError("exam_reference_invalid")
        if exam.get('date_fact_id') is not None:
            if exam['date_fact_id'] not in profile['facts']:raise ProfileError('exam_date_reference_invalid')
            validate_exam_date(profile['facts'][exam['date_fact_id']]['value'])
    for conflict in profile["conflicts"].values():
        if conflict["field_id"] not in profile["facts"]:
            raise ProfileError("conflict_reference_invalid")
        alternative = conflict["candidate"] if conflict["status"] == "unresolved" else conflict["alternative"]
        for source_id in alternative["source_refs"]:
            _source(profile, source_id)
    for checkpoint in profile["checkpoints"].values():
        if checkpoint["target_id"] not in profile["targets"]:
            raise ProfileError("checkpoint_target_reference_invalid")
    try:
        json.dumps(profile, allow_nan=False)
    except (ValueError,TypeError) as exc:
        raise ProfileError("profile_not_json_serializable") from exc
