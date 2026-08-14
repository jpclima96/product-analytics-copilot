"""Testes das quatro métricas sobre o dataset sintético."""

from __future__ import annotations

from app.data.metrics import run_metric


def test_activation_rate(con):
    df = run_metric(con, "activation_rate")
    assert list(df.columns) == ["signups", "activated", "activation_rate"]
    row = df.iloc[0]
    assert row["signups"] > 0
    assert 0 <= row["activated"] <= row["signups"]
    # Ativação = concluir o passo 3 do onboarding: banda plausível.
    assert 0.30 <= row["activation_rate"] <= 0.70


def test_onboarding_funnel_is_monotonic(con):
    df = run_metric(con, "onboarding_funnel").sort_values("step")
    assert list(df["step"]) == [1, 2, 3]
    users = list(df["users"])
    # Funil monotonicamente decrescente.
    assert users[0] > users[1] > users[2]
    # Topo do funil = 100%.
    assert abs(df.iloc[0]["pct_of_top"] - 1.0) < 1e-9
    assert (df["pct_of_prev"].dropna() <= 1.0).all()


def test_retention_d7(con):
    df = run_metric(con, "retention_d7")
    assert list(df.columns) == ["cohort_users", "retained_d7", "retention_d7"]
    row = df.iloc[0]
    assert row["cohort_users"] > 0
    assert 0 <= row["retained_d7"] <= row["cohort_users"]
    assert 0.10 <= row["retention_d7"] <= 0.45


def test_feature_adoption(con):
    df = run_metric(con, "feature_adoption")
    assert list(df.columns) == [
        "feature_name",
        "users",
        "active_users",
        "adoption_rate",
    ]
    assert len(df) == 6  # seis features
    assert (df["adoption_rate"] > 0).all()
    assert (df["adoption_rate"] <= 1.0).all()
    # Ordenado por usuários (desc).
    assert list(df["users"]) == sorted(df["users"], reverse=True)


def test_unknown_metric_raises(con):
    import pytest

    with pytest.raises(KeyError):
        run_metric(con, "nao_existe")
