from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import Field
from psycopg.types.json import Jsonb

from .auth import current_user
from .config import settings
from .db import connect
from .repositories import RepositoryError, github_url, local_path, planning_context, resolve, schedule
from .role_reviews import snapshot_hash
from .schema import StrictModel, DesignProfile
from .design import extract_design
from .accounts import audit

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


class PublicationPreviewInput(StrictModel):
    design_profile: DesignProfile | None = None


class PublishInput(StrictModel):
    snapshot_id: UUID
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    design_profile: DesignProfile


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


def accessible_source(c, source_id, owner, *, lock=False):
    # Lock the same source row for grants, revocations and new AI requests.
    source = c.execute("SELECT * FROM studio_sources WHERE id=%s" + (" FOR UPDATE" if lock else ""), (source_id,)).fetchone()
    if not source or (source["owner_id"] != owner and not (
        source["publication_id"] and c.execute(
            "SELECT 1 FROM studio_source_assignments WHERE source_id=%s AND account_id=%s", (source_id, owner)
        ).fetchone()
    )):
        raise HTTPException(404, "배정된 업무를 찾을 수 없습니다. 업무 담당자에게 배정을 요청해 주세요.")
    return source


def project_source_access(c, p):
    if not p["source_id"]:
        return {"can_use": True, "can_manage": False}
    source = c.execute("SELECT owner_id,publication_id FROM studio_sources WHERE id=%s", (p["source_id"],)).fetchone()
    manages = bool(source and source["owner_id"] == p["owner_id"])
    assigned = bool(source and source["publication_id"] and c.execute(
        "SELECT 1 FROM studio_source_assignments WHERE source_id=%s AND account_id=%s", (p["source_id"], p["owner_id"])
    ).fetchone())
    return {"can_use": manages or assigned, "can_manage": manages}


def require_project_source(c, p):
    if p["source_id"]:
        accessible_source(c, p["source_id"], p["owner_id"], lock=True)


def source_view(row):
    return {k: v for k, v in row.items() if k != "owner_id"}


def publication_preview(c, source, snapshot_id, profile=None):
    snapshot = code_snapshot(c, source["id"], snapshot_id)
    if snapshot["status"] != "ready":
        raise HTTPException(409, "업무 분석이 준비된 후 게시해 주세요.")
    analysis = snapshot["analysis"]
    profile = profile.model_dump() if profile else extract_design(analysis)
    paths = {entry["path"] for entry in analysis["manifest"]}
    if not set(profile["evidence"]) <= paths:
        raise HTTPException(422, "디자인 근거는 분석된 파일에서만 선택할 수 있습니다.")
    scope = sorted(analysis["manifest"], key=lambda item: item["path"])
    consent = model_consent()
    context = planning_context(source, snapshot, source["name"] + " " + source["description"])
    fingerprint = snapshot_hash([str(source["id"]), str(snapshot_id), scope, consent, profile])
    return {"context": context, "model": consent, "fingerprint": fingerprint,
            "scope": scope, "design_profile": profile}


def published_basis(c, source_id, publication_id, owner, idea):
    source = accessible_source(c, source_id, owner, lock=True)
    publication = c.execute(
        "SELECT * FROM studio_source_publications WHERE id=%s AND source_id=%s",
        (publication_id, source_id),
    ).fetchone()
    if not publication:
        raise HTTPException(404, "게시된 업무를 찾을 수 없습니다.")
    if source["publication_id"] != publication["id"]:
        raise HTTPException(409, "업무 기준이 변경되었습니다. 업무를 다시 선택해 주세요.")
    if publication["consent"] != model_consent():
        raise HTTPException(409, "AI 연결 설정이 변경되었습니다. 업무 연결 설정에서 다시 게시해 주세요.")
    snapshot = code_snapshot(c, source_id, publication["snapshot_id"])
    return planning_context(source, snapshot, idea), publication


@router.get("")
def list_sources(owner: User):
    with connect() as c:
        rows = c.execute(
                "SELECT s.*, cs.commit_sha, cs.analysis_version, cs.status, cs.error, "
                "pub.snapshot_id AS published_snapshot_id, pub.design_profile, pub.consent AS published_model, pub.created_at AS published_at "
                "FROM studio_sources s LEFT JOIN studio_code_snapshots cs ON cs.id=s.current_snapshot_id "
                "LEFT JOIN studio_source_publications pub ON pub.id=s.publication_id "
                "WHERE s.owner_id=%s OR (s.publication_id IS NOT NULL AND EXISTS "
                "(SELECT 1 FROM studio_source_assignments a WHERE a.source_id=s.id AND a.account_id=%s)) "
                "ORDER BY s.created_at DESC", (owner, owner),
            ).fetchall()
        result = []
        for row in rows:
            manages = row["owner_id"] == owner
            # Assignees get publication metadata, never repository paths, errors,
            # analysis or draft settings. Generation reads the approved basis internally.
            view = source_view(row) if manages else {key: row[key] for key in (
                "id", "name", "description", "publication_id", "published_snapshot_id", "published_model", "published_at"
            )}
            result.append({**view, "can_manage": manages})
        return result


@router.get("/{source_id}/assignments")
def list_assignments(source_id: UUID, owner: User):
    with connect() as c:
        owned_source(c, source_id, owner)
        return c.execute("SELECT account_id,created_at FROM studio_source_assignments WHERE source_id=%s ORDER BY created_at", (source_id,)).fetchall()


@router.put("/{source_id}/assignments/{account_id}")
def assign_source(source_id: UUID, account_id: str, owner: User):
    if not 1 <= len(account_id) <= 100 or account_id.strip() != account_id:
        raise HTTPException(422, "계정 식별자를 확인해 주세요.")
    with connect() as c:
        source = owned_source(c, source_id, owner, lock=True)
        if not source["publication_id"]:
            raise HTTPException(409, "게시된 업무만 배정할 수 있습니다.")
        if settings().auth_mode == 'supabase' and not c.execute(
            "SELECT 1 FROM studio_accounts WHERE id=%s AND active AND provisioning_status='ready'", (account_id,)
        ).fetchone():
            raise HTTPException(404, '사용 가능한 계정을 찾을 수 없습니다.')
        changed = c.execute("INSERT INTO studio_source_assignments(source_id,account_id,assigned_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING account_id", (source_id, account_id, owner)).fetchone()
        if changed and settings().auth_mode == 'supabase':
            audit(c, owner, '업무 배정', account_id, source['name'])
        return {"account_id": account_id, "assigned": True}


@router.delete("/{source_id}/assignments/{account_id}")
def unassign_source(source_id: UUID, account_id: str, owner: User):
    with connect() as c:
        source = owned_source(c, source_id, owner, lock=True)
        changed = c.execute("DELETE FROM studio_source_assignments WHERE source_id=%s AND account_id=%s RETURNING account_id", (source_id, account_id)).fetchone()
        if changed and settings().auth_mode == 'supabase':
            audit(c, owner, '업무 배정 해제', account_id, source['name'])
        return {"account_id": account_id, "assigned": False}


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


@router.post("/{source_id}/check")
def check_source(source_id: UUID, tasks: BackgroundTasks, owner: User):
    with connect() as c:
        source = accessible_source(c, source_id, owner)
        if source["owner_id"] != owner:
            return {"scheduled": False}
        updated = c.execute(
            "UPDATE studio_sources SET last_checked_at=now() WHERE id=%s "
            "AND (last_checked_at IS NULL OR last_checked_at < now()-interval '5 minutes') RETURNING id",
            (source_id,),
        ).fetchone()
    if updated:
        tasks.add_task(refresh_source, source_id, owner)
    return {"scheduled": bool(updated)}


@router.post("/{source_id}/snapshots/{snapshot_id}/publication-preview")
def preview_publication(source_id: UUID, snapshot_id: UUID, inp: PublicationPreviewInput, owner: User):
    with connect() as c:
        source = owned_source(c, source_id, owner)
        return publication_preview(c, source, snapshot_id, inp.design_profile)


@router.post("/{source_id}/publish")
def publish_source(source_id: UUID, inp: PublishInput, owner: User):
    with connect() as c:
        source = owned_source(c, source_id, owner, lock=True)
        preview = publication_preview(c, source, inp.snapshot_id, inp.design_profile)
        if preview["fingerprint"] != inp.fingerprint:
            raise HTTPException(409, "코드 범위와 디자인 설정을 다시 확인한 후 게시해 주세요.")
        publication = c.execute(
            "INSERT INTO studio_source_publications(id,source_id,snapshot_id,owner_id,consent,scope,design_profile,fingerprint) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_id,fingerprint) DO NOTHING RETURNING *",
            (uuid4(), source_id, inp.snapshot_id, owner, Jsonb(preview["model"]), Jsonb(preview["scope"]),
             Jsonb(preview["design_profile"]), inp.fingerprint),
        ).fetchone()
        if not publication:
            publication = c.execute("SELECT * FROM studio_source_publications WHERE source_id=%s AND fingerprint=%s", (source_id, inp.fingerprint)).fetchone()
        c.execute("UPDATE studio_sources SET publication_id=%s WHERE id=%s", (publication["id"], source_id))
        return {"id": publication["id"], "snapshot_id": publication["snapshot_id"]}


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
