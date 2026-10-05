"""Service managing discussion heat metrics calculation, caching, and manual correction."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from collections.abc import Callable
from pathlib import Path

from intervention.metric_models import (
    CoolingSummary,
    HeatConfig,
    MetricBundle,
    TopicLabel,
)
from intervention.metrics import aggregate_heat, calculate_cooling, read_round_completion
from intervention.models import Platform
from intervention.topic_labels import (
    TopicLabelStore,
    correct_label,
    label_actions,
    read_actions,
)

logger = logging.getLogger(__name__)


def make_default_llm_classifier() -> Callable[[str, str], tuple[bool, str]]:
    """Create a default topic classifier using LLMClient if available."""
    try:
        from app.utils.llm_client import LLMClient

        llm = LLMClient()
    except Exception:
        llm = None

    def _classifier(content: str, topic_summary: str) -> tuple[bool, str]:
        if not llm:
            # Fallback substring heuristic
            rel = topic_summary.lower() in content.lower()
            return rel, "Default heuristic matching"

        prompt = (
            f"请判断以下社交媒体内容是否属于或讨论给定的话题事件。\n\n"
            f"话题事件：{topic_summary}\n\n"
            f"内容：{content}\n\n"
            f"请以严格JSON格式返回：{{\"related\": true/false, \"reason\": \"简述原因\"}}"
        )
        try:
            res = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.1)
            return bool(res.get("related", False)), str(res.get("reason", ""))
        except Exception as e:
            logger.warning(f"Topic classification failed: {e}")
            raise

    return _classifier


class InterventionMetricsService:
    """Service providing topic intervention heat metrics computation and caching."""

    def __init__(
        self,
        root: Path | str,
        classifier: Callable[[str, str], tuple[bool, str]] | None = None,
    ) -> None:
        self.root = Path(root)
        self.classifier = classifier or make_default_llm_classifier()
        self._refresh_queue: queue.Queue[tuple[str, bool, bool]] = queue.Queue()
        self._pending_tasks: dict[str, tuple[bool, bool]] = {}
        self._task_lock = threading.Lock()
        self._worker_thread = threading.Thread(
            target=self._process_refresh_queue, daemon=True
        )
        self._worker_thread.start()

    def get_config(self, run_id: str) -> HeatConfig | None:
        """Load saved HeatConfig for the given simulation run."""
        sim_dir = self.root / run_id
        config_path = sim_dir / "interventions" / "heat_config.json"
        if not config_path.exists():
            return None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return HeatConfig(**data)
        except Exception as e:
            logger.warning(f"Failed to read heat config for {run_id}: {e}")
            return None

    def save_config(self, run_id: str, config: HeatConfig) -> None:
        """Save HeatConfig atomically to the simulation directory."""
        sim_dir = self.root / run_id
        target_dir = sim_dir / "interventions"
        target_dir.mkdir(parents=True, exist_ok=True)
        config_path = target_dir / "heat_config.json"
        tmp_path = target_dir / "heat_config.json.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(config.model_dump_json(indent=2))
        os.replace(tmp_path, config_path)

    def get(self, run_id: str) -> MetricBundle | None:
        """Retrieve cached MetricBundle if present."""
        sim_dir = self.root / run_id
        bundle_path = sim_dir / "interventions" / "metrics_bundle.json"
        if not bundle_path.exists():
            return None
        try:
            with open(bundle_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MetricBundle(**data)
        except Exception as e:
            logger.warning(f"Failed to read metrics bundle for {run_id}: {e}")
            return None

    def _save_bundle(self, run_id: str, bundle: MetricBundle) -> None:
        sim_dir = self.root / run_id
        target_dir = sim_dir / "interventions"
        target_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = target_dir / "metrics_bundle.json"
        tmp_path = target_dir / "metrics_bundle.json.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(bundle.model_dump_json(indent=2))
        os.replace(tmp_path, bundle_path)

    def compute(
        self,
        run_id: str,
        config: HeatConfig,
        *,
        finished: bool = False,
        force_incomplete: bool = False,
    ) -> MetricBundle:
        """Compute full per-round heat metrics and cooling timeline."""
        sim_dir = self.root / run_id
        if not sim_dir.exists():
            raise FileNotFoundError(f"Simulation dir not found: {sim_dir}")

        sim_cfg_path = sim_dir / "simulation_config.json"
        sim_cfg = {}
        if sim_cfg_path.exists():
            try:
                with open(sim_cfg_path, "r", encoding="utf-8") as f:
                    sim_cfg = json.load(f)
            except Exception:
                pass

        time_cfg = sim_cfg.get("time_config", {})
        total_hours = time_cfg.get("total_simulation_hours", 72)
        total_rounds = total_hours * 2
        max_rounds = sim_cfg.get("max_rounds")
        if max_rounds and isinstance(max_rounds, int) and max_rounds < total_rounds:
            total_rounds = max_rounds
        if total_rounds < 1:
            total_rounds = 1

        topic_summary = (
            sim_cfg.get("topic") or sim_cfg.get("topic_id") or config.topic_id
        )

        enabled_platforms: set[Platform] = set()
        for p in ("twitter", "reddit"):
            if (sim_dir / p).exists() or (sim_dir / f"{p}_profiles.csv").exists():
                enabled_platforms.add(p)  # type: ignore[arg-type]
        if not enabled_platforms:
            enabled_platforms = {"twitter"}

        snapshot = read_actions(sim_dir)
        store = TopicLabelStore(sim_dir)
        labels = label_actions(
            snapshot.actions,
            topic_id=config.topic_id,
            topic_summary=topic_summary,
            classifier=self.classifier,
            version=config.classifier_version,
            store=store,
        )
        completion = read_round_completion(sim_dir)
        rounds = aggregate_heat(
            snapshot.actions,
            labels,
            enabled_platforms=enabled_platforms,
            completed_rounds=completion,
            total_rounds=total_rounds,
        )

        if force_incomplete:
            cooling = CoolingSummary(status="incomplete")
        elif finished:
            if snapshot.errors:
                cooling = CoolingSummary(status="incomplete")
            else:
                cooling = calculate_cooling(rounds, config, finished=True)
        else:
            completed_prefix = []
            for r in rounds:
                if all(r.platforms.get(p) is not None for p in enabled_platforms):
                    completed_prefix.append(r)
                else:
                    break
            if snapshot.errors:
                cooling = CoolingSummary(status="incomplete")
            elif not completed_prefix:
                cooling = CoolingSummary(status="provisional")
            else:
                cooling = calculate_cooling(completed_prefix, config, finished=False)

        bundle = MetricBundle(
            run_id=run_id,
            config=config,
            rounds=rounds,
            cooling=cooling,
            final=finished,
            revision=store.revision(),
            errors=snapshot.errors,
        )

        self._save_bundle(run_id, bundle)
        return bundle

    def correct(
        self,
        run_id: str,
        key: tuple[str, Platform, int],
        *,
        related: bool,
        reason: str,
    ) -> TopicLabel:
        """Manually override a topic classification label and update metrics."""
        sim_dir = self.root / run_id
        store = TopicLabelStore(sim_dir)
        label = correct_label(store, key, related=related, reason=reason)

        config = self.get_config(run_id)
        if config:
            self.compute(run_id, config)

        return label

    def request_refresh(
        self,
        run_id: str,
        *,
        finished: bool = False,
        force_incomplete: bool = False,
    ) -> None:
        """Queue a background refresh request coalesced by run_id."""
        with self._task_lock:
            # If already pending, coalesce flags
            old = self._pending_tasks.get(run_id)
            if old:
                finished = finished or old[0]
                force_incomplete = force_incomplete or old[1]
            self._pending_tasks[run_id] = (finished, force_incomplete)
            self._refresh_queue.put((run_id, finished, force_incomplete))

    def _process_refresh_queue(self) -> None:
        while True:
            try:
                run_id, finished, force_incomplete = self._refresh_queue.get()
                with self._task_lock:
                    pending = self._pending_tasks.pop(run_id, None)
                    if pending:
                        finished = finished or pending[0]
                        force_incomplete = force_incomplete or pending[1]

                config = self.get_config(run_id)
                if config:
                    try:
                        self.compute(
                            run_id,
                            config,
                            finished=finished,
                            force_incomplete=force_incomplete,
                        )
                    except Exception as e:
                        logger.error(f"Error computing metrics for {run_id}: {e}")
            except Exception as e:
                logger.error(f"Error in refresh queue worker: {e}")
            finally:
                self._refresh_queue.task_done()


_service_instance: InterventionMetricsService | None = None
_service_lock = threading.Lock()


def get_metrics_service() -> InterventionMetricsService:
    """Get or initialize the global InterventionMetricsService singleton."""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            from app.services.simulation_runner import SimulationRunner

            root = Path(SimulationRunner.RUN_STATE_DIR)
            _service_instance = InterventionMetricsService(root=root)
        return _service_instance

