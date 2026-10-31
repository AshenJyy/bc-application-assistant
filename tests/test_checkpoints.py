from pathlib import Path

import pytest

from bc_application.checkpoints import (checkpoint_readiness,create_checkpoint,page_requirements,
                                        require_permitted_action,transition)
from bc_application.profile import (ProfileError,add_statement,add_target,create_profile,set_fact)

FIXTURE = Path(__file__).parent/"fixtures/synthetic_psr.pdf"


def test_page_gate_is_local_and_survives_resume():
    profile = create_profile(FIXTURE)
    statement = add_statement(profile,"Synthetic student selects UC and gives their first name.")
    set_fact(profile,"personal.legal_given_name","Synthetic",statement)
    target = add_target(profile,system="uc",school="Synthetic UC campus",program=None,source_id=statement)
    ready = create_checkpoint(profile,target,"personal",fact_ids=["personal.legal_given_name"])
    missing = create_checkpoint(profile,target,"family",fact_ids=["family.parent_name"])
    assert checkpoint_readiness(profile,ready)["data_ready"]
    assert not checkpoint_readiness(profile,missing)["data_ready"]
    transition(profile,ready,"data_ready")
    assert not checkpoint_readiness(profile,ready)["ready_to_fill"]
    assert profile["checkpoints"][ready]["state"] == "data_ready"
    with pytest.raises(ProfileError,match="incomplete"):
        transition(profile,missing,"data_ready")


def test_manual_essays_and_conflicts_block_only_the_affected_page():
    profile = create_profile(FIXTURE)
    a,b = add_statement(profile,"Synthetic name A."),add_statement(profile,"Synthetic name B.")
    set_fact(profile,"personal.name","A",a)
    set_fact(profile,"personal.name","B",b)
    assert page_requirements(profile,fact_ids=["personal.name"])["conflicted_fact_ids"] == ["personal.name"]
    assert not page_requirements(profile,fact_ids=[],manual_fields=["required essay"])["data_ready"]


def test_new_conditional_field_reopens_saved_data_checkpoint():
    profile = create_profile(FIXTURE)
    s = add_statement(profile,"Synthetic target selection.")
    target = add_target(profile,system="mit",school="MIT",program=None,source_id=s)
    cp = create_checkpoint(profile,target,"general",fact_ids=[])
    transition(profile,cp,"data_ready")
    assert create_checkpoint(profile,target,"general",fact_ids=["personal.new_required_field"]) == cp
    assert profile["checkpoints"][cp]["state"] == "collecting"
    assert not checkpoint_readiness(profile,cp)["data_ready"]


def test_oral_course_schedule_requires_transcript_before_page_can_be_ready():
    from bc_application.profile import set_course_schedule
    profile = create_profile(FIXTURE)
    record = profile["academic"]["courses"][0]
    s = add_statement(profile,"This synthetic course lasted a semester.",scope=[record["record_id"]])
    set_course_schedule(profile,record["record_id"],duration="semester",source_id=s)
    field = f"schedules.{record['record_id']}.duration"
    readiness = page_requirements(profile,fact_ids=[field])
    assert not readiness["data_ready"]
    assert readiness["academic_reviews"][0]["transcript_or_report_card_review_required"]


@pytest.mark.parametrize("action",["submit","submit_application","send_invitation","attest","pay","write_essay","fill_browser"])
def test_forbidden_or_not_yet_implemented_actions_are_rejected(action):
    with pytest.raises(ProfileError,match="not_available"):
        require_permitted_action(action)
