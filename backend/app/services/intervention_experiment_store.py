"""Persistence, integrity verification, and run reservation for intervention experiments."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

from intervention.experiment_models import Experiment, ExperimentRun, FrozenScene
from intervention.models import InterventionError


def _compute_scene_hash(scene: FrozenScene, scene_dir: Path) -> str:
    """Compute deterministic SHA-256 over scene metadata and copied frozen files."""
    hasher = hashlib.sha256()

    # 1. Canonical scene JSON
    canonical_json = json.dumps(
        scene.canonical_dict(),
        sort_keys=True,
        ensure_ascii=False,
    )
    hasher.update(canonical_json.encode("utf-8"))

    # 2. Sorted file contents in scene_dir (excluding scene.json)
    all_files: list[Path] = []
    for root, _, files in os.walk(scene_dir):
        for f in files:
            if f != "scene.json" and not f.endswith(".tmp"):
                all_files.append(Path(root) / f)

    all_files.sort(key=lambda p: str(p.relative_to(scene_dir)))

    for path in all_files:
        rel_str = str(path.relative_to(scene_dir))
        hasher.update(rel_str.encode("utf-8"))
        hasher.update(path.read_bytes())

    return hasher.hexdigest()


class ExperimentStore:
    """Store for managing frozen scenes, experiments, and isolated runs."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.scenes_dir = self.root / "scenes"
        self.experiments_dir = self.root / "experiments"
        self.db_path = self.root / "experiments.sqlite"

        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    experiment_id TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    replicate_id INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    simulation_id TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    compatibility_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exploratory INTEGER NOT NULL,
                    error TEXT,
                    PRIMARY KEY (experiment_id, variant_id, replicate_id)
                );
                """
            )
            conn.commit()

    def freeze(self, source_dir: Path | str, *, scene: FrozenScene) -> FrozenScene:
        """Freeze input files and configuration for deterministic rebuilds."""
        src_path = Path(source_dir)
        target_scene_dir = self.scenes_dir / scene.scene_id
        target_scene_dir.mkdir(parents=True, exist_ok=True)

        # Collect and validate relative paths
        files_to_copy: list[str] = []
        for file_map in (scene.profile_files, scene.relationship_files):
            for rel_file in file_map.values():
                if not rel_file:
                    continue
                if rel_file.startswith("/") or ".." in rel_file:
                    raise InterventionError(
                        code="path_traversal_forbidden",
                        message=f"Path traversal forbidden in scene definition: {rel_file}",
                    )
                src_file = src_path / rel_file
                if not src_file.exists() or not src_file.is_file():
                    raise InterventionError(
                        code="scene_file_missing",
                        message=f"Referenced scene file does not exist in source: {rel_file}",
                    )
                files_to_copy.append(rel_file)

        # Copy only the whitelisted files
        for rel_file in set(files_to_copy):
            dest_file = target_scene_dir / rel_file
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path / rel_file, dest_file)

        # Also write simulation_config.json if not copied
        config_path = target_scene_dir / "simulation_config.json"
        if not config_path.exists():
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(scene.config, f, indent=2, ensure_ascii=False)

        # Compute deterministic hash
        sha = _compute_scene_hash(scene, target_scene_dir)
        final_scene = scene.model_copy(update={"sha256": sha})

        # Save scene.json atomically
        scene_json_path = target_scene_dir / "scene.json"
        tmp_scene_json = target_scene_dir / "scene.json.tmp"
        with open(tmp_scene_json, "w", encoding="utf-8") as f:
            f.write(final_scene.model_dump_json(indent=2))
        os.replace(tmp_scene_json, scene_json_path)

        return final_scene

    def get_scene(self, scene_id: str) -> FrozenScene:
        """Retrieve frozen scene metadata."""
        scene_path = self.scenes_dir / scene_id / "scene.json"
        if not scene_path.exists():
            raise InterventionError(
                code="scene_not_found",
                message=f"Scene {scene_id} not found in store",
            )
        with open(scene_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return FrozenScene(**data)

    def verify_scene(self, scene_id: str) -> None:
        """Verify hash integrity of frozen scene against stored disk files."""
        scene = self.get_scene(scene_id)
        scene_dir = self.scenes_dir / scene_id
        computed = _compute_scene_hash(scene, scene_dir)
        if computed != scene.sha256:
            raise InterventionError(
                code="scene_integrity_error",
                message=f"Frozen scene integrity check failed for {scene_id}: expected {scene.sha256}, got {computed}",
            )

    def save(self, experiment: Experiment) -> None:
        """Save experiment definition atomically."""
        exp_dir = self.experiments_dir / experiment.experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        exp_path = exp_dir / "experiment.json"
        tmp_path = exp_dir / "experiment.json.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(experiment.model_dump_json(indent=2))
        os.replace(tmp_path, exp_path)

    def get(self, experiment_id: str) -> Experiment:
        """Retrieve experiment definition."""
        exp_path = self.experiments_dir / experiment_id / "experiment.json"
        if not exp_path.exists():
            raise InterventionError(
                code="experiment_not_found",
                message=f"Experiment {experiment_id} not found in store",
            )
        with open(exp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Experiment(**data)

    def put_run(self, run: ExperimentRun) -> None:
        """Insert or update an ExperimentRun."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO experiment_runs (
                    experiment_id, variant_id, replicate_id, idempotency_key,
                    run_id, simulation_id, seed, compatibility_hash, status,
                    exploratory, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id, variant_id, replicate_id) DO UPDATE SET
                    status = excluded.status,
                    exploratory = excluded.exploratory,
                    error = excluded.error
                """,
                (
                    run.experiment_id,
                    run.variant_id,
                    run.replicate_id,
                    "",  # idempotency key preserved on update
                    run.run_id,
                    run.simulation_id,
                    run.seed,
                    run.compatibility_hash,
                    run.status,
                    1 if run.exploratory else 0,
                    run.error,
                ),
            )
            conn.commit()

    def list_runs(self, experiment_id: str) -> list[ExperimentRun]:
        """List all runs for an experiment."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT experiment_id, variant_id, replicate_id, idempotency_key,
                       run_id, simulation_id, seed, compatibility_hash, status,
                       exploratory, error
                FROM experiment_runs
                WHERE experiment_id = ?
                ORDER BY variant_id, replicate_id
                """,
                (experiment_id,),
            )
            rows = cur.fetchall()
            return [
                ExperimentRun(
                    run_id=r["run_id"],
                    simulation_id=r["simulation_id"],
                    experiment_id=r["experiment_id"],
                    variant_id=r["variant_id"],
                    replicate_id=r["replicate_id"],
                    seed=r["seed"],
                    compatibility_hash=r["compatibility_hash"],
                    status=r["status"],
                    exploratory=bool(r["exploratory"]),
                    error=r["error"],
                )
                for r in rows
            ]

    def reserve_run(
        self,
        experiment_id: str,
        variant_id: str,
        replicate_id: int,
        idempotency_key: str,
        *,
        factory: Callable[[], ExperimentRun],
    ) -> tuple[ExperimentRun, bool]:
        """Reserve a replicate run atomically. Returns (run, is_new)."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT experiment_id, variant_id, replicate_id, idempotency_key,
                       run_id, simulation_id, seed, compatibility_hash, status,
                       exploratory, error
                FROM experiment_runs
                WHERE experiment_id = ? AND variant_id = ? AND replicate_id = ?
                """,
                (experiment_id, variant_id, replicate_id),
            )
            row = cur.fetchone()
            if row is not None:
                existing = ExperimentRun(
                    run_id=row["run_id"],
                    simulation_id=row["simulation_id"],
                    experiment_id=row["experiment_id"],
                    variant_id=row["variant_id"],
                    replicate_id=row["replicate_id"],
                    seed=row["seed"],
                    compatibility_hash=row["compatibility_hash"],
                    status=row["status"],
                    exploratory=bool(row["exploratory"]),
                    error=row["error"],
                )
                return existing, False

            # Create new run via factory
            run = factory()
            conn.execute(
                """
                INSERT INTO experiment_runs (
                    experiment_id, variant_id, replicate_id, idempotency_key,
                    run_id, simulation_id, seed, compatibility_hash, status,
                    exploratory, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.experiment_id,
                    run.variant_id,
                    run.replicate_id,
                    idempotency_key,
                    run.run_id,
                    run.simulation_id,
                    run.seed,
                    run.compatibility_hash,
                    run.status,
                    1 if run.exploratory else 0,
                    run.error,
                ),
            )
            conn.commit()
            return run, True
