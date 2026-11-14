"""Background pipeline jobs: status, per-task progress, cancellation, retry, detailed logs, crash recovery.

Guarantees about scientific outputs:
  * a task writes its output only after it completed AND passed validation (schema + completeness gate); every write
    is atomic (temp file + rename), so a cancelled / crashed / failed task leaves no partial or misleading output;
  * leftover temp files are removed at start-up; jobs found 'running' after a restart are marked 'interrupted';
  * failed tasks keep their error and traceback in the job log; retry re-runs only unfinished tasks.
"""
from __future__ import annotations
import json
import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .core.config import get_settings
from .core.security import redact
from .gee import cancel as cancelmod

log = logging.getLogger("gcl.jobs")
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gcl-job")
_jobs: dict[str, dict] = {}
_events: dict[str, threading.Event] = {}
_lock = threading.RLock()

TERMINAL = {"completed", "completed_with_errors", "failed", "cancelled", "interrupted"}


def _dir():
    d = get_settings().data_dir / "cache"
    (d / "job_logs").mkdir(parents=True, exist_ok=True)
    return d


def _persist():
    try:
        tmp = _dir() / "jobs.json.tmp"
        tmp.write_text(json.dumps(list(_jobs.values())[-200:]), encoding="utf-8")
        tmp.replace(_dir() / "jobs.json")
    except OSError:
        log.exception("could not persist jobs")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _logline(jid: str, msg: str):
    try:
        with open(_dir() / "job_logs" / f"{jid}.log", "a", encoding="utf-8") as f:
            f.write(f"{_now()} {redact(msg)}\n")
    except OSError:
        pass


def label(t: dict) -> str:
    return f"{t['type']}:{t['key']}" + (f":{t['season']}" if t.get("season") else "")


def _progress(job: dict) -> dict:
    n = len(job["tasks"]) or 1
    done = sum(1 for t in job["tasks"] if t["status"] in ("done", "failed", "cancelled", "skipped"))
    return {"done": done, "total": len(job["tasks"]), "percent": round(100 * done / n)}


def recover() -> None:
    """Load history; mark interrupted jobs; remove partial files."""
    from .core import store
    removed = store.clean_partial_files()
    try:
        for j in json.loads((_dir() / "jobs.json").read_text(encoding="utf-8")):
            if j["status"] in ("queued", "running"):
                j["status"] = "interrupted"
                j["error"] = "Server stopped while the job was active. Completed tasks are kept; use retry to run the rest."
                for t in j["tasks"]:
                    if t["status"] in ("running", "pending"):
                        t["status"] = "interrupted" if t["status"] == "running" else "pending"
            _jobs[j["id"]] = j
    except (OSError, ValueError, KeyError):
        pass
    if removed:
        log.warning("removed %d partial temp files at start-up", len(removed))


def submit(spec: dict) -> dict:
    """spec: {region, start, end, tasks: [{type: 'series'|'stack', key, season?}]}"""
    jid = uuid.uuid4().hex[:12]
    tasks = [{**t, "id": i, "label": label(t), "status": "pending", "attempts": 0, "error": None, "detail": None} for i, t in enumerate(spec["tasks"])]
    job = {"id": jid, "status": "queued", "created": _now(), "spec": {**spec, "tasks": spec["tasks"]}, "tasks": tasks, "error": None, "cancel_requested": False}
    job["progress"] = _progress(job)
    with _lock:
        _jobs[jid] = job
        _events[jid] = threading.Event()
        _persist()
    _logline(jid, f"queued {len(tasks)} task(s): " + ", ".join(t["label"] for t in tasks))
    _pool.submit(_run, jid)
    return job


def cancel(jid: str) -> dict | None:
    with _lock:
        job = _jobs.get(jid)
        if not job:
            return None
        if job["status"] in TERMINAL:
            return job
        job["cancel_requested"] = True
        _events.setdefault(jid, threading.Event()).set()
        if job["status"] == "queued":
            job["status"] = "cancelled"
            for t in job["tasks"]:
                t["status"] = "cancelled"
            job["progress"] = _progress(job)
        _persist()
    _logline(jid, "cancel requested")
    return job


def retry(jid: str) -> dict | None:
    """Re-run every task that did not finish successfully. Finished tasks are not repeated."""
    with _lock:
        job = _jobs.get(jid)
        if not job or job["status"] not in TERMINAL or job["status"] == "completed":
            return job
        for t in job["tasks"]:
            if t["status"] != "done":
                t["status"], t["error"] = "pending", None
        job.update(status="queued", error=None, cancel_requested=False)
        job.pop("finished", None)
        _events[jid] = threading.Event()
        job["progress"] = _progress(job)
        _persist()
    _logline(jid, "retry requested")
    _pool.submit(_run, jid)
    return job


def _run(jid: str):
    from .gee import extract
    job = _jobs[jid]
    ev = _events.setdefault(jid, threading.Event())
    with _lock:
        if job["status"] == "cancelled":
            return
        job["status"] = "running"
        job["started"] = _now()
        _persist()
    spec = job["spec"]
    cancelmod.set_event(ev)
    try:
        for t in job["tasks"]:
            if t["status"] == "done":
                continue
            if ev.is_set():
                t["status"] = "cancelled"
                continue
            t.update(status="running", started=_now(), attempts=t["attempts"] + 1, error=None)
            job["progress"] = _progress(job)
            _persist()
            _logline(jid, f"start {t['label']} (attempt {t['attempts']})")
            try:
                if t["type"] == "series":
                    res = extract.run_series_job(t["key"], spec["region"], spec["start"], spec["end"])
                else:
                    res = extract.run_stack_job(t["key"], spec["region"], spec["start"], spec["end"], t["season"])
                t.update(status="done", detail=res, finished=_now())
                _logline(jid, f"done {t['label']}: {json.dumps(res, default=str)}")
            except cancelmod.JobCancelled:
                t.update(status="cancelled", error="cancelled by user", finished=_now())
                _logline(jid, f"cancelled {t['label']} (no output written)")
            except Exception as e:      # surfaced with traceback in the log; never converted into data
                t.update(status="failed", error=redact(f"{type(e).__name__}: {e}"), finished=_now())
                _logline(jid, f"FAILED {t['label']}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
                log.warning("job %s task %s failed: %s", jid, t["label"], type(e).__name__)
            job["progress"] = _progress(job)
            _persist()
    finally:
        cancelmod.set_event(None)
    statuses = {t["status"] for t in job["tasks"]}
    if ev.is_set() or "cancelled" in statuses:
        job["status"] = "cancelled"
    elif statuses == {"done"}:
        job["status"] = "completed"
    elif "done" in statuses:
        job["status"] = "completed_with_errors"
    else:
        job["status"] = "failed"
    if job["status"] in ("failed", "completed_with_errors"):
        job["error"] = "One or more tasks failed; see task errors and the job log."
    job["finished"] = _now()
    job["progress"] = _progress(job)
    _persist()
    _logline(jid, f"job {job['status']}")


def get(jid: str) -> dict | None:
    return _jobs.get(jid)


def log_tail(jid: str, max_bytes: int = 20000) -> str | None:
    p = _dir() / "job_logs" / f"{jid}.log"
    if not p.exists() or jid not in _jobs:
        return None
    data = p.read_bytes()[-max_bytes:]
    return data.decode("utf-8", errors="replace")


def list_jobs() -> list[dict]:
    return sorted(_jobs.values(), key=lambda j: j["created"], reverse=True)


recover()
