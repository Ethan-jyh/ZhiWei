"""Blueprint and HTTP routes for simulation statement interventions."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.services.intervention_service import InterventionService
from intervention.experiment_models import Experiment, FrozenScene, make_timing_variants
from intervention.metric_models import HeatConfig
from intervention.models import InterventionError, Statement

logger = logging.getLogger("mirofish.api.intervention")


def create_intervention_blueprint(
    service: InterventionService | None = None,
    metrics_service: Any = None,
    experiment_service: Any = None,
) -> Blueprint:
    bp = Blueprint("intervention", __name__)

    def _get_service() -> InterventionService:
        if service is not None:
            return service
        from app.services.simulation_runner import SimulationRunner

        return InterventionService(
            root=SimulationRunner.RUN_STATE_DIR,
            context_provider=SimulationRunner.get_intervention_context,
        )

    def _get_metrics_service():
        if metrics_service is not None:
            return metrics_service
        from app.services.intervention_metrics import get_metrics_service

        return get_metrics_service()

    def _get_experiment_service():
        if experiment_service is not None:
            return experiment_service
        from pathlib import Path
        from app.services.intervention_experiment import InterventionExperimentService
        from app.services.intervention_experiment_store import ExperimentStore
        from app.services.simulation_manager import SimulationManager
        from app.services.simulation_runner import SimulationRunner

        store_dir = Path(SimulationRunner.RUN_STATE_DIR).parent / "experiments"
        store = ExperimentStore(store_dir)
        manager = SimulationManager()
        return InterventionExperimentService(
            store=store,
            simulation_manager=manager,
            runner=SimulationRunner,
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

    @bp.route("/<run_id>/intervention-metrics", methods=["GET"])
    def get_intervention_metrics(run_id: str):
        ms = _get_metrics_service()
        try:
            cfg = ms.get_config(run_id)
            if cfg is None:
                return jsonify({"success": True, "data": {"status": "not_configured"}}), 200
            bundle = ms.get(run_id)
            if bundle is None:
                return jsonify({"success": True, "data": {"status": "computing"}}), 200
            return jsonify({"success": True, "data": bundle.model_dump(mode="json")}), 200
        except Exception as e:
            return _handle_error(e)

    @bp.route("/<run_id>/intervention-metric-config", methods=["PUT"])
    def save_intervention_metric_config(run_id: str):
        ms = _get_metrics_service()
        data = request.get_json(silent=True) or {}
        try:
            cfg = HeatConfig(**data)
            ms.save_config(run_id, cfg)
            bundle = ms.compute(run_id, cfg)
            return jsonify({"success": True, "data": bundle.model_dump(mode="json")}), 200
        except Exception as e:
            return _handle_error(e)

    @bp.route("/<run_id>/intervention-labels/correct", methods=["POST"])
    def correct_intervention_label(run_id: str):
        ms = _get_metrics_service()
        data = request.get_json(silent=True) or {}
        try:
            platform = data.get("platform")
            trace_rowid = data.get("trace_rowid")
            related = data.get("related")
            reason = data.get("reason", "")
            if not platform or trace_rowid is None:
                return jsonify({"success": False, "error": "platform and trace_rowid required"}), 400
            label = ms.correct(
                run_id,
                (run_id, platform, int(trace_rowid)),
                related=related,
                reason=reason,
            )
            return jsonify({"success": True, "data": label.model_dump(mode="json")}), 200
        except Exception as e:
            return _handle_error(e)

    @bp.route("/experiments", methods=["POST"])
    def create_experiment():
        es = _get_experiment_service()
        data = request.get_json(silent=True) or {}
        try:
            source_simulation_id = data.get("source_simulation_id")
            if not source_simulation_id:
                return jsonify({"success": False, "error": "source_simulation_id required"}), 400

            from app.services.simulation_runner import SimulationRunner

            source_dir = Path(SimulationRunner.RUN_STATE_DIR) / source_simulation_id
            if not source_dir.exists():
                return jsonify({"success": False, "error": f"Source simulation {source_simulation_id} not found"}), 404

            config_file = source_dir / "simulation_config.json"
            cfg = {}
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)

            project_id = data.get("project_id") or cfg.get("project_id", "default_proj")
            topic_id = data.get("topic_id") or cfg.get("topic_id", "default_topic")
            total_rounds = cfg.get("max_rounds", 20)
            t0_sources = data.get("t0_sources", [])
            metric_cfg_data = data.get("metric_config", {})
            metric_cfg = HeatConfig(**metric_cfg_data)

            profile_files = {}
            for p in ("twitter", "reddit"):
                if (source_dir / f"{p}_profiles.csv").exists():
                    profile_files[p] = f"{p}_profiles.csv"
                elif (source_dir / f"{p}_profiles.json").exists():
                    profile_files[p] = f"{p}_profiles.json"

            rel_files = {}
            if (source_dir / "initial_follows.json").exists():
                rel_files["follows"] = "initial_follows.json"

            scene_id = f"scene_{uuid.uuid4().hex[:12]}"
            scene = FrozenScene(
                scene_id=scene_id,
                project_id=project_id,
                topic_id=topic_id,
                t0_sources=t0_sources,
                config=cfg,
                profile_files=profile_files,
                relationship_files=rel_files,
                agent_mapping={},
                model_settings=cfg.get("model_settings", {"model": "default"}),
                metric_config=metric_cfg,
                sha256="",
            )
            frozen_scene = es.store.freeze(source_dir, scene=scene)

            statement_data = data.get("statement", {})
            statement = Statement(**statement_data)
            early_round = int(data.get("early_round", 5))
            late_round = int(data.get("late_round", 15))

            variants = make_timing_variants(
                statement,
                early_round=early_round,
                late_round=late_round,
                total_rounds=total_rounds,
            )

            experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
            experiment = Experiment(
                experiment_id=experiment_id,
                scene=frozen_scene,
                variants=variants,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            created = es.create(experiment)
            return jsonify({"success": True, "data": created.model_dump(mode="json")}), 201
        except Exception as e:
            return _handle_error(e)

    @bp.route("/experiments/<experiment_id>/runs", methods=["POST"])
    def create_experiment_run(experiment_id: str):
        es = _get_experiment_service()
        data = request.get_json(silent=True) or {}
        try:
            variant_id = data.get("variant_id")
            if not variant_id:
                return jsonify({"success": False, "error": "variant_id required"}), 400
            replicate_id = int(data.get("replicate_id", 1))
            seed = int(data.get("seed", 42))
            idempotency_key = data.get("idempotency_key") or f"{experiment_id}_{variant_id}_{replicate_id}"

            run = es.create_run(
                experiment_id,
                variant_id,
                replicate_id=replicate_id,
                seed=seed,
                idempotency_key=idempotency_key,
            )
            return jsonify({"success": True, "data": run.model_dump(mode="json")}), 201
        except Exception as e:
            return _handle_error(e)

    @bp.route("/experiments/<experiment_id>/runs/<run_id>/start", methods=["POST"])
    def start_experiment_run(experiment_id: str, run_id: str):
        es = _get_experiment_service()
        try:
            run = es.start_run(run_id)
            return jsonify({"success": True, "data": run.model_dump(mode="json")}), 202
        except Exception as e:
            return _handle_error(e)

    @bp.route("/experiments/<experiment_id>/comparison", methods=["GET"])
    def get_experiment_comparison(experiment_id: str):
        es = _get_experiment_service()
        ms = _get_metrics_service()
        is_srv = _get_service()
        try:
            comparison = es.compare(
                experiment_id,
                metrics_provider=lambda r: ms.get(r),
                statements_provider=lambda r: is_srv.list(r),
            )
            return jsonify({"success": True, "data": comparison.model_dump(mode="json")}), 200
        except Exception as e:
            return _handle_error(e)

    return bp
