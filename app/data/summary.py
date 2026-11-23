"""Resumo executável das quatro métricas sobre os dados sintéticos.

Uso:
    python -m app.data.summary
"""

from __future__ import annotations

from app.data.catalog import metric_names
from app.data.db import build_connection
from app.data.generate import DEFAULT_N_USERS, SEED
from app.data.metrics import run_metric


def main() -> None:
    con = build_connection(n_users=DEFAULT_N_USERS, seed=SEED)

    n_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    dmin = con.execute("SELECT MIN(signup_ts) FROM users").fetchone()[0]
    dmax = con.execute("SELECT MAX(event_ts) FROM events").fetchone()[0]

    print("=" * 68)
    print("Product Analytics Copilot — camada de dados")
    print("=" * 68)
    print(f"Usuários : {n_users:,}")
    print(f"Eventos  : {n_events:,}")
    print(f"Período  : {dmin:%Y-%m-%d} → {dmax:%Y-%m-%d}")

    print("\nEventos por tipo:")
    for etype, cnt in con.execute(
        "SELECT event_type, COUNT(*) FROM events GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"  {etype:<28} {cnt:>10,}")

    for name in metric_names():
        print("\n" + "-" * 68)
        print(f"[{name}]")
        df = run_metric(con, name)
        print(df.to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()
