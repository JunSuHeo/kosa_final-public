from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID, uuid4
import json
import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg.types.json import Jsonb
from .auth import current_user
from .config import settings
from .db import connect, initialize
from .schema import Snapshot, empty_snapshot
from .review import review
from .role_reviews import (
    Role, ROLES, snapshot_hash, read_report, review_prompt_version,
)

from .source_api import router as source_router, owned_source, ready_basis, model_consent, require_code_consent, source_fingerprint
from .source_review import HANDOFF, source_markdown

User = Annotated[str, Depends(current_user)]


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="기획실 Studio API", version="2.0.0", lifespan=lifespan)


app.include_router(source_router)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(Input):
    id: UUID = Field(default_factory=uuid4)
    idea: str = Field(min_length=3, max_length=8000)
    title: str = Field(default="", max_length=200)
    source_id: UUID | None = None
    code_snapshot_id: UUID | None = None
    forked_from: UUID | None = None
    code_consent: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_source_pair(self):
        if (self.source_id is None) != (self.code_snapshot_id is None):
            raise ValueError("기준 프로젝트와 코드 스냅샷을 함께 지정해 주세요.")
        if not self.source_id and (self.forked_from or self.code_consent):
            raise ValueError("기준 프로젝트를 지정해 주세요.")
        return self


class TitleInput(Input):
    title: str = Field(min_length=1, max_length=200)


class JobInput(Input):
    id: UUID = Field(default_factory=uuid4)
    base_version: int = Field(ge=0)
    kind: Literal["generate", "revise"] = "revise"
    request: str = Field(min_length=1, max_length=8000)
    target_id: str | None = None


class AnswerInput(Input):
    base_version: int = Field(ge=0)
    answers: dict[str, str] = Field(max_length=3)


class ManualInput(Input):
    base_version: int = Field(ge=0)
    snapshot: Snapshot
    summary: str = Field(default="문서 직접 편집", min_length=1, max_length=200)


class DecisionInput(Input):
    expected_version: int = Field(ge=0)
    acknowledge_warnings: bool = False


class LoginInput(Input):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=1024)


def project(c, project_id, owner, lock=False):
    row = c.execute(
        "SELECT * FROM studio_projects WHERE id=%s AND owner_id=%s"
        + (" FOR UPDATE" if lock else ""),
        (project_id, owner),
    ).fetchone()
    if not row:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    return row


def check_version(p, version):
    if p["current_version"] != version:
        raise HTTPException(
            409, "확정 버전이 변경되었습니다. 현재 버전을 불러온 후 다시 시도해 주세요."
        )


def add_job(c, p, inp):
    old = c.execute("SELECT * FROM studio_jobs WHERE id=%s", (inp.id,)).fetchone()
    if old:
        if (
            old["project_id"],
            old["base_version"],
            old["request"],
            old["kind"],
            old["partial"].get("target_id"),
        ) != (p["id"], inp.base_version, inp.request, inp.kind, inp.target_id):
            raise HTTPException(409, "같은 실행 ID가 다른 요청에 사용되었습니다.")
        return old
    check_version(p, inp.base_version)
    if c.execute(
        "SELECT 1 FROM studio_jobs WHERE project_id=%s AND status IN ('queued','running','awaiting_answers','waiting_review')",
        (p["id"],),
    ).fetchone():
        raise HTTPException(409, "진행 중인 실행 또는 검토할 수정안이 있습니다.")
    if c.execute(
        "SELECT 1 FROM studio_proposals WHERE project_id=%s AND status='pending'",
        (p["id"],),
    ).fetchone():
        raise HTTPException(409, "먼저 현재 수정안을 승인하거나 거절해 주세요.")
    if inp.kind == "revise" and not p["current_version"]:
        raise HTTPException(409, "먼저 기획 초안을 생성하고 확정해 주세요.")
    require_code_consent(p)
    s = settings()
    stage = "questions" if inp.kind == "generate" else "revise"
    job = c.execute(
        "INSERT INTO studio_jobs(id,project_id,base_version,kind,status,stage,request,provider,model,ai_mode,partial,code_snapshot_id) "
        "VALUES (%s,%s,%s,%s,'queued',%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            inp.id,
            p["id"],
            inp.base_version,
            inp.kind,
            stage,
            inp.request,
            s.llm_provider,
            s.model,
            s.ai_mode,
            Jsonb({"target_id": inp.target_id}),
            p["code_snapshot_id"],
        ),
    ).fetchone()
    c.execute(
        "INSERT INTO studio_messages(project_id,role,content) VALUES (%s,'user',%s)",
        (p["id"], inp.request),
    )
    return job


@app.get("/health")
def health():
    with connect() as c:
        c.execute("SELECT 1")
    s = settings()
    return {
        "status": "ok",
        "database": "ready",
        "auth_mode": s.auth_mode,
        "ai_mode": s.ai_mode,
        "provider": s.llm_provider,
        "model": s.model,
        "version": "2.0.0",
    }


@app.post("/api/auth/login")
def login(inp: LoginInput):
    s = settings()
    if s.auth_mode != "supabase" or not s.supabase_anon_key:
        raise HTTPException(400, "실제 로그인 환경이 설정되지 않았습니다.")
    try:
        r = httpx.post(
            s.supabase_url.rstrip("/") + "/auth/v1/token?grant_type=password",
            headers={"apikey": s.supabase_anon_key},
            json=inp.model_dump(),
            timeout=20,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "인증 서버에 연결할 수 없습니다.") from None
    if r.status_code != 200:
        raise HTTPException(401, "이메일 또는 비밀번호를 확인해 주세요.")
    data = r.json()
    return {"access_token": data["access_token"], "expires_in": data["expires_in"]}


@app.get("/api/projects")
def projects(owner: User, source_id: UUID | None = None):
    with connect() as c:
        if source_id:
            owned_source(c, source_id, owner)
        return c.execute(
            "SELECT * FROM studio_projects WHERE owner_id=%s "
            + ("AND source_id=%s " if source_id else "")
            + "ORDER BY updated_at DESC",
            (owner, source_id) if source_id else (owner,),
        ).fetchall()


@app.post("/api/projects", status_code=201)
def create_project(inp: ProjectInput, owner: User):
    idea, title = (
        inp.idea.strip(),
        inp.title.strip() or inp.idea.strip().split("\n")[0][:55],
    )
    if len(idea) < 3:
        raise HTTPException(422, "아이디어를 세 글자 이상 입력해 주세요.")
    with connect() as c:
        # Lock even an absent UUID so identical client retries serialize.
        c.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,1))", (str(inp.id),)
        )
        old = c.execute(
            "SELECT * FROM studio_projects WHERE id=%s", (inp.id,)
        ).fetchone()
        if old:
            if old["owner_id"] != owner:
                raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
            if (old["idea"], old["title"], old["source_id"], old["code_snapshot_id"], old["forked_from"]) != (
                idea, title, inp.source_id, inp.code_snapshot_id, inp.forked_from
            ):
                raise HTTPException(
                    409, "같은 프로젝트 ID가 다른 요청에 사용되었습니다."
                )
            return old
        initial = empty_snapshot(title)
        consent = None
        if inp.source_id:
            context = ready_basis(c, inp.source_id, inp.code_snapshot_id, owner, idea)
            consent = model_consent()
            if consent and inp.code_consent != source_fingerprint(context, consent, idea):
                raise HTTPException(409, "모델에 전달할 코드 범위를 확인해 주세요.")
            if inp.forked_from:
                origin = project(c, inp.forked_from, owner)
                if origin["source_id"] != inp.source_id or origin["code_snapshot_id"] == inp.code_snapshot_id:
                    raise HTTPException(409, "같은 저장소의 새 코드 스냅샷으로만 분기할 수 있습니다.")
            initial["source_context"] = context
        p = c.execute(
            "INSERT INTO studio_projects(id,owner_id,title,idea,planning_type,source_id,code_snapshot_id,forked_from,code_model_consent) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (inp.id, owner, title, idea, "existing" if inp.source_id else "new", inp.source_id,
             inp.code_snapshot_id, inp.forked_from, Jsonb(consent) if consent else None),
        ).fetchone()
        c.execute(
            "INSERT INTO studio_revisions(project_id,version,snapshot,summary) VALUES (%s,0,%s,'프로젝트 시작')",
            (p["id"], Jsonb(initial)),
        )
        add_job(c, p, JobInput(base_version=0, kind="generate", request=idea))
        return p


@app.patch("/api/projects/{project_id}")
def rename(project_id: UUID, inp: TitleInput, owner: User):
    if not inp.title.strip():
        raise HTTPException(422, "제목을 입력해 주세요.")
    with connect() as c:
        project(c, project_id, owner, True)
        return c.execute(
            "UPDATE studio_projects SET title=%s,updated_at=now() WHERE id=%s RETURNING *",
            (inp.title.strip(), project_id),
        ).fetchone()


@app.get("/api/projects/{project_id}")
def get_project(project_id: UUID, owner: User):
    with connect() as c:
        p = project(c, project_id, owner)
        revision = c.execute(
            "SELECT * FROM studio_revisions WHERE project_id=%s AND version=%s",
            (project_id, p["current_version"]),
        ).fetchone()
        proposal = c.execute(
            "SELECT * FROM studio_proposals WHERE project_id=%s AND status='pending'",
            (project_id,),
        ).fetchone()
        job = c.execute(
            "SELECT * FROM studio_jobs WHERE project_id=%s ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        messages = c.execute(
            "SELECT * FROM studio_messages WHERE project_id=%s ORDER BY id",
            (project_id,),
        ).fetchall()
        revisions = c.execute(
            "SELECT version,summary,created_at FROM studio_revisions WHERE project_id=%s ORDER BY version DESC",
            (project_id,),
        ).fetchall()
        return {
            "project": p,
            "revision": revision,
            "proposal": proposal,
            "job": job,
            "messages": messages,
            "revisions": revisions,
            "screen_previews": settings().local_screen_previews.get(str(project_id), {}) if p["code_snapshot_id"] else {},
        }


class ReviewInput(Input):
    proposal_id: UUID | None = None
    version: int | None = Field(default=None, ge=1)


class RetryReviewInput(Input):
    role: Role


def review_target(c, p, proposal_id, version, starting=False):
    if (proposal_id is None) == (version is None):
        raise HTTPException(422, "수정안 ID 또는 확정 버전 중 하나를 지정해 주세요.")
    if proposal_id is not None:
        target = c.execute(
            "SELECT * FROM studio_proposals WHERE project_id=%s AND id=%s",
            (p["id"], proposal_id),
        ).fetchone()
        if not target:
            raise HTTPException(404, "수정안을 찾을 수 없습니다.")
        if starting and target["status"] != "pending":
            raise HTTPException(409, "현재 검토 중인 수정안을 선택해 주세요.")
        return f"proposal:{proposal_id}", target["candidate"], target["base_version"]
    target = c.execute(
        "SELECT * FROM studio_revisions WHERE project_id=%s AND version=%s AND version>0",
        (p["id"], version),
    ).fetchone()
    if not target:
        raise HTTPException(404, "확정 버전을 찾을 수 없습니다.")
    return f"revision:{version}", target["snapshot"], version


@app.get("/api/projects/{project_id}/reviews")
def get_role_review(
    project_id: UUID,
    owner: User,
    proposal_id: UUID | None = None,
    version: int | None = None,
):
    with connect() as c:
        p = project(c, project_id, owner)
        key, _, _ = review_target(c, p, proposal_id, version)
        row = c.execute(
            "SELECT id FROM studio_reviews WHERE project_id=%s AND target_key=%s",
            (project_id, key),
        ).fetchone()
        return read_report(c, row["id"]) if row else None


@app.post("/api/projects/{project_id}/reviews", status_code=201)
def start_role_review(project_id: UUID, inp: ReviewInput, owner: User):
    with connect() as c:
        p = project(c, project_id, owner, True)
        key, snapshot, version = review_target(
            c, p, inp.proposal_id, inp.version, starting=True
        )
        old = c.execute(
            "SELECT id FROM studio_reviews WHERE project_id=%s AND target_key=%s",
            (project_id, key),
        ).fetchone()
        if old:
            return read_report(c, old["id"])
        require_code_consent(p)
        s = settings()
        report_id = uuid4()
        c.execute(
            "INSERT INTO studio_reviews(id,project_id,target_key,proposal_id,version,snapshot,snapshot_hash,status,provider,model,ai_mode,prompt_version,code_snapshot_id) VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s,%s,%s,%s)",
            (
                report_id,
                project_id,
                key,
                inp.proposal_id,
                version,
                Jsonb(snapshot),
                snapshot_hash(snapshot),
                s.llm_provider,
                s.model,
                s.ai_mode,
                review_prompt_version(snapshot),
                p["code_snapshot_id"],
            ),
        )
        for role in ROLES:
            c.execute(
                "INSERT INTO studio_review_agents(review_id,role,status) VALUES (%s,%s,'queued')",
                (report_id, role),
            )
        return read_report(c, report_id)


@app.post("/api/projects/{project_id}/reviews/{review_id}/retry")
def retry_role_review(
    project_id: UUID, review_id: UUID, inp: RetryReviewInput, owner: User
):
    with connect() as c:
        project(c, project_id, owner, True)
        report = c.execute(
            "SELECT * FROM studio_reviews WHERE id=%s AND project_id=%s FOR UPDATE",
            (review_id, project_id),
        ).fetchone()
        if not report:
            raise HTTPException(404, "검토 결과를 찾을 수 없습니다.")
        if report["status"] in ("queued", "running"):
            raise HTTPException(409, "진행 중인 역할 검토가 있습니다.")
        row = c.execute(
            "UPDATE studio_review_agents SET status='queued',error=NULL,updated_at=now() WHERE review_id=%s AND role=%s AND status='failed' RETURNING role",
            (review_id, inp.role),
        ).fetchone()
        if not row:
            raise HTTPException(409, "실패한 역할만 재시도할 수 있습니다.")
        c.execute(
            "UPDATE studio_reviews SET status='queued',updated_at=now() WHERE id=%s",
            (review_id,),
        )
        return read_report(c, review_id)


@app.get("/api/projects/{project_id}/revisions/{version}")
def get_revision(project_id: UUID, version: int, owner: User):
    with connect() as c:
        project(c, project_id, owner)
        rev = c.execute(
            "SELECT * FROM studio_revisions WHERE project_id=%s AND version=%s",
            (project_id, version),
        ).fetchone()
        if not rev:
            raise HTTPException(404, "버전을 찾을 수 없습니다.")
        return rev


@app.post("/api/projects/{project_id}/jobs", status_code=201)
def create_job(project_id: UUID, inp: JobInput, owner: User):
    with connect() as c:
        p = project(c, project_id, owner, True)
        return add_job(c, p, inp)


@app.post("/api/projects/{project_id}/jobs/{job_id}/answers")
def answer(project_id: UUID, job_id: UUID, inp: AnswerInput, owner: User):
    with connect() as c:
        p = project(c, project_id, owner, True)
        job = c.execute(
            "SELECT * FROM studio_jobs WHERE id=%s AND project_id=%s FOR UPDATE",
            (job_id, project_id),
        ).fetchone()
        if not job:
            raise HTTPException(404, "실행을 찾을 수 없습니다.")
        check_version(p, inp.base_version)
        if job["base_version"] != inp.base_version:
            raise HTTPException(409, "질문의 기준 버전이 다릅니다.")
        keys = {q["key"] for q in job["questions"]}
        if set(inp.answers) != keys or any(len(v) > 2000 for v in inp.answers.values()):
            raise HTTPException(
                422, "모든 질문에 대한 답변 key를 정확히 전달해 주세요."
            )
        if job["status"] != "awaiting_answers":
            if job["answers"] == inp.answers and job["status"] in {
                "queued",
                "running",
                "waiting_review",
                "completed",
            }:
                return job
            raise HTTPException(409, "답변을 기다리는 실행이 아닙니다.")
        result = c.execute(
            "UPDATE studio_jobs SET answers=%s,status='queued',updated_at=now() WHERE id=%s RETURNING *",
            (Jsonb(inp.answers), job_id),
        ).fetchone()
        text = "\n".join(
            q["title"] + "\n→ " + (inp.answers[q["key"]] or "AI가 가정하고 진행")
            for q in job["questions"]
        )
        c.execute(
            "INSERT INTO studio_messages(project_id,role,content) VALUES (%s,'user',%s)",
            (project_id, text),
        )
        return result


@app.post("/api/projects/{project_id}/jobs/{job_id}/cancel")
def cancel(project_id: UUID, job_id: UUID, owner: User):
    with connect() as c:
        project(c, project_id, owner, True)
        job = c.execute(
            "SELECT * FROM studio_jobs WHERE id=%s AND project_id=%s FOR UPDATE",
            (job_id, project_id),
        ).fetchone()
        if not job:
            raise HTTPException(404, "실행을 찾을 수 없습니다.")
        if job["status"] == "cancelled":
            return job
        if job["status"] not in {"queued", "running", "awaiting_answers"}:
            raise HTTPException(409, "취소할 수 없는 실행입니다.")
        return c.execute(
            "UPDATE studio_jobs SET status='cancelled',updated_at=now() WHERE id=%s RETURNING *",
            (job_id,),
        ).fetchone()


@app.post("/api/projects/{project_id}/proposals", status_code=201)
def manual_edit(project_id: UUID, inp: ManualInput, owner: User):
    candidate = inp.snapshot.model_dump(exclude_unset=True)
    with connect() as c:
        p = project(c, project_id, owner, True)
        check_version(p, inp.base_version)
        if c.execute(
            "SELECT 1 FROM studio_jobs WHERE project_id=%s AND status IN ('running','queued','awaiting_answers')",
            (project_id,),
        ).fetchone():
            raise HTTPException(409, "AI 실행이 끝난 후 직접 편집해 주세요.")
        before = c.execute(
            "SELECT snapshot FROM studio_revisions WHERE project_id=%s AND version=%s",
            (project_id, inp.base_version),
        ).fetchone()["snapshot"]
        issues, diff = review(before, candidate)
        if before.get("source_context") != candidate.get("source_context"):
            raise HTTPException(422, "기획에 고정된 코드 기준과 근거를 변경할 수 없습니다.")
        if not diff:
            raise HTTPException(422, "변경된 내용이 없습니다.")
        c.execute(
            "UPDATE studio_jobs SET status='completed',updated_at=now() WHERE project_id=%s AND status='waiting_review'",
            (project_id,),
        )
        c.execute(
            "UPDATE studio_proposals SET status='superseded' WHERE project_id=%s AND status='pending'",
            (project_id,),
        )
        return c.execute(
            "INSERT INTO studio_proposals(id,project_id,base_version,candidate,summary,issues,diff) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (
                uuid4(),
                project_id,
                inp.base_version,
                Jsonb(candidate),
                inp.summary,
                Jsonb(issues),
                Jsonb(diff),
            ),
        ).fetchone()


@app.post("/api/projects/{project_id}/proposals/{proposal_id}/{decision}")
def decide(
    project_id: UUID,
    proposal_id: UUID,
    decision: Literal["approve", "reject"],
    inp: DecisionInput,
    owner: User,
):
    with connect() as c:
        p = project(c, project_id, owner, True)
        proposal = c.execute(
            "SELECT * FROM studio_proposals WHERE id=%s AND project_id=%s FOR UPDATE",
            (proposal_id, project_id),
        ).fetchone()
        if not proposal:
            raise HTTPException(404, "수정안을 찾을 수 없습니다.")
        wanted = "approved" if decision == "approve" else "rejected"
        if proposal["status"] == wanted:
            return {"status": wanted, "version": proposal["approved_version"]}
        if proposal["status"] != "pending":
            raise HTTPException(409, "이미 처리된 수정안입니다.")
        version = None
        if decision == "approve":
            check_version(p, inp.expected_version)
            if proposal["base_version"] != inp.expected_version:
                raise HTTPException(409, "수정안의 기준 버전이 다릅니다.")
            before = c.execute(
                "SELECT snapshot FROM studio_revisions WHERE project_id=%s AND version=%s",
                (project_id, p["current_version"]),
            ).fetchone()["snapshot"]
            issues, _ = review(before, proposal["candidate"])
            if any(i["severity"] == "blocking" for i in issues):
                raise HTTPException(409, "차단 오류를 먼저 해결해 주세요.")
            if issues and not inp.acknowledge_warnings:
                raise HTTPException(409, "경고와 가정을 확인한 후 승인해 주세요.")
            version = p["current_version"] + 1
            c.execute(
                "INSERT INTO studio_revisions(project_id,version,snapshot,summary) VALUES (%s,%s,%s,%s)",
                (
                    project_id,
                    version,
                    Jsonb(proposal["candidate"]),
                    proposal["summary"],
                ),
            )
            c.execute(
                "UPDATE studio_projects SET current_version=%s,updated_at=now() WHERE id=%s",
                (version, project_id),
            )
        c.execute(
            "UPDATE studio_proposals SET status=%s,approved_version=%s WHERE id=%s",
            (wanted, version, proposal_id),
        )
        if proposal["job_id"]:
            c.execute(
                "UPDATE studio_jobs SET status='completed',updated_at=now() WHERE id=%s",
                (proposal["job_id"],),
            )
        c.execute(
            "INSERT INTO studio_messages(project_id,role,content) VALUES (%s,'assistant',%s)",
            (
                project_id,
                f"v{version}으로 확정했어요. 이 버전을 기준으로 다음 작업을 이어갈 수 있어요."
                if version
                else "수정안을 거절했어요. 확정된 기획은 유지됩니다.",
            ),
        )
        return {"status": wanted, "version": version}


def markdown(s):
    lines = ["# " + s["prd"]["title"], ""]
    for section in s["prd"]["sections"]:
        lines += [f"## {section['title']} ({section['id']})", section["content"], ""]
    lines += [
        "## 사용자 역할",
        ", ".join(s["prd"]["roles"]),
        "## 플랫폼",
        ", ".join(s["prd"]["platforms"]),
        "## 가정",
    ]
    lines += ["- " + a for a in s["prd"]["assumptions"]]
    lines += ["", "# 요구사항"]
    for r in s["requirements"]:
        lines += [f"## [{r['priority']}] {r['id']} {r['title']}", r["description"]] + [
            "- " + a for a in r["acceptance"]
        ]
    lines += ["", "# 기능명세"]
    for f in s["features"]:
        lines += [
            f"## {f['id']} {f['title']}",
            f"요구사항: {f['requirement_id']} · 사용자: {f['actor']}",
            f["description"],
        ]
        for key, label in [
            ("preconditions", "사전 조건"),
            ("steps", "정상 동작"),
            ("exceptions", "예외"),
            ("acceptance", "검수 조건"),
        ]:
            lines += ["### " + label] + ["- " + a for a in f[key]]
    lines += ["", "# 유저플로우"]
    for n in s["flow"]["nodes"]:
        lines += [
            f"- {n['id']} [{n['type']}] {n['title']} · 기능: {', '.join(n['feature_ids'])}"
        ]
    for e in s["flow"]["edges"]:
        lines += [f"- {e['id']}: {e['source']} → {e['target']} {e['label']}"]
    lines += ["", "# 와이어프레임"]
    for w in s["screens"]:
        lines += [
            f"## {w['id']} {w['title']}",
            f"화면 노드: {w['node_id']} · {w['device']}",
        ]
        for b in w["blocks"]:
            lines += [
                f"- {b['id']} [{b['type']}] {b['label']}: {b['content']}"
                + (" → " + b["target_screen_id"] if b["target_screen_id"] else "")
            ]
    return "\n".join(lines + source_markdown(s))


@app.get("/api/projects/{project_id}/revisions/{version}/export")
def export(
    project_id: UUID,
    version: int,
    owner: User,
    format: Literal["json", "markdown"] = "markdown",
):
    rev = get_revision(project_id, version, owner)
    if not version:
        raise HTTPException(409, "아직 확정된 기획이 없습니다.")
    envelope = {
        "project_id": str(project_id),
        "version": version,
        "created_at": rev["created_at"].isoformat(),
        "snapshot": rev["snapshot"],
    }
    if rev["snapshot"].get("source_context"):
        envelope["handoff"] = HANDOFF
    content = (
        json.dumps(envelope, ensure_ascii=False, indent=2)
        if format == "json"
        else f"기획 확정본 v{version}\n\n" + markdown(rev["snapshot"])
    )
    ext, media = (
        ("json", "application/json") if format == "json" else ("md", "text/markdown")
    )
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="studio-v{version}.{ext}"'
        },
    )
