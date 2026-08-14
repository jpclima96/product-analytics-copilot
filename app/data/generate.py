"""Gerador reproduzível de eventos sintéticos.

- Seed fixa → resultado determinístico (mesma seed + mesmo `n_users` produzem
  exatamente os mesmos dados).
- Sem PII: todos os dados são sintéticos.
- Modela cadastro, onboarding, criação de projeto, uso de features, assinatura,
  cancelamento e atividade recorrente (curva de retenção).

A camada de armazenamento (DuckDB) fica em `app/data/db.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.core.models import EventType

# --------------------------------------------------------------------------- #
# Parâmetros do gerador (decisões de modelagem)
# --------------------------------------------------------------------------- #
SEED = 42
DEFAULT_N_USERS = 12_000          # "pelo menos 10.000 usuários"
SIGNUP_WINDOW_DAYS = 182          # ~6 meses de cadastros
ACTIVITY_HORIZON_DAYS = 90        # janela de atividade por usuário após o signup
START_DATE = datetime(2025, 1, 1)  # naive UTC (evita ambiguidade de fuso)

FEATURES = ["dashboards", "reports", "alerts", "integrations", "export", "api"]
FEATURE_WEIGHTS = np.array([0.30, 0.22, 0.15, 0.12, 0.13, 0.08])
COUNTRIES = ["BR", "US", "PT", "DE", "IN", "MX"]

# Probabilidades do funil de onboarding (condicional ao passo anterior).
ONB_P_STEP1 = 0.88
ONB_P_STEP2 = 0.80
ONB_P_STEP3 = 0.72
P_PROJECT_AFTER_ONB = 0.75
P_SUBSCRIBE_IF_ACTIVATED = 0.55
P_CANCEL_IF_SUBSCRIBED = 0.28
RETENTION_DECAY_DAYS = 45.0       # escala de decaimento da atividade


def generate_frames(
    n_users: int = DEFAULT_N_USERS, seed: int = SEED
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gera os DataFrames ``users`` e ``events`` de forma determinística."""
    rng = np.random.default_rng(seed)

    users: list[dict] = []
    events: list[dict] = []
    counter = 0

    def emit(user_id, etype: EventType, ts, properties=None, session_id=None):
        nonlocal counter
        counter += 1
        events.append(
            {
                "event_id": f"evt_{counter:09d}",
                "user_id": user_id,
                "event_type": etype.value,
                "event_ts": ts,
                "properties": json.dumps(properties or {}),
                "session_id": session_id,
            }
        )

    # Sorteios por usuário (vetorizados para reprodutibilidade e velocidade).
    signup_offset = rng.integers(0, SIGNUP_WINDOW_DAYS, size=n_users)
    signup_second = rng.integers(0, 86_400, size=n_users)
    countries = rng.choice(COUNTRIES, size=n_users)
    engagement = rng.beta(2.0, 5.0, size=n_users)  # média ~0.286

    for k in range(n_users):
        user_id = f"u_{k:06d}"
        signup_ts = START_DATE + timedelta(
            days=int(signup_offset[k]), seconds=int(signup_second[k])
        )
        plan = "free"

        emit(user_id, EventType.signup, signup_ts)

        # --- Funil de onboarding -------------------------------------------- #
        reached_step = 0
        step_ts = signup_ts
        if rng.random() < ONB_P_STEP1:
            step_ts = signup_ts + timedelta(hours=float(rng.uniform(0.1, 24)))
            emit(user_id, EventType.onboarding_step_completed, step_ts, {"step": 1})
            reached_step = 1
            if rng.random() < ONB_P_STEP2:
                step_ts = step_ts + timedelta(hours=float(rng.uniform(1, 36)))
                emit(user_id, EventType.onboarding_step_completed, step_ts, {"step": 2})
                reached_step = 2
                if rng.random() < ONB_P_STEP3:
                    step_ts = step_ts + timedelta(hours=float(rng.uniform(1, 48)))
                    emit(
                        user_id,
                        EventType.onboarding_step_completed,
                        step_ts,
                        {"step": 3},
                    )
                    reached_step = 3

        # --- Ativação (canônica: concluir o passo 3 do onboarding) ---------- #
        activated_ts = None
        if reached_step == 3:
            activated_ts = step_ts
            emit(user_id, EventType.activated, activated_ts)

        # --- Criação de projeto --------------------------------------------- #
        if reached_step >= 2 and rng.random() < P_PROJECT_AFTER_ONB:
            proj_ts = step_ts + timedelta(hours=float(rng.uniform(1, 72)))
            emit(
                user_id,
                EventType.project_created,
                proj_ts,
                {"project_id": f"p_{k:06d}"},
            )

        # --- Assinatura e cancelamento -------------------------------------- #
        if activated_ts is not None and rng.random() < P_SUBSCRIBE_IF_ACTIVATED:
            sub_ts = activated_ts + timedelta(days=float(rng.uniform(0, 10)))
            plan = str(rng.choice(["pro", "business"], p=[0.7, 0.3]))
            emit(user_id, EventType.subscription_started, sub_ts, {"plan": plan})
            if rng.random() < P_CANCEL_IF_SUBSCRIBED:
                cancel_ts = sub_ts + timedelta(days=float(rng.uniform(10, 120)))
                emit(
                    user_id,
                    EventType.subscription_cancelled,
                    cancel_ts,
                    {"plan": plan},
                )

        # --- Atividade recorrente (curva de retenção) ----------------------- #
        days = np.arange(ACTIVITY_HORIZON_DAYS)
        active_prob = engagement[k] * np.exp(-days / RETENTION_DECAY_DAYS)
        active_days = days[rng.random(ACTIVITY_HORIZON_DAYS) < active_prob]
        for d in active_days:
            base = signup_ts + timedelta(
                days=int(d), seconds=int(rng.integers(0, 86_400))
            )
            session_id = f"{user_id}-d{int(d)}"
            emit(user_id, EventType.session_start, base, session_id=session_id)
            emit(
                user_id,
                EventType.login,
                base + timedelta(seconds=1),
                session_id=session_id,
            )
            n_feat = int(rng.integers(1, 4))
            feats = rng.choice(FEATURES, size=n_feat, replace=False, p=FEATURE_WEIGHTS)
            for fname in feats:
                emit(
                    user_id,
                    EventType.feature_used,
                    base + timedelta(minutes=int(rng.integers(1, 120))),
                    {"feature_name": str(fname)},
                    session_id=session_id,
                )

        users.append(
            {
                "user_id": user_id,
                "signup_ts": signup_ts,
                "plan": plan,
                "country": str(countries[k]),
            }
        )

    users_df = pd.DataFrame(users)
    events_df = pd.DataFrame(events).sort_values("event_ts").reset_index(drop=True)
    return users_df, events_df
