"""The Household Task List — the family's own "someone needs to do this" pile.

Holds the design rules: claiming is volunteering (never assignment or a lock),
completion credits exactly once and flows into the resolved record, and letting
a task go is a release, never a logged win.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from exhale.api import app
from exhale.reflection import build_weekly_reflection
from exhale.tasks import (
    MAX_OPEN_TASKS,
    add_task,
    claim_task,
    complete_task,
    drop_task,
    open_tasks,
)

client = TestClient(app)


# --- the pile ---------------------------------------------------------------------
def test_add_claim_complete_flow():
    items, task = add_task([], "Mow the lawn", created_by="Andy")
    items = claim_task(items, task["id"], who="Ali")
    assert items[0]["claimed_by"] == "Ali"
    items, done = complete_task(items, task["id"], who="Ali")
    assert done["status"] == "done" and done["completed_by"] == "Ali"
    assert open_tasks(items) == []  # done tasks leave the open pile


def test_reclaiming_is_allowed_plans_change():
    items, task = add_task([], "Call the plumber", created_by="Andy")
    items = claim_task(items, task["id"], who="Andy")
    items = claim_task(items, task["id"], who="Ali")  # a signal, not a lock
    assert items[0]["claimed_by"] == "Ali"


def test_anyone_can_complete_even_unclaimed():
    items, task = add_task([], "Run to the dump", created_by="Ali")
    items, done = complete_task(items, task["id"], who="Andy")
    assert done["completed_by"] == "Andy"


def test_double_complete_refused():
    items, task = add_task([], "Fix the gate", created_by="Andy")
    items, _ = complete_task(items, task["id"], who="Andy")
    with pytest.raises(ValueError):
        complete_task(items, task["id"], who="Ali")


def test_empty_description_refused():
    with pytest.raises(ValueError):
        add_task([], "   ", created_by="Andy")


def test_open_pile_is_capped():
    items = []
    for i in range(MAX_OPEN_TASKS):
        items, _ = add_task(items, f"task {i}", created_by="Andy")
    with pytest.raises(ValueError):
        add_task(items, "one too many", created_by="Andy")


def test_drop_removes_without_ceremony():
    items, task = add_task([], "Repaint the fence someday", created_by="Andy")
    items = drop_task(items, task["id"])
    assert items == []


def test_open_tasks_oldest_first():
    items, first = add_task([], "First chore", created_by="Andy")
    items[0]["created_at"] = (datetime.now() - timedelta(days=2)).isoformat()
    items, second = add_task(items, "Second chore", created_by="Ali")
    assert [t["id"] for t in open_tasks(items)] == [first["id"], second["id"]]


# --- API + the celebration path ---------------------------------------------------
def test_completed_task_flows_into_handled_and_reflection():
    fam = "fam_tasks_flow"
    task = client.post(f"/v1/families/{fam}/tasks",
                       json={"description": "Mow the lawn"}).json()
    r = client.post(f"/v1/families/{fam}/tasks/{task['id']}/complete")
    assert r.status_code == 200

    # Handled recap (Today's closing note) carries the win...
    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 1
    assert "Mow the lawn" in handled["items"][0]["brief_description"]
    assert handled["items"][0]["resolved_type"] == "task"


def test_completed_task_lands_in_the_weekly_reflection():
    profile = {"resolved_log": [{
        "item_id": "task_x", "resolved_type": "task",
        "brief_description": "Run to the dump — done by Andy",
        "resolved_at": datetime.now().isoformat(),
    }]}
    carried = build_weekly_reflection(profile, None)["carried"]
    assert carried["count"] == 1
    assert "Run to the dump" in carried["items"][0]["text"]
    assert carried["items"][0]["kind"] == "task"


def test_double_complete_never_double_credits_via_api():
    fam = "fam_tasks_dupe"
    task = client.post(f"/v1/families/{fam}/tasks",
                       json={"description": "Fix the gate"}).json()
    assert client.post(f"/v1/families/{fam}/tasks/{task['id']}/complete").status_code == 200
    assert client.post(f"/v1/families/{fam}/tasks/{task['id']}/complete").status_code == 409
    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 1  # credited exactly once


def test_dropped_task_is_not_celebrated():
    fam = "fam_tasks_drop"
    task = client.post(f"/v1/families/{fam}/tasks",
                       json={"description": "Repaint the fence someday"}).json()
    assert client.delete(f"/v1/families/{fam}/tasks/{task['id']}").status_code == 200
    assert client.get(f"/v1/families/{fam}/tasks").json()["open"] == []
    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 0  # letting go is a release, not a win


def test_tasks_endpoint_lists_open_pile():
    fam = "fam_tasks_list"
    client.post(f"/v1/families/{fam}/tasks", json={"description": "Call the plumber"})
    client.post(f"/v1/families/{fam}/tasks", json={"description": "Mow the lawn"})
    pile = client.get(f"/v1/families/{fam}/tasks").json()["open"]
    assert [t["description"] for t in pile] == ["Call the plumber", "Mow the lawn"]
