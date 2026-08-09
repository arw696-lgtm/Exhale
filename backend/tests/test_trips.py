"""Tests for trip detection (travel bookings → suggested away periods)."""

from datetime import datetime, timedelta, timezone

from exhale.trips import is_travel_artifact, suggest_trips

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)


def _entry(title, days_out, *, sender=None, eid=None):
    return {
        "extraction_id": eid or f"ext_{title[:8]}_{days_out}",
        "extracted_event": title,
        "source_document_name": title,
        "source_sender": sender,
        "event_date": (NOW.date() + timedelta(days=days_out)).isoformat(),
    }


ANDY_TRIP = [
    _entry("Budget Rent A Car: Reservation Confirmation at PDX", 9,
           sender="confirmation@budget.com"),
    _entry("Your Airbnb reservation is confirmed", 9,
           sender="automated@airbnb.com"),
    _entry("Your flight confirmation - MSP to PDX", 10,
           sender="deltaairlines@delta.com"),
]


# --- classification ----------------------------------------------------------
def test_travel_artifacts_recognized_by_domain_and_wording():
    for e in ANDY_TRIP:
        assert is_travel_artifact(e), e["extracted_event"]
    assert is_travel_artifact(_entry("Hotel check-in reminder", 5))


def test_restaurant_reservation_is_not_a_trip_signal():
    """Dinner at Aubergine is a night out, not a vacation."""

    aubergine = _entry(
        "Your reservation for Restaurant Aubergine on Saturday, 6:00 PM", 12,
        sender="noreply@opentable.com")
    assert not is_travel_artifact(aubergine)


def test_school_email_is_not_travel():
    assert not is_travel_artifact(_entry("Field Trip Permission Slip", 4))


# --- clustering --------------------------------------------------------------
def test_bookings_within_days_cluster_into_one_trip():
    out = suggest_trips(ANDY_TRIP, now=NOW)
    assert len(out) == 1
    trip = out[0]
    assert trip["artifact_count"] == 3
    assert trip["start"] == (NOW.date() + timedelta(days=9)).isoformat()
    assert trip["end"] == (NOW.date() + timedelta(days=10)).isoformat()
    assert any("Airbnb" in a for a in trip["artifacts"])


def test_one_booking_alone_never_suggests():
    out = suggest_trips([ANDY_TRIP[0]], now=NOW)
    assert out == []


def test_far_apart_bookings_form_separate_clusters():
    fall = [_entry("Flight to DEN", 40, sender="ua@united.com"),
            _entry("Hotel confirmation Denver", 41)]
    out = suggest_trips(ANDY_TRIP + fall, now=NOW)
    assert len(out) == 2
    assert out[0]["start"] < out[1]["start"]


def test_past_trips_not_suggested():
    past = [_entry("Flight home", -20, sender="delta@delta.com"),
            _entry("Airbnb receipt", -19, sender="automated@airbnb.com")]
    assert suggest_trips(past, now=NOW) == []


def test_far_future_trips_wait_their_turn():
    spring = [_entry("Flight to CDG", 200, sender="delta@delta.com"),
              _entry("Paris apartment - Airbnb", 201, sender="automated@airbnb.com")]
    assert suggest_trips(spring, now=NOW) == []


# --- suggestion lifecycle ----------------------------------------------------
def test_declared_away_period_stops_the_suggestion():
    away = [{"start": (NOW.date() + timedelta(days=8)).isoformat(),
             "end": (NOW.date() + timedelta(days=12)).isoformat()}]
    assert suggest_trips(ANDY_TRIP, existing_away=away, now=NOW) == []


def test_dismissal_is_remembered_and_stable():
    first = suggest_trips(ANDY_TRIP, now=NOW)[0]
    again = suggest_trips(ANDY_TRIP, now=NOW)[0]
    assert first["trip_id"] == again["trip_id"]  # stable across renders
    assert suggest_trips(ANDY_TRIP, dismissed={first["trip_id"]}, now=NOW) == []


def test_new_artifact_changes_the_trip_id_so_it_resurfaces():
    """A dismissed 2-booking cluster that gains a flight is new information —
    it may suggest again."""

    two = ANDY_TRIP[:2]
    dismissed = {suggest_trips(two, now=NOW)[0]["trip_id"]}
    assert suggest_trips(two, dismissed=dismissed, now=NOW) == []
    out = suggest_trips(ANDY_TRIP, dismissed=dismissed, now=NOW)
    assert len(out) == 1
