"""Page data gates and persistent safe transitions; no browser actions."""
from __future__ import annotations

from .profile import ProfileError, _event, check_sources, identifier, review_requirements

FORBIDDEN_ACTIONS = {"submit", "submit_application", "submit_essay", "send_invitation", "invite",
                     "sign", "declaration", "attest", "pay", "payment", "write_essay", "answer_subjective"}
TRANSITIONS = {"collecting": {"data_ready","blocked"}, "blocked": {"collecting"},
               "data_ready": {"collecting","blocked"}}


def transaction_active(checkpoint: dict) -> bool:
    return checkpoint.get("state") in {"prepared", "saved_unverified", "needs_restore"} or (
        checkpoint.get("state") == "verified" and (checkpoint.get("context", {}).get("real_account_test") or checkpoint.get("context", {}).get('restore_after_test'))
        and checkpoint.get("journal") is not None)


def page_requirements(profile: dict, *, fact_ids: list[str], course_ids: list[str] | None = None,
                      manual_fields: list[str] | None = None, record_columns: dict[str,list[str]] | None = None) -> dict:
    courses = {c["record_id"] for c in profile["academic"]["courses"]}
    required_courses = set(course_ids or [])
    supplemental_courses = {f.split(".")[1] for f in fact_ids if f.startswith("schedules.")}
    required_courses.update(supplemental_courses)
    if any(course_id not in courses for course_id in required_courses):
        raise ProfileError("required_course_reference_missing")
    missing = [f for f in fact_ids if f not in profile["facts"]]
    conflicted = sorted({c["field_id"] for c in profile["conflicts"].values()
                         if c["status"] == "unresolved" and c["field_id"] in fact_ids})
    from .profile import RAW_BINDABLE_COLUMNS
    columns = record_columns or {}
    if any(record_id not in required_courses or not selected or not set(selected) <= RAW_BINDABLE_COLUMNS
           for record_id,selected in columns.items()):
        raise ProfileError("required_original_course_columns_invalid")
    def relevant_review(course_id,issue,has_statement):
        original_values_only = course_id not in supplemental_courses and course_id in columns
        # A clear original course name does not become ambiguous because that
        # row has no final result yet. This permits name-only PSR references;
        # status/term answers still need explicit facts, and any requested grade
        # column keeps the original missing-result review in force.
        if (original_values_only and issue=='result_and_completion_status_require_confirmation'
                and set(columns[course_id])=={'description'}):
            return False
        return not (original_values_only and (issue == "course_schedule_not_recorded_in_psr" or
            (issue == "equivalency_marker_requires_explanation" and has_statement)))
    reviews = []
    for course_id in required_courses:
        for review in review_requirements(profile,course_id):
            if relevant_review(course_id,review["issue"],not review["student_clarification_required"]):
                reviews.append(review)
    source_issues = check_sources(profile)
    # Only required facts/courses and the mandatory PSR gate affect the page.
    required_source_ids = {profile["psr_source_id"]}
    for f in fact_ids:
        if f in profile["facts"]:
            required_source_ids.update(profile["facts"][f]["source_refs"])
    for course_id in required_courses:
        for review in profile["reviews"].values():
            if (review["record_id"] == course_id and review["document_evidence"] and
                    relevant_review(course_id,review["issue"],review["clarification_source_id"] is not None)):
                required_source_ids.add(review["document_evidence"]["source_id"])
    relevant = [s for s in source_issues if s["source_id"] in required_source_ids]
    manual = list(manual_fields or [])
    return {"data_ready": not (missing or conflicted or reviews or relevant or manual),
            "missing_fact_ids": missing, "conflicted_fact_ids": conflicted, "academic_reviews": reviews,
            "source_issues": relevant, "manual_fields_remaining": manual,
            "browser_permission_verified": False, "ready_to_fill": False}


def create_checkpoint(profile: dict, target_id: str, page_key: str, *, fact_ids: list[str],
                      course_ids: list[str] | None = None, manual_fields: list[str] | None = None,
                      record_columns: dict[str,list[str]] | None = None,instance_key: str | None = None) -> str:
    if target_id not in profile["targets"] or not page_key.strip():
        raise ProfileError("observed_target_and_page_required")
    for checkpoint_id, checkpoint in profile["checkpoints"].items():
        if checkpoint["target_id"] == target_id and checkpoint["page_key"] == page_key and checkpoint.get('instance_key')==instance_key:
            if transaction_active(checkpoint):
                raise ProfileError("pending_transaction_requires_recovery")
            signature = (list(fact_ids),list(course_ids or []),list(manual_fields or []),record_columns or {})
            if signature != (checkpoint["required_fact_ids"],checkpoint["required_course_ids"],checkpoint["manual_fields_remaining"],checkpoint.get("required_record_columns",{})):
                checkpoint["required_fact_ids"],checkpoint["required_course_ids"],checkpoint["manual_fields_remaining"],checkpoint["required_record_columns"] = signature
                checkpoint["state"] = "collecting"
                _event(profile,"page_requirements_changed",[checkpoint_id])
            return checkpoint_id
    checkpoint_id = identifier("checkpoint")
    profile["checkpoints"][checkpoint_id] = {"checkpoint_id": checkpoint_id, "target_id": target_id,
        "page_key": page_key, "state": "collecting", "required_fact_ids": list(fact_ids),
        "required_course_ids": list(course_ids or []), "manual_fields_remaining": list(manual_fields or []),
        "required_record_columns":record_columns or {}}
    if instance_key is not None:profile['checkpoints'][checkpoint_id]['instance_key']=instance_key
    _event(profile, "page_checkpoint_created", [checkpoint_id, target_id])
    return checkpoint_id


def checkpoint_readiness(profile: dict, checkpoint_id: str) -> dict:
    cp = profile["checkpoints"].get(checkpoint_id)
    if not cp:
        raise ProfileError("checkpoint_reference_missing")
    return page_requirements(profile, fact_ids=cp["required_fact_ids"], course_ids=cp["required_course_ids"],
                             manual_fields=cp["manual_fields_remaining"],record_columns=cp.get("required_record_columns"))


def transition(profile: dict, checkpoint_id: str, state: str) -> None:
    cp = profile["checkpoints"].get(checkpoint_id)
    if not cp or state not in TRANSITIONS.get(cp["state"], set()):
        raise ProfileError("checkpoint_transition_unsupported")
    if state == "data_ready" and not checkpoint_readiness(profile, checkpoint_id)["data_ready"]:
        raise ProfileError("page_required_data_incomplete")
    cp["state"] = state
    _event(profile, "page_checkpoint_transition", [checkpoint_id, state])


def require_permitted_action(action: str) -> None:
    if action in FORBIDDEN_ACTIONS or action not in {"inspect", "collect_facts", "plan_factual_page", "save_profile"}:
        raise ProfileError("action_not_available_in_m2")
