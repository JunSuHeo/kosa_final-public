from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .auth import current_user
from .config import settings
from .db import connect
from .repositories import RepositoryError, github_url, local_path, planning_context, resolve, schedule
from .role_reviews import snapshot_hash
from .schema import StrictModel

router = APIRouter(prefix="/api/sources")
User = Annotated[str, Depends(current_user)]


class SourceInput(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=1000)
    kind: Literal["local", "github"]
    repository: str = Field(min_length=1, max_length=300)
    ref: str = Field(min_length=1, max_length=250)
    analysis_paths: list[str] = Field(default_factory=list, max_length=12)


class PreviewInput(StrictModel):
    idea: str = Field(min_length=3, max_length=8000)


def owned_source(c, source_id, owner, *, lock=False):
    source = c.execute(
        "SELECT * FROM studio_sources WHERE id=%s AND owner_id=%s" + (" FOR UPDATE" if lock else ""),
        (source_id, owner),
    ).fetchone()
    if not source:
        raise HTTPException(404, "기준 프로젝트를 찾을 수 없습니다.")
    return source


def code_snapshot(c, source_id, snapshot_id):
    result = c.execute(
        "SELECT * FROM studio_code_snapshots WHERE id=%s AND source_id=%s",
        (snapshot_id, source_id),
    ).fetchone()
    if not result:
        raise HTTPException(404, "코드 스냅샷을 찾을 수 없습니다.")
    return result


def ready_basis(c, source_id, snapshot_id, owner, idea):
    source = owned_source(c, source_id, owner)
    snapshot = code_snapshot(c, source_id, snapshot_id)
    if snapshot["status"] != "ready":
        raise HTTPException(409, "코드 분석이 준비된 후 기획을 시작해 주세요.")
    return planning_context(source, snapshot, idea)


def source_fingerprint(context, consent, idea):
    return snapshot_hash([context, consent, idea])


def model_consent():
    s = settings()
    return {"provider": s.llm_provider, "model": s.model} if s.ai_mode == "live" else None


def require_code_consent(project):
    consent = model_consent()
    if consent and project["code_snapshot_id"] and project["code_model_consent"] != consent:
        raise HTTPException(409, "현재 AI 설정에서 코드 전송을 확인한 새 기획 작업을 시작해 주세요.")


def source_view(row):
    return {k: v for k, v in row.items() if k != "owner_id"}


@router.get("")
def list_sources(owner: User):
    with connect() as c:
        return [
            source_view(row) for row in c.execute(
                "SELECT s.*, cs.commit_sha, cs.analysis_version, cs.status, cs.error "
                "FROM studio_sources s LEFT JOIN studio_code_snapshots cs ON cs.id=s.current_snapshot_id "
                "WHERE s.owner_id=%s ORDER BY s.created_at DESC", (owner,),
            )
        ]


@router.post("", status_code=201)
def register_source(inp: SourceInput, owner: User):
    try:
        repository = (github_url(inp.repository.strip()) if inp.kind == "github"
                      else local_path(inp.repository.strip()).relative_to(
                          settings().local_repository_root_resolved
                      ).as_posix())
    except RepositoryError as error:
        raise HTTPException(422, str(error)) from None
    paths = []
    for value in inp.analysis_paths:
        value = value.strip()
        parts = PurePosixPath(value).parts
        if (not parts or value.startswith("/") or ".." in parts or len(value) > 200
                or any(ch in value for ch in ("\\", "\0", "\n", "\r"))):
            raise HTTPException(422, "분석 우선 경로는 저장소 내부의 상대 경로여야 합니다.")
        paths.append(PurePosixPath(value).as_posix())
    name, ref = inp.name.strip(), inp.ref.strip()
    if not name or not ref:
        raise HTTPException(422, "이름과 브랜치를 입력해 주세요.")
    with connect() as c:
        result = c.execute(
            "INSERT INTO studio_sources(id,owner_id,name,description,kind,repository,ref,analysis_paths) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (owner_id,kind,repository,ref) DO NOTHING RETURNING *",
            (uuid4(), owner, name, inp.description.strip(), inp.kind, repository, ref, paths),
        ).fetchone()
        if not result:
            raise HTTPException(409, "이미 같은 저장소와 브랜치가 등록되었습니다.")
        return source_view(result)


@router.post("/{source_id}/analyze")
def refresh_source(source_id: UUID, owner: User):
    with connect() as c:
        source = owned_source(c, source_id, owner, lock=True)
        try:
            sha, dirty = resolve(source)
        except (RepositoryError, OSError) as error:
            message = str(error) if isinstance(error, RepositoryError) else "저장소에 접근할 수 없습니다."
            c.execute("UPDATE studio_sources SET last_error=%s WHERE id=%s", (message, source_id))
            return {"status": "failed", "error": message}
        snapshot = schedule(c, source, sha, dirty)
        c.execute(
            "UPDATE studio_sources SET current_snapshot_id=%s,last_error=NULL,working_tree_dirty=%s WHERE id=%s",
            (snapshot["id"], dirty, source_id),
        )
        return snapshot


@router.get("/{source_id}/snapshots/{snapshot_id}")
def snapshot_detail(source_id: UUID, snapshot_id: UUID, owner: User):
    with connect() as c:
        owned_source(c, source_id, owner)
        snapshot = code_snapshot(c, source_id, snapshot_id)
        analysis = snapshot.pop("analysis")
        if analysis:
            snapshot["analysis"] = {k: v for k, v in analysis.items() if k != "files"}
        return snapshot


@router.post("/{source_id}/snapshots/{snapshot_id}/preview")
def preview(source_id: UUID, snapshot_id: UUID, inp: PreviewInput, owner: User):
    with connect() as c:
        context = ready_basis(c, source_id, snapshot_id, owner, inp.idea.strip())
    consent = model_consent()
    return {"context": context, "model": consent, "fingerprint": source_fingerprint(context, consent, inp.idea.strip())}


@router.post("/{source_id}/snapshots/{snapshot_id}/retry")
def retry_analysis(source_id: UUID, snapshot_id: UUID, owner: User):
    with connect() as c:
        owned_source(c, source_id, owner)
        code_snapshot(c, source_id, snapshot_id)
        result = c.execute(
            "UPDATE studio_code_snapshots SET status='queued',error=NULL WHERE id=%s AND status='failed' RETURNING id,status",
            (snapshot_id,),
        ).fetchone()
        if not result:
            raise HTTPException(409, "실패한 분석만 재시도할 수 있습니다.")
        return result
