"""Shared helpers for the JSON API."""
from flask import jsonify, request


def ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def fail(message, status=400, **extra):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status


def body() -> dict:
    """Request payload from JSON or a classic form post."""
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}
    return {k: (v if len(v) > 1 else v[0])
            for k, v in request.form.to_dict(flat=False).items()}


def query_params() -> dict:
    return {k: (v if len(v) > 1 else v[0])
            for k, v in request.args.to_dict(flat=False).items()}


def paging(default_size=50, max_size=500):
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.args.get("page_size", default_size))
    except (TypeError, ValueError):
        size = default_size
    return page, max(1, min(size, max_size))
