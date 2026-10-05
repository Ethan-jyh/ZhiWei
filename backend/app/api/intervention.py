"""Blueprint and HTTP routes for simulation statement interventions."""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.services.intervention_service import InterventionService
from intervention.models import InterventionError

logger = logging.getLogger("mirofish.api.intervention")


def create_intervention_blueprint(service: InterventionService | None = None) -> Blueprint:
    bp = Blueprint("intervention", __name__)

    def _get_service() -> InterventionService:
        if service is not None:
            return service
        from app.services.simulation_runner import SimulationRunner

        return InterventionService(
            root=SimulationRunner.RUN_STATE_DIR,
            context_provider=SimulationRunner.get_intervention_context,
        )

    def _handle_error(e: Exception):
        if isinstance(e, FileNotFoundError):
            return jsonify({"success": False, "error": str(e), "code": "not_found"}), 404
        if isinstance(e, InterventionError):
            if e.code in ("run_not_accepting", "idempotency_conflict"):
                return jsonify({"success": False, "error": e.message, "code": e.code}), 409
            return jsonify({"success": False, "error": e.message, "code": e.code}), 400
        if isinstance(e, (ValueError, ValidationError)):
            return jsonify({"success": False, "error": str(e), "code": "validation_error"}), 400
        logger.exception("Unexpected error handling intervention API: %s", e)
        return jsonify({"success": False, "error": str(e), "code": "internal_error"}), 500

    @bp.route("/<run_id>/intervention-plan", methods=["PUT"])
    def save_intervention_plan(run_id: str):
        srv = _get_service()
        data = request.get_json(silent=True) or {}
        items = data.get("statements", data if isinstance(data, list) else [])
        try:
            persisted = srv.save_plan(run_id, items)
            return jsonify({
                "success": True,
                "data": [s.model_dump(mode="json") for s in persisted],
            }), 200
        except Exception as e:
            return _handle_error(e)

    @bp.route("/<run_id>/interventions", methods=["POST"])
    def submit_intervention(run_id: str):
        srv = _get_service()
        data = request.get_json(silent=True) or {}
        try:
            statement, execution = srv.submit(run_id, data)
            return jsonify({
                "success": True,
                "data": {
                    "statement": statement.model_dump(mode="json"),
                    "execution": execution.model_dump(mode="json"),
                },
            }), 202
        except Exception as e:
            return _handle_error(e)

    @bp.route("/<run_id>/interventions", methods=["GET"])
    def list_interventions(run_id: str):
        srv = _get_service()
        try:
            items = srv.list(run_id)
            return jsonify({
                "success": True,
                "data": items,
            }), 200
        except Exception as e:
            return _handle_error(e)

    @bp.route("/<run_id>/interventions/<event_id>/cancel", methods=["POST"])
    def cancel_intervention(run_id: str, event_id: str):
        srv = _get_service()
        try:
            execution = srv.cancel(run_id, event_id)
            return jsonify({
                "success": True,
                "data": execution.model_dump(mode="json"),
            }), 202
        except Exception as e:
            return _handle_error(e)

    return bp
