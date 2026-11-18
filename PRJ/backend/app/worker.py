import logging
import time
import uuid
from psycopg.types.json import Jsonb
from .config import settings
from .db import connect, initialize
from .generation import generate
from .review import review
from .repositories import process_analysis

log = logging.getLogger(__name__)
STAGES = ["prd", "features", "flow", "wireframes", "implementation", "validation"]


def artifact_parts(snapshot):
    return (
        snapshot["prd"]["sections"],
        snapshot["requirements"],
        snapshot["features"],
        snapshot["flow"]["nodes"],
        snapshot["screens"],
        snapshot.get("implementation"),
    )


def persist(job_id, **values):
    allowed = {"status", "stage", "questions", "partial", "usage", "error"}
    assert values.keys() <= allowed
    args = [
        Jsonb(v) if k in {"questions", "partial", "usage"} else v
        for k, v in values.items()
    ]
    with connect() as c:
        return (
            c.execute(
                "UPDATE studio_jobs SET "
                + ",".join(k + "=%s" for k in values)
                + ",updated_at=now() WHERE id=%s AND status NOT IN ('cancelled','completed','waiting_review') RETURNING id",
                [*args, job_id],
            ).fetchone()
            is not None
        )


def process(job_id):
    with connect() as lease:
        lease.autocommit = True
        locked = lease.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS locked",
            (str(job_id),),
        ).fetchone()["locked"]
        if not locked:
            return
        try:
            _process(job_id)
        except Exception as exc:
            # Do not log prompts, responses, connection URLs or provider exceptions containing credentials.
            log.warning("generation_failed job=%s type=%s", job_id, type(exc).__name__)
            message = (
                str(exc)
                if isinstance(exc, RuntimeError)
                else "생성 결과를 검증하지 못했습니다. 다시 시도해 주세요."
            )
            persist(job_id, status="failed", error=message[:500])
        finally:
            lease.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s,0))", (str(job_id),)
            )


def _process(job_id):
    with connect() as c:
        job = c.execute("SELECT * FROM studio_jobs WHERE id=%s", (job_id,)).fetchone()
        if not job or job["status"] not in {"queued", "running"}:
            return
        project = c.execute(
            "SELECT * FROM studio_projects WHERE id=%s", (job["project_id"],)
        ).fetchone()
        revision = c.execute(
            "SELECT snapshot FROM studio_revisions WHERE project_id=%s AND version=%s",
            (job["project_id"], job["base_version"]),
        ).fetchone()["snapshot"]
    s = settings()
    if (job["provider"], job["model"], job["ai_mode"]) != (
        s.llm_provider,
        s.model,
        s.ai_mode,
    ):
        raise RuntimeError("실행 후 모델 설정이 바뀌었습니다. 새 실행을 시작해 주세요.")
    if job["code_snapshot_id"] != project["code_snapshot_id"] or (
        job["code_snapshot_id"] and str(job["code_snapshot_id"]) != revision.get("source_context", {}).get("snapshot_id")
    ):
        raise RuntimeError("실행의 코드 기준을 확인할 수 없습니다.")
    if project["current_version"] != job["base_version"]:
        raise RuntimeError(
            "기준 버전이 변경되었습니다. 현재 확정본에서 다시 시작해 주세요."
        )
    if not persist(job_id, status="running"):
        return
    context = {
        "idea": project["idea"],
        "request": job["request"],
        "answers": job["answers"],
        "snapshot": revision,
        "target_id": job["partial"].get("target_id"),
    }
    basis = revision.get("source_context")
    if basis:
        context["snapshot"] = {k: v for k, v in revision.items() if k != "source_context"}
        context["source_context"] = basis
    partial, usage = job["partial"], job["usage"]
    if job["stage"] == "questions":
        result, tokens = generate("questions", context, job)
        with connect() as c:
            updated = c.execute(
                "UPDATE studio_jobs SET status='awaiting_answers',stage='prd',questions=%s,usage=%s,updated_at=now() "
                "WHERE id=%s AND status='running' RETURNING id",
                (Jsonb(result["questions"]), Jsonb(usage + [tokens]), job_id),
            ).fetchone()
            if updated:
                c.execute(
                    "INSERT INTO studio_messages(project_id,role,content) VALUES (%s,'assistant',%s)",
                    (
                        job["project_id"],
                        "제품의 방향을 맞추기 위해 몇 가지만 확인할게요.",
                    ),
                )
        return
    if job["kind"] == "revise":
        candidate, tokens = generate("revise", context, job)
        usage += [tokens]
    else:
        for stage in STAGES[STAGES.index(job["stage"]) :]:
            if stage == "validation" or (stage == "implementation" and not basis):
                break
            with connect() as c:
                state = c.execute(
                    "SELECT status FROM studio_jobs WHERE id=%s", (job_id,)
                ).fetchone()
            if state["status"] == "cancelled":
                return
            result, tokens = generate(stage, {**context, "generated": partial}, job)
            partial[stage] = result
            usage += [tokens]
            if not persist(
                job_id,
                stage=STAGES[STAGES.index(stage) + 1],
                partial=partial,
                usage=usage,
            ):
                return
        candidate = {
            "prd": partial["prd"],
            **partial["features"],
            "flow": partial["flow"],
            **partial["wireframes"],
        }
        if basis:
            candidate["implementation"] = partial["implementation"]
    if basis:
        candidate["source_context"] = basis
    issues, diff = review(revision, candidate)
    if any(i["severity"] == "blocking" for i in issues):
        repaired, tokens = generate(
            "repair", {**context, "snapshot": {k: v for k, v in candidate.items() if k != "source_context"}, "issues": issues}, job
        )
        usage += [tokens]
        if basis:
            repaired["source_context"] = basis
        if all(not original or updated for original, updated in zip(
            artifact_parts(candidate), artifact_parts(repaired)
        )):
            candidate = repaired
            issues, diff = review(revision, candidate)
    blocked = any(issue["severity"] == "blocking" for issue in issues)
    summary = "기획 초안 생성" if job["kind"] == "generate" else job["request"][:160]
    with connect() as c:
        p = c.execute(
            "SELECT * FROM studio_projects WHERE id=%s FOR UPDATE", (job["project_id"],)
        ).fetchone()
        current = c.execute(
            "SELECT * FROM studio_jobs WHERE id=%s FOR UPDATE", (job_id,)
        ).fetchone()
        if current["status"] in {"cancelled", "completed", "waiting_review"}:
            return
        if p["current_version"] != job["base_version"]:
            raise RuntimeError("생성 중 기준 버전이 변경되었습니다.")
        c.execute(
            "INSERT INTO studio_proposals(id,project_id,job_id,base_version,candidate,summary,issues,diff) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(job_id) DO NOTHING",
            (
                uuid.uuid4(),
                p["id"],
                job_id,
                job["base_version"],
                Jsonb(candidate),
                summary,
                Jsonb(issues),
                Jsonb(diff),
            ),
        )
        c.execute(
            "UPDATE studio_jobs SET status='waiting_review',stage='done',usage=%s,updated_at=now() WHERE id=%s",
            (Jsonb(usage), job_id),
        )
        c.execute(
            "INSERT INTO studio_messages(project_id,role,content) VALUES (%s,'assistant',%s)",
            (
                p["id"],
                "초안을 준비했어요. 검토 패널에서 승인 전에 해결할 항목을 확인해 주세요."
                if blocked
                else "PRD부터 와이어프레임까지 연결된 초안을 준비했어요. 내용을 살펴보고 검토 패널에서 확정해 주세요.",
            ),
        )


def main():
    from .role_reviews import process_review
    logging.basicConfig(level=logging.INFO)
    initialize()
    while True:
        with connect() as c:
            analyses = c.execute(
                "SELECT id FROM studio_code_snapshots WHERE status IN ('queued','running') ORDER BY created_at LIMIT 5"
            ).fetchall()
        for analysis in analyses:
            try:
                process_analysis(analysis["id"])
            except Exception:
                log.error("Source analysis interrupted; will resume: %s", analysis["id"])
        with connect() as c:
            jobs = c.execute(
                "SELECT id FROM studio_jobs WHERE status IN ('queued','running') ORDER BY created_at LIMIT 20"
            ).fetchall()
        for job in jobs:
            process(job["id"])
        with connect() as c:
            reviews = c.execute("SELECT id FROM studio_reviews WHERE status IN ('queued','running') ORDER BY created_at LIMIT 20").fetchall()
        for report in reviews:
            try:
                process_review(report["id"])
            except Exception:
                logging.error("Role review interrupted; will resume: %s", report["id"])
        time.sleep(1)


if __name__ == "__main__":
    main()
