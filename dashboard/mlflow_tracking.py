"""
MLflow-backed version performance tracking.

Reuses the SAME sqlite database the Phase 4 eval harness already wrote to
(evals/mlflow.db) — so the 5 real v1.0 eval runs you already have are the
seeded baseline for version comparison, not a fresh empty store. Every
version created in the Play/Tweak page gets its own real runs logged here
when you click "Run eval on this version" — nothing in this file is
computed from a mock number.

Primary comparison metric: price_movement_pct (% moved from asking price in
the buyer's favor on closed deals) — per your call on which metric drives
version comparison.
"""
import sys
import time
from pathlib import Path

import mlflow
import pandas as pd

DASHBOARD_DIR = Path(__file__).resolve().parent
ROOT = DASHBOARD_DIR.parent
DB_PATH = ROOT / "evals" / "mlflow.db"
EXPERIMENT_NAME = "olx-negotiation-agent-evals"

sys.path.insert(0, str(ROOT / "evals"))


def _client() -> mlflow.MlflowClient:
    mlflow.set_tracking_uri(f"sqlite:///{DB_PATH}")
    return mlflow.MlflowClient(tracking_uri=f"sqlite:///{DB_PATH}")


def _experiment_id() -> str:
    mlflow.set_tracking_uri(f"sqlite:///{DB_PATH}")
    exp = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if exp is None:
        return mlflow.create_experiment(EXPERIMENT_NAME)
    return exp.experiment_id


def seed_historical_baselines() -> int:
    """One-time backfill: the 5 real Phase-4 eval runs already in
    evals/mlflow.db were logged before this dashboard's version concept
    existed, so they have no `version` tag yet. Tag them retroactively as
    v1.0 so the very first thing you see on Track Performance is real data,
    not an empty chart. Idempotent — safe to call on every app start.

    Returns how many runs were newly tagged.
    """
    client = _client()
    exp_id = _experiment_id()
    runs = client.search_runs([exp_id])
    tagged = 0
    for run in runs:
        if "version" not in run.data.tags:
            client.set_tag(run.info.run_id, "version", "v1.0")
            tagged += 1
    return tagged


def log_eval_run(version_id: str, test_case_id: str, model_id: str, metrics: dict, params: dict) -> str:
    """Logs one real test-case run against one config version. Returns the MLflow run id."""
    mlflow.set_tracking_uri(f"sqlite:///{DB_PATH}")
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name=f"{test_case_id}_{version_id}") as run:
        mlflow.set_tags({"test_case": test_case_id, "version": version_id, "model": model_id})
        for k, v in params.items():
            mlflow.log_param(k, v)
        for k, v in metrics.items():
            if v is not None:
                mlflow.log_metric(k, v)
        return run.info.run_id


def get_version_comparison() -> pd.DataFrame:
    """One row per version, aggregated from real logged runs."""
    client = _client()
    exp_id = _experiment_id()
    runs = client.search_runs([exp_id])
    rows = []
    for run in runs:
        tags = run.data.tags
        metrics = run.data.metrics
        rows.append(
            {
                "version": tags.get("version", "untagged"),
                "test_case": tags.get("test_case"),
                "model": tags.get("model"),
                "price_movement_pct": metrics.get("price_movement_pct"),
                "outcome_deal_closed": metrics.get("outcome_deal_closed"),
                "comps_count": metrics.get("comps_count"),
                "rounds_run": metrics.get("rounds_run"),
                "reasoning_present": metrics.get("reasoning_present"),
                "errored": metrics.get("errored"),
                "duration_sec": metrics.get("duration_sec"),
                "start_time": run.info.start_time,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "version", "n_runs", "avg_price_movement_pct", "deal_close_rate",
                "avg_rounds_run", "reasoning_coverage_pct", "avg_duration_sec", "last_run",
            ]
        )
    df = pd.DataFrame(rows)
    grouped = (
        df.groupby("version")
        .agg(
            n_runs=("test_case", "count"),
            avg_price_movement_pct=("price_movement_pct", "mean"),
            deal_close_rate=("outcome_deal_closed", "mean"),
            avg_rounds_run=("rounds_run", "mean"),
            reasoning_coverage_pct=("reasoning_present", "mean"),
            avg_duration_sec=("duration_sec", "mean"),
            last_run=("start_time", "max"),
        )
        .reset_index()
    )
    grouped["last_run"] = pd.to_datetime(grouped["last_run"], unit="ms")
    grouped["deal_close_rate"] = (grouped["deal_close_rate"] * 100).round(1)
    grouped["reasoning_coverage_pct"] = (grouped["reasoning_coverage_pct"] * 100).round(1)
    grouped["avg_price_movement_pct"] = grouped["avg_price_movement_pct"].round(1)
    grouped["avg_rounds_run"] = grouped["avg_rounds_run"].round(1)
    grouped["avg_duration_sec"] = grouped["avg_duration_sec"].round(1)
    return grouped.sort_values("last_run")


def get_before_after(current_version_id: str) -> dict:
    """Compares current_version_id's real average against the version run
    immediately before it in time. Returns None fields honestly when a
    version hasn't been scored yet — no fabricated placeholder score."""
    cmp = get_version_comparison()
    if cmp.empty or current_version_id not in cmp["version"].values:
        return {"current": None, "previous": None, "delta": None, "has_data": False}
    cmp = cmp.sort_values("last_run").reset_index(drop=True)
    idx = cmp.index[cmp["version"] == current_version_id][0]
    current_row = cmp.iloc[idx]
    if idx == 0:
        return {
            "current": current_row.to_dict(),
            "previous": None,
            "delta": None,
            "has_data": True,
        }
    previous_row = cmp.iloc[idx - 1]
    cur_val = current_row["avg_price_movement_pct"]
    prev_val = previous_row["avg_price_movement_pct"]
    delta = None
    if pd.notna(cur_val) and pd.notna(prev_val):
        delta = round(cur_val - prev_val, 1)
    return {
        "current": current_row.to_dict(),
        "previous": previous_row.to_dict(),
        "delta": delta,
        "has_data": True,
    }
