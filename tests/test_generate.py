"""Testes do gerador sintético: reprodutibilidade, volume e schema."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from app.core.models import Event, EventType, User
from app.data.generate import (
    SEED,
    SIGNUP_WINDOW_DAYS,
    generate_frames,
)


def test_reproducible_with_fixed_seed():
    u1, e1 = generate_frames(n_users=500, seed=SEED)
    u2, e2 = generate_frames(n_users=500, seed=SEED)
    pd.testing.assert_frame_equal(u1, u2)
    pd.testing.assert_frame_equal(e1, e2)


def test_different_seed_changes_data():
    _, e1 = generate_frames(n_users=500, seed=1)
    _, e2 = generate_frames(n_users=500, seed=2)
    assert len(e1) != len(e2) or not e1.equals(e2)


def test_at_least_10k_users_over_six_months():
    users, _ = generate_frames()
    assert len(users) >= 10_000
    span = users["signup_ts"].max() - users["signup_ts"].min()
    # Cadastros distribuídos ao longo de ~6 meses.
    assert timedelta(days=150) <= span <= timedelta(days=SIGNUP_WINDOW_DAYS)


def test_event_types_are_whitelisted():
    _, events = generate_frames(n_users=800, seed=SEED)
    allowed = {e.value for e in EventType}
    assert set(events["event_type"].unique()) <= allowed
    # Todos os tipos de evento exigidos aparecem no dataset.
    required = {
        EventType.signup.value,
        EventType.onboarding_step_completed.value,
        EventType.project_created.value,
        EventType.feature_used.value,
        EventType.subscription_started.value,
        EventType.subscription_cancelled.value,
    }
    assert required <= set(events["event_type"].unique())


def test_schema_columns():
    users, events = generate_frames(n_users=100, seed=SEED)
    assert list(users.columns) == ["user_id", "signup_ts", "plan", "country"]
    assert list(events.columns) == [
        "event_id",
        "user_id",
        "event_type",
        "event_ts",
        "properties",
        "session_id",
    ]


def test_rows_validate_against_pydantic_models():
    import json

    users, events = generate_frames(n_users=50, seed=SEED)
    for row in users.to_dict("records"):
        User.model_validate(row)
    for row in events.head(200).to_dict("records"):
        # Um loader real trata ausência como None (pandas expõe como NaN).
        session_id = row["session_id"]
        row = {
            **row,
            "properties": json.loads(row["properties"]),
            "session_id": None if pd.isna(session_id) else session_id,
        }
        Event.model_validate(row)


def test_every_user_has_signup():
    users, events = generate_frames(n_users=300, seed=SEED)
    signups = events[events["event_type"] == EventType.signup.value]
    assert set(signups["user_id"]) == set(users["user_id"])
    assert len(signups) == len(users)
