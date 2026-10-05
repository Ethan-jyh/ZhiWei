"""Service coordinating intervention experiments, run compilation, and execution."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from intervention.experiment_models import (
    ComparisonResult,
    Experiment,
    ExperimentRun,
    FrozenScene,
)
from intervention.metric_models import HeatConfig, MetricBundle
from intervention.models import InterventionError, Platform, Statement
from app.services.intervention_experiment_store import ExperimentStore
from app.services.simulation_manager import SimulationManager, SimulationStatus

logger = logging.getLogger(__name__)


def compatibility_hash(
    scene: FrozenScene,
    *,
    runtime_model_config: dict[str, Any],
    metric_config: HeatConfig,
    enabled_platforms: set[Platform],
    total_rounds: int,
) -> str:
    """Generate a baseline hash for verifying experiment compatibility across runs."""
    hasher = hashlib.sha256()
    hasher.update(scene.sha256.encode("utf-8"))
    hasher.update(
        json.dumps(runtime_model_config, sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
    )
    hasher.update(metric_config.model_dump_json().encode("utf-8"))
    hasher.update(",".join(sorted(enabled_platforms)).encode("utf-8"))
    hasher.update(str(total_rounds).encode("utf-8"))
    return hasher.hexdigest()[:16]


def prepare_frozen_run(
    manager: SimulationManager,
    scene: FrozenScene,
    run_id: str,
    statements: list[Statement],
    *,
    scene_dir: Path | None = None,
) -> Path:
    """Deterministically compile a new simulation directory from frozen scene inputs."""
    sim_dir = Path(manager._get_simulation_dir(run_id))
    sim_dir.mkdir(parents=True, exist_ok=True)

    if scene_dir is None:
        scene_dir = Path(manager.SIMULATION_DATA_DIR) / "experiments" / "scenes" / scene.scene_id

    # 1. Copy frozen profile and relationship files
    for file_map in (scene.profile_files, scene.relationship_files):
        for rel_file in file_map.values():
            if not rel_file:
                continue
            src = scene_dir / rel_file
            if src.exists() and src.is_file():
                dest = sim_dir / rel_file
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    # 2. Compile simulation_config.json
    cfg = copy.deepcopy(scene.config)
    cfg["simulation_id"] = run_id
    config_file = sim_dir / "simulation_config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    # 3. Write initial intervention plan (substituting run_id on statements)
    interventions_dir = sim_dir / "interventions"
    interventions_dir.mkdir(parents=True, exist_ok=True)
    plan_statements = []
    for stmt in statements:
        updated_stmt = stmt.model_copy(deep=True, update={"run_id": run_id})
        plan_statements.append(updated_stmt.model_dump(mode="json"))

    plan_file = interventions_dir / "initial_intervention_plan.json"
    tmp_plan_file = interventions_dir / "initial_intervention_plan.json.tmp"
    with open(tmp_plan_file, "w", encoding="utf-8") as f:
        json.dump(plan_statements, f, indent=2, ensure_ascii=False)
    os.replace(tmp_plan_file, plan_file)

    # 4. Mark simulation state as READY
    state = manager.get_simulation(run_id) if hasattr(manager, "get_simulation") else None
    if state is None:
        state = manager._load_simulation_state(run_id)
    if state:
        state.status = SimulationStatus.READY
        state.profiles_generated = True
        state.config_generated = True
        manager._save_simulation_state(state)

    return config_file


class InterventionExperimentService:
    """Service orchestrating experiment creation, variant compilation, and run execution."""

    def __init__(
        self,
        store: ExperimentStore,
        simulation_manager: SimulationManager,
        runner: Any,
    ) -> None:
        self.store = store
        self.simulation_manager = simulation_manager
        self.runner = runner

    def create(self, experiment: Experiment) -> Experiment:
        """Register a new experiment definition."""
        self.store.save(experiment)
        return experiment

    def create_run(
        self,
        experiment_id: str,
        variant_id: str,
        *,
        replicate_id: int,
        seed: int,
        idempotency_key: str,
    ) -> ExperimentRun:
        """Compile and reserve an isolated run for an experiment variant."""
        exp = self.store.get(experiment_id)
        var = next((v for v in exp.variants if v.variant_id == variant_id), None)
        if var is None:
            raise InterventionError(
                code="variant_not_found",
                message=f"Variant {variant_id} not found in experiment {experiment_id}",
            )

        def factory() -> ExperimentRun:
            sim_state = self.simulation_manager.create_simulation(
                project_id=exp.scene.project_id,
                graph_id=exp.scene.config.get("graph_id", ""),
            )
            run_id = sim_state.simulation_id
            scene_dir = self.store.scenes_dir / exp.scene.scene_id

            prepare_frozen_run(
                self.simulation_manager,
                exp.scene,
                run_id=run_id,
                statements=var.statements,
                scene_dir=scene_dir,
            )

            total_rounds = exp.scene.config.get("max_rounds", 20)
            enabled_platforms = set(exp.scene.profile_files.keys())
            comp_hash = compatibility_hash(
                exp.scene,
                runtime_model_config=exp.scene.model_settings,
                metric_config=exp.scene.metric_config,
                enabled_platforms=enabled_platforms,  # type: ignore[arg-type]
                total_rounds=total_rounds,
            )

            return ExperimentRun(
                run_id=run_id,
                simulation_id=run_id,
                experiment_id=experiment_id,
                variant_id=variant_id,
                replicate_id=replicate_id,
                seed=seed,
                compatibility_hash=comp_hash,
                status="ready",
                exploratory=False,
            )

        run, is_new = self.store.reserve_run(
            experiment_id,
            variant_id,
            replicate_id,
            idempotency_key,
            factory=factory,
        )
        return run

    def start_run(self, run_id: str) -> ExperimentRun:
        """Start execution of a compiled experiment run."""
        run = self.store.get_run(run_id)
        if run is None:
            raise InterventionError(
                code="run_not_found",
                message=f"Run {run_id} not found in store",
            )

        if run.status in ("running", "completed"):
            return run

        self.runner.start_simulation(simulation_id=run_id)
        run.status = "running"
        self.store.put_run(run)
        return run

    def mark_exploratory(self, run_id: str, *, reason: str = "") -> None:
        """Mark a run as exploratory due to manual intervention adjustments."""
        run = self.store.get_run(run_id)
        if run:
            run.exploratory = True
            self.store.put_run(run)

    def compare(
        self,
        experiment_id: str,
        *,
        metrics_provider: Callable[[str], MetricBundle | None],
        statements_provider: Callable[[str], list[dict[str, Any]]],
    ) -> ComparisonResult:
        """Transparently compare compatible runs against baseline without obscuring anomalies."""
        experiment = self.store.get(experiment_id)
        runs = self.store.list_runs(experiment_id)
        variant_map = {v.variant_id: v for v in experiment.variants}

        included_runs: list[dict[str, Any]] = []
        incompatible_runs: list[dict[str, Any]] = []

        standard_limitations = [
            "不同随机种子或LLM随机采样存在固有方差，单次实验结果不代表因果预测准确率",
            "各运行间环境状态、平台数据库与讨论历史相互严格隔离，无继承关系",
            "热度指标仅衡量围绕特定话题的发帖与互动频次规模及回落时间，不代表公众对方案认同度或满意度",
        ]

        for run in runs:
            variant = variant_map.get(run.variant_id)
            bundle = metrics_provider(run.simulation_id)
            actual_stmts = statements_provider(run.simulation_id)

            # 1. Metric configuration check
            if bundle is not None:
                b_cfg = bundle.config
                s_cfg = experiment.scene.metric_config
                if (
                    b_cfg.threshold != s_cfg.threshold
                    or b_cfg.consecutive_rounds != s_cfg.consecutive_rounds
                    or b_cfg.minutes_per_round != s_cfg.minutes_per_round
                ):
                    incompatible_runs.append({
                        "run_id": run.run_id,
                        "variant_id": run.variant_id,
                        "reason": "metric_config_mismatch",
                        "detail": f"Threshold {b_cfg.threshold} != baseline {s_cfg.threshold}",
                    })
                    continue

            # 2. Check compatibility hash
            total_rounds = experiment.scene.config.get("max_rounds", 20)
            enabled_platforms = set(experiment.scene.profile_files.keys())
            expected_hash = compatibility_hash(
                experiment.scene,
                runtime_model_config=experiment.scene.model_settings,
                metric_config=experiment.scene.metric_config,
                enabled_platforms=enabled_platforms,  # type: ignore[arg-type]
                total_rounds=total_rounds,
            )
            if run.compatibility_hash and run.compatibility_hash != expected_hash:
                incompatible_runs.append({
                    "run_id": run.run_id,
                    "variant_id": run.variant_id,
                    "reason": "compatibility_hash_mismatch",
                    "detail": "Baseline scene or model settings diverged",
                })
                continue

            # 3. Check for exploratory: extra manual statements
            is_exploratory = run.exploratory
            if variant is not None:
                expected_count = len(variant.statements)
                if len(actual_stmts) > expected_count:
                    is_exploratory = True
                else:
                    for s in actual_stmts:
                        if s.get("origin") == "manual" or s.get("source") == "manual":
                            is_exploratory = True
                            break

            included_runs.append({
                "run": run.model_dump(),
                "variant_id": run.variant_id,
                "replicate_id": run.replicate_id,
                "seed": run.seed,
                "status": run.status,
                "exploratory": is_exploratory,
                "bundle": bundle.model_dump() if bundle else None,
                "statements": actual_stmts,
                "error": run.error,
            })

        return ComparisonResult(
            experiment_id=experiment_id,
            runs=included_runs,
            incompatible_runs=incompatible_runs,
            limitations=standard_limitations,
        )
