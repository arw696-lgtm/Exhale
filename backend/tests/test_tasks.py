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
    done_this_week,
    drop_task,
    open_tasks,
    week_key,
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


# --- weekly contributions ---------------------------------------------------------
def test_weekly_contribution_returns_next_week():
    items, task = add_task([], "Clean the house", created_by="Andy", cadence="weekly")
    this_week = datetime(2026, 7, 22, 10, 0)   # a Wednesday
    next_week = this_week + timedelta(days=7)

    items, done = complete_task(items, task["id"], who="Ali", now=this_week)
    assert done["last_completed_by"] == "Ali"
    # Covered: out of the pile this week, quietly credited...
    assert open_tasks(items, now=this_week) == []
    assert [t["id"] for t in done_this_week(items, now=this_week)] == [task["id"]]
    # ...and back on the pile when the week turns — no re-adding.
    assert [t["id"] for t in open_tasks(items, now=next_week)] == [task["id"]]


def test_weekly_double_complete_same_week_refused():
    items, task = add_task([], "Vacuum", created_by="Andy", cadence="weekly")
    now = datetime(2026, 7, 22, 10, 0)
    items, _ = complete_task(items, task["id"], who="Andy", now=now)
    with pytest.raises(ValueError):
        complete_task(items, task["id"], who="Ali", now=now + timedelta(days=2))


def test_weekly_next_week_completion_is_a_fresh_win():
    items, task = add_task([], "Vacuum", created_by="Andy", cadence="weekly")
    w1 = datetime(2026, 7, 22, 10, 0)
    w2 = w1 + timedelta(days=7)
    items, _ = complete_task(items, task["id"], who="Andy", now=w1)
    items, done = complete_task(items, task["id"], who="Ali", now=w2)  # no error
    assert done["last_completed_by"] == "Ali"
    assert done["last_completed_week"] == week_key(w2)


def test_weekly_completion_clears_the_claim():
    # Next week starts fresh: last week's volunteer isn't silently on the hook.
    items, task = add_task([], "Clean the house", created_by="Andy", cadence="weekly")
    items = claim_task(items, task["id"], who="Ali")
    items, done = complete_task(items, task["id"], who="Ali")
    assert done["claimed_by"] is None


def test_bad_cadence_refused():
    with pytest.raises(ValueError):
        add_task([], "Daily thing", created_by="Andy", cadence="daily")


def test_weekly_credit_is_per_week_via_api():
    fam = "fam_weekly_credit"
    task = client.post(f"/v1/families/{fam}/tasks",
                       json={"description": "Clean the house",
                             "cadence": "weekly"}).json()
    r = client.post(f"/v1/families/{fam}/tasks/{task['id']}/complete")
    assert r.json()["status"] == "covered_this_week"
    # Same week, second tap → refused, credit stays single.
    assert client.post(f"/v1/families/{fam}/tasks/{task['id']}/complete").status_code == 409

    handled = client.get(f"/v1/families/{fam}/briefing").json()["handled"]
    assert handled["count"] == 1
    assert "contribution this week" in handled["items"][0]["brief_description"]

    pile = client.get(f"/v1/families/{fam}/tasks").json()
    assert pile["open"] == []                       # covered — out of the pile
    assert len(pile["covered_this_week"]) == 1      # shown as quiet credit


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


# --- concurrency: simultaneous writers must never lose an edit --------------------
def test_concurrent_adds_lose_nothing():
    """Two members adding tasks in the same instant — every add survives.

    Exercises the per-family lock around the read-modify-write pattern; without
    it, racing threads clobber each other's list and adds vanish.
    """

    import threading

    fam = "fam_tasks_race"
    N = 25

    def hammer(prefix):
        for i in range(N):
            client.post(f"/v1/families/{fam}/tasks",
                        json={"description": f"{prefix} {i}"})

    threads = [threading.Thread(target=hammer, args=(who,))
               for who in ("andy", "ali")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    pile = client.get(f"/v1/families/{fam}/tasks").json()["open"]
    assert len(pile) == 2 * N  # nothing lost to the race
