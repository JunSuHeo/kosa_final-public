"""Thin controller connecting existing generation/validation and publication."""

import copy
from pathlib import Path

from . import evidence, run, publish, workspace
from .codex_adapter import ExecutionError


STAGES = ("configuration", "environment", "prepare", "codex", "collect", "validation", "publication")


def execute_workflow(config_path: Path, task: str, repo_root: Path, results_dir: Path, *,
                     publish_mode="simulate", issue=None, adapter=None, test_executor=None,
                     simulation_github=None, simulation_git=None, issue_context=None, stage_callback=None):
    if publish_mode not in ("simulate", "prepare", "real"):
        raise ValueError("Unknown publication mode")
    if publish_mode != "simulate" and (simulation_github is not None or simulation_git is not None):
        raise ValueError("Simulation dependencies cannot be used in another mode")
    generation = run.execute_request(config_path, task, repo_root, results_dir,
                                     adapter=adapter, test_executor=test_executor, stop_on_failure=True,
                                     issue_context=issue_context, stage_callback=stage_callback)
    result = copy.deepcopy(generation)
    result.update(execution_id=generation["run_id"], project_name=generation["project_id"],
                  workflow_mode=publish_mode, workflow_status="failed", workflow_result_path=None,
                  publication={"status": "not_run", "attempted": False, "pr_url": None})
    if ((generation["final_status"] == "completed" and generation["validation_status"] == "passed")
            or (generation["final_status"] == "validation_failed"
                and generation.get("publish_on_test_failure", generation.get("draft_on_test_failure")))):
        stage = {"name": "publication", "status": "running", "started_at": run._now(), "ended_at": None}
        result["stages"].append(stage)
        # Pass only sealed evidence to the existing publisher. Simulated adapters
        # are enforced by that module; no caller-supplied real transport is used.
        try:
            if stage_callback is not None:
                stage_callback("publication", generation)
            publication = publish.publish(Path(generation["result_path"]), config_path, repo_root,
                                          simulate=publish_mode == "simulate", execute=publish_mode == "real",
                                          issue=issue, github=simulation_github, network_git=simulation_git,
                                          publication_guard=(lambda: stage_callback("publication_check", generation))
                                          if stage_callback is not None else None)
            result["publication"] = publication
            success = (publication["status"] == {"simulate": "simulated", "prepare": "prepared", "real": "published"}[publish_mode]
                       and not publication["blocked_reasons"])
            stage.update(status="passed" if success else "failed", ended_at=run._now())
            if success:
                result["final_status"] = "completed"
                result["workflow_status"] = {"simulate": "completed_simulation", "prepare": "prepared", "real": "published"}[publish_mode]
            else:
                result["final_status"] = ("approval_invalidated" if any(reason.get("status") == "approval_invalidated"
                                          for reason in publication["blocked_reasons"]) else "publication_failed")
                result["errors"].extend(publication["blocked_reasons"])
        except ExecutionError as exc:
            stage.update(status="failed", ended_at=run._now())
            result["final_status"] = exc.status
            result["errors"].append({"status": exc.status, "message": workspace.redact(str(exc))})
        except Exception:
            stage.update(status="failed", ended_at=run._now())
            result["final_status"] = "publication_failed"
            result["publication"] = {"status": "outcome_unknown" if publish_mode == "real" else "failed",
                                      "attempted": publish_mode == "real", "pr_url": None}
            result["errors"].append({"status": "publication_failed", "message": "Publication orchestration failed; raw details are withheld."})
    recorded = {stage["name"] for stage in result["stages"]}
    result["stages"].extend({"name": name, "status": "not_run", "started_at": None, "ended_at": None}
                            for name in STAGES if name not in recorded)
    result["ended_at"] = run._now()
    if generation["result_path"] is not None:
        directory = Path(generation["result_path"]).parent
        result["workflow_result_path"] = str(directory / "workflow.json")
        try:
            evidence.save_json(directory, "workflow.json", result)
        except (OSError, TypeError, ValueError):
            result.update(final_status="result_collection_failed", workflow_status="failed", workflow_result_path=None)
            result["errors"].append({"status": "result_collection_failed", "message": "Unified workflow result could not be saved."})
    return result
