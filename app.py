"""DevOps Task Tracker - Project 1 (one-tier: Flask serves UI + API, data in memory)."""
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from werkzeug.exceptions import HTTPException
from flask import Flask, jsonify, request, send_from_directory, g
from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Gauge, Histogram,
                               generate_latest)

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
VALID_ENVS = {"DEV", "QA", "PROD"}
PRIORITIES = {"low", "medium", "high"}
MAX_TITLE, MAX_DESC = 120, 500

REQUESTS = Counter("http_requests_total", "Total HTTP requests",
                   ["method", "endpoint", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request duration in seconds",
                    ["method", "endpoint"])
APP_INFO = Gauge("app_info", "Application information (value is always 1)",
                 ["version", "environment"])
TASKS_GAUGE = Gauge("tasks_total", "Tasks currently held in memory", ["state"])

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("task-tracker")


def get_env():
    env = os.getenv("APP_ENV", "DEV").upper()
    return env if env in VALID_ENVS else "DEV"


class TaskStore:
    """Thread-safe in-memory store. Lost on restart by design (see README)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}

    def list(self):
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: t["created_at"], reverse=True)

    def create(self, title, description, priority):
        now = datetime.now(timezone.utc).isoformat()
        task = {"id": uuid.uuid4().hex[:12], "title": title, "description": description,
                "priority": priority, "completed": False, "created_at": now, "updated_at": now}
        with self._lock:
            self._tasks[task["id"]] = task
        return dict(task)

    def update(self, task_id, changes):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task.update(changes)
            task["updated_at"] = datetime.now(timezone.utc).isoformat()
            return dict(task)

    def delete(self, task_id):
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def clear(self):
        with self._lock:
            self._tasks.clear()

    def counts(self):
        with self._lock:
            done = sum(1 for t in self._tasks.values() if t["completed"])
            return len(self._tasks), len(self._tasks) - done, done


def validate(payload, partial):
    """Return (clean_dict, error_message)."""
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."
    allowed = {"title", "description", "priority", "completed"}
    unknown = set(payload) - allowed
    if unknown:
        return None, "Unknown field(s): " + ", ".join(sorted(unknown))
    clean = {}
    if "title" in payload or not partial:
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            return None, "title is required and must be a non-empty string."
        if len(title.strip()) > MAX_TITLE:
            return None, f"title must be at most {MAX_TITLE} characters."
        clean["title"] = title.strip()
    if "description" in payload:
        d = payload["description"]
        if not isinstance(d, str) or len(d) > MAX_DESC:
            return None, f"description must be a string of at most {MAX_DESC} characters."
        clean["description"] = d.strip()
    if "priority" in payload:
        if payload["priority"] not in PRIORITIES:
            return None, "priority must be one of: low, medium, high."
        clean["priority"] = payload["priority"]
    if "completed" in payload:
        if not isinstance(payload["completed"], bool):
            return None, "completed must be true or false."
        clean["completed"] = payload["completed"]
    if partial and not clean:
        return None, "Provide at least one field to update."
    return clean, None


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    store = TaskStore()
    app.extensions["store"] = store
    started = time.time()
    APP_INFO.labels(version=APP_VERSION, environment=get_env()).set(1)

    def refresh_gauges():
        total, pending, done = store.counts()
        TASKS_GAUGE.labels(state="pending").set(pending)
        TASKS_GAUGE.labels(state="completed").set(done)

    @app.before_request
    def start_timer():
        g.t0 = time.perf_counter()

    @app.after_request
    def record(resp):
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        if endpoint != "/metrics":
            REQUESTS.labels(request.method, endpoint, str(resp.status_code)).inc()
            LATENCY.labels(request.method, endpoint).observe(time.perf_counter() - g.t0)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "no-store" if request.path.startswith(("/api", "/health", "/ready")) else resp.headers.get("Cache-Control", "no-cache")
        return resp

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/health")
    def health():
        return jsonify(status="healthy", version=APP_VERSION, environment=get_env(),
                       uptime_seconds=int(time.time() - started))

    @app.get("/ready")
    def ready():
        return jsonify(status="ready", version=APP_VERSION, environment=get_env())

    @app.get("/api/tasks")
    def list_tasks():
        tasks = store.list()
        total, pending, done = store.counts()
        return jsonify(tasks=tasks, summary={"total": total, "pending": pending, "completed": done})

    @app.post("/api/tasks")
    def create_task():
        payload = request.get_json(silent=True)
        clean, err = validate(payload, partial=False)
        if err:
            return jsonify(error=err), 400
        task = store.create(clean["title"], clean.get("description", ""), clean.get("priority", "medium"))
        if clean.get("completed"):
            task = store.update(task["id"], {"completed": True})
        refresh_gauges()
        log.info("task created id=%s", task["id"])
        return jsonify(task), 201

    @app.patch("/api/tasks/<task_id>")
    def update_task(task_id):
        if not re.fullmatch(r"[0-9a-f]{12}", task_id):
            return jsonify(error="Task not found."), 404
        payload = request.get_json(silent=True)
        clean, err = validate(payload, partial=True)
        if err:
            return jsonify(error=err), 400
        task = store.update(task_id, clean)
        if task is None:
            return jsonify(error="Task not found."), 404
        refresh_gauges()
        return jsonify(task)

    @app.delete("/api/tasks/<task_id>")
    def delete_task(task_id):
        if not store.delete(task_id):
            return jsonify(error="Task not found."), 404
        refresh_gauges()
        return "", 204

    @app.get("/metrics")
    def metrics():
        refresh_gauges()
        return app.response_class(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="Resource not found."), 404

    @app.errorhandler(405)
    def bad_method(_):
        return jsonify(error="Method not allowed."), 405

    @app.errorhandler(Exception)
    def server_error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        log.exception("unhandled error: %s", type(exc).__name__)
        return jsonify(error="Internal server error."), 500

    return app


app = create_app()

if __name__ == "__main__":  # local development only; containers use Gunicorn
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
