from dataclasses import asdict

import pytest

from bc_application.planning import PlannerUnavailable, ProfileRef, UnconfiguredPlanningProvider


def test_future_planner_is_explicitly_unavailable_and_has_no_duplicate_profile():
    provider = UnconfiguredPlanningProvider()
    reference = ProfileRef("synthetic-profile", 1)
    assert set(asdict(reference)) == {"profile_id", "revision"}
    assert not provider.capabilities()
    with pytest.raises(PlannerUnavailable):
        provider.read_items(reference, ("synthetic-target",))
    with pytest.raises(PlannerUnavailable):
        provider.propose_progress_sync(reference, ())
