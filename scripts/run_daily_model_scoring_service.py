"""Persistent market-close scheduler for the independent daily scoring job."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
STATE_PATH = ROOT / "runs" / "daily_model_scoring" / "scheduler_state.json"


def _load_state() -> dict[str, str]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _register_vnstock_api_key() -> None:
    """Raise the free vnstock quota from 20 (guest) to 60 requests/minute."""

    api_key = os.getenv("VNSTOCK_API_KEY", "").strip()
    if not api_key:
        # Stay under the guest quota; vnai aborts the process once it is exceeded.
        try:
            configured = float(os.getenv("WAVE_H120_REQUESTS_PER_MINUTE", "18"))
        except ValueError:
            configured = 18.0
        os.environ["WAVE_H120_REQUESTS_PER_MINUTE"] = str(min(configured, 18.0))
        print("VNSTOCK_API_KEY is empty; vnstock runs in guest mode (18 requests/minute).", flush=True)
        return
    try:
        import vnstock
    except Exception as exc:  # noqa: BLE001 - the sync step reports the real import error
        print(f"Cannot import vnstock to register the API key: {exc}", flush=True)
        return
    for name in ("change_api_key", "register_user"):
        register = getattr(vnstock, name, None)
        if callable(register):
            try:
                register(api_key)
                print(f"Registered VNSTOCK_API_KEY via vnstock.{name}().", flush=True)
            except (Exception, SystemExit) as exc:
                print(f"Registering VNSTOCK_API_KEY failed: {exc}", flush=True)
            return
    print("vnstock reads VNSTOCK_API_KEY from the environment.", flush=True)


def _run_for_today(today: str) -> int:
    command = [sys.executable, "scripts/run_daily_model_scoring.py", "--snapshot-date", today]
    print(f"Daily scoring started for {today}", flush=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    _report(today, completed)
    return completed.returncode


def _report(today: str, completed: subprocess.CompletedProcess[str]) -> None:
    """Print one readable line per run so `docker compose logs` shows why it failed."""

    if completed.returncode == 0:
        print(f"Daily scoring succeeded for {today}", flush=True)
        return
    detail = completed.stderr.strip()[-1_500:]
    try:
        manifest = json.loads(completed.stdout)
        for step in manifest.get("steps", []):
            if step.get("return_code"):
                detail = (step.get("stderr_tail") or step.get("stdout_tail") or "").strip()[-1_500:]
        detail = manifest.get("error") or detail
    except (json.JSONDecodeError, AttributeError):
        pass
    print(f"Daily scoring failed for {today} (exit {completed.returncode}):\n{detail}", flush=True)


def _prune_after_success() -> None:
    """Bound both orchestration and H120 run directories after a good run."""
    keep = os.getenv("WAVE_DAILY_KEEP_SUCCESS_RUNS", "14")
    failed_days = os.getenv("WAVE_DAILY_FAILED_RETENTION_DAYS", "3")
    for root in ("runs/daily_model_scoring", "runs/wave_h120_shadow"):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/prune_daily_runs.py",
                "--run-root",
                root,
                "--keep-success",
                keep,
                "--failed-retention-days",
                failed_days,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Daily run cleanup failed for {root}: {result.stderr[-500:]}", flush=True)
        elif result.stdout.strip():
            print(result.stdout.strip(), flush=True)


def _latest_weekday(value: date) -> date:
    """Return the most recent weekday, allowing a restarted worker to catch up."""

    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


def _startup_candidate(now: datetime, target: str) -> str:
    """Choose a completed market day when the worker starts before close."""

    candidate = now.date()
    try:
        target_time = datetime.strptime(target, "%H:%M").time()
        if now.weekday() < 5 and now.time() < target_time:
            candidate -= timedelta(days=1)
    except ValueError:
        # Keep the safe weekday fallback if an invalid schedule is supplied.
        pass
    return _latest_weekday(candidate).isoformat()


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def main() -> int:
    target = os.getenv("WAVE_DAILY_SCORING_TIME", "19:00")
    run_on_start = _truthy(os.getenv("WAVE_DAILY_SCORING_RUN_ON_START", "false"))
    max_attempts = _positive_int("WAVE_DAILY_SCORING_MAX_ATTEMPTS", 8)
    retry_minutes = _positive_int("WAVE_DAILY_SCORING_RETRY_MINUTES", 30)
    state = _load_state()
    _register_vnstock_api_key()

    def attempt(today: str) -> None:
        attempts = int(state.get("attempt_count", 0)) if state.get("attempt_date") == today else 0
        if attempts >= max_attempts:
            return
        state["attempt_date"] = today
        state["attempt_count"] = str(attempts + 1)
        state["last_attempt_started_at_utc"] = datetime.now(TZ).astimezone().isoformat()
        _save_state(state)
        state["last_return_code"] = str(_run_for_today(today))
        # Retry cooldown starts when the potentially long-running job finishes.
        state["last_attempt_at_utc"] = datetime.now(TZ).astimezone().isoformat()
        if state["last_return_code"] == "0":
            state["last_success_date"] = today
            _prune_after_success()
        _save_state(state)

    if run_on_start:
        now = datetime.now(TZ)
        candidate = _startup_candidate(now, target)
        if state.get("last_success_date") != candidate:
            attempt(candidate)
    print(f"Daily advisory scoring scheduler active; market-close time={target} {TZ.key}; max_attempts={max_attempts}", flush=True)
    while True:
        now = datetime.now(TZ)
        today = now.date().isoformat()
        attempts = int(state.get("attempt_count", 0)) if state.get("attempt_date") == today else 0
        last_attempt = state.get("last_attempt_at_utc", "")
        retry_due = True
        if last_attempt:
            try:
                retry_due = (now.astimezone() - datetime.fromisoformat(last_attempt)).total_seconds() >= retry_minutes * 60
            except ValueError:
                pass
        if now.weekday() < 5 and now.strftime("%H:%M") >= target and state.get("last_success_date") != today and attempts < max_attempts and retry_due:
            attempt(today)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
