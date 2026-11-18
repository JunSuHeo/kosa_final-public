from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Section(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    group: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(max_length=12000)


class Prd(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    sections: list[Section] = Field(max_length=30)
    roles: list[str] = Field(max_length=10)
    platforms: list[str] = Field(max_length=6)
    assumptions: list[str] = Field(max_length=20)


class Requirement(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=6000)
    priority: Literal["P0", "P1", "P2"]
    acceptance: list[str] = Field(max_length=12)


class Feature(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    requirement_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=6000)
    actor: str
    preconditions: list[str] = Field(max_length=10)
    steps: list[str] = Field(max_length=15)
    exceptions: list[str] = Field(max_length=10)
    acceptance: list[str] = Field(max_length=12)


class Features(StrictModel):
    requirements: list[Requirement] = Field(max_length=20)
    features: list[Feature] = Field(max_length=40)


class Node(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["start", "screen", "decision", "action", "end"]
    title: str = Field(min_length=1, max_length=160)
    section: str
    feature_ids: list[str] = Field(max_length=10)
    x: float = Field(ge=-10000, le=10000)
    y: float = Field(ge=-10000, le=10000)


class Edge(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    source: str
    target: str
    label: str = Field(max_length=160)


class Flow(StrictModel):
    nodes: list[Node] = Field(max_length=100)
    edges: list[Edge] = Field(max_length=160)


class Block(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    type: Literal[
        "heading", "text", "input", "button", "card", "list", "stat", "navigation"
    ]
    label: str = Field(max_length=500)
    content: str = Field(max_length=3000)
    target_screen_id: str | None


class Screen(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    node_id: str
    title: str = Field(min_length=1, max_length=160)
    device: Literal["mobile", "desktop"]
    blocks: list[Block] = Field(max_length=24)


class Wireframes(StrictModel):
    screens: list[Screen] = Field(max_length=16)


class CodeEvidence(StrictModel):
    id: str
    path: str
    sha256: str
    start_line: int
    end_line: int
    quote: str


class SourceContext(StrictModel):
    source_id: str
    snapshot_id: str
    name: str
    repository: str
    ref: str
    commit_sha: str
    analysis_version: str
    analysis_paths: list[str]
    files_analyzed: int
    excluded: dict[str, int]
    evidence: list[CodeEvidence] = Field(max_length=40)


class AcceptanceCase(StrictModel):
    id: str
    scenario: str = Field(min_length=1, max_length=1500)


class ChangeTask(StrictModel):
    id: str
    requirement_ids: list[str] = Field(min_length=1, max_length=12)
    evidence_ids: list[str] = Field(max_length=12)
    acceptance_ids: list[str] = Field(min_length=1, max_length=12)
    existing_targets: list[str] = Field(max_length=12)
    proposed_targets: list[str] = Field(max_length=12)
    reuse: str = Field(max_length=1500)
    implementation: str = Field(min_length=1, max_length=3000)


class ScopeItem(StrictModel):
    area: str = Field(min_length=1, max_length=300)
    disposition: Literal["apply", "exclude", "unverified"]
    reason: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(max_length=12)


class ImplementationPlan(StrictModel):
    current_behavior: str = Field(min_length=1, max_length=3000)
    proposed_behavior: str = Field(min_length=1, max_length=3000)
    confirmed_policy: list[str] = Field(max_length=16)
    preserve: list[str] = Field(max_length=16)
    exceptions: list[str] = Field(max_length=16)
    assumptions: list[str] = Field(max_length=16)
    unresolved: list[str] = Field(max_length=16)
    scope: list[ScopeItem] = Field(min_length=1, max_length=40)
    tasks: list[ChangeTask] = Field(min_length=1, max_length=25)
    acceptance: list[AcceptanceCase] = Field(min_length=1, max_length=30)


class DraftSnapshot(StrictModel):
    prd: Prd
    requirements: list[Requirement] = Field(max_length=20)
    features: list[Feature] = Field(max_length=40)
    flow: Flow
    screens: list[Screen] = Field(max_length=16)


class SourceDraft(DraftSnapshot):
    implementation: ImplementationPlan


class Snapshot(DraftSnapshot):
    source_context: SourceContext | None = None
    implementation: ImplementationPlan | None = None


class Question(StrictModel):
    key: str
    title: str
    options: list[str] = Field(min_length=2, max_length=5)


class Questions(StrictModel):
    questions: list[Question] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({q.key for q in self.questions}) != len(self.questions):
            raise ValueError("질문 key가 중복되었습니다.")
        return self


class Issue(StrictModel):
    severity: Literal["blocking", "warning"]
    target: str
    message: str


def empty_snapshot(title: str) -> dict:
    return Snapshot(
        prd=Prd(title=title, sections=[], roles=[], platforms=[], assumptions=[]),
        requirements=[],
        features=[],
        flow=Flow(nodes=[], edges=[]),
        screens=[],
    ).model_dump(exclude_unset=True)


def validate_snapshot(snapshot: dict) -> list[dict]:
    s = Snapshot.model_validate(snapshot)
    issues = []

    def issue(target, message, severity="blocking"):
        issues.append(
            Issue(severity=severity, target=target, message=message).model_dump()
        )

    collections = [
        s.prd.sections,
        s.requirements,
        s.features,
        s.flow.nodes,
        s.flow.edges,
        s.screens,
    ]
    ids = [x.id for items in collections for x in items] + [
        b.id for x in s.screens for b in x.blocks
    ]
    if len(ids) != len(set(ids)):
        issue("snapshot", "항목 ID가 중복되었습니다.")
    reqs = {r.id for r in s.requirements}
    features = {f.id for f in s.features}
    nodes = {n.id: n for n in s.flow.nodes}
    screens = {w.id for w in s.screens}
    for f in s.features:
        if f.requirement_id not in reqs:
            issue(f.id, "연결된 요구사항을 찾을 수 없습니다.")
        if f.actor not in s.prd.roles:
            issue(f.id, "PRD에 정의되지 않은 사용자 역할입니다.")
        if not f.exceptions:
            issue(f.id, "예외 동작을 보강해 주세요.", "warning")
        if not f.acceptance:
            issue(f.id, "검수 조건이 비어 있습니다.", "warning")
    for n in s.flow.nodes:
        if set(n.feature_ids) - features:
            issue(n.id, "연결된 기능을 찾을 수 없습니다.")
    for e in s.flow.edges:
        if e.source not in nodes or e.target not in nodes:
            issue(e.id, "흐름 연결의 시작 또는 도착 노드가 없습니다.")
    if s.flow.nodes:
        starts = {n.id for n in s.flow.nodes if n.type == "start"}
        if not starts or not any(n.type == "end" for n in s.flow.nodes):
            issue("flow", "흐름에 시작과 종료 노드가 필요합니다.")
        reached = set(starts)
        for _ in range(len(nodes)):
            expanded = reached | {
                e.target
                for e in s.flow.edges
                if e.source in reached and e.target in nodes
            }
            if expanded == reached:
                break
            reached = expanded
        for n in s.flow.nodes:
            if starts and n.id not in reached:
                issue(n.id, "시작점에서 도달할 수 없는 흐름 노드입니다.")
            if n.type == "decision":
                outgoing = [e for e in s.flow.edges if e.source == n.id]
                if len(outgoing) < 2 or any(not e.label.strip() for e in outgoing):
                    issue(
                        n.id, "분기에는 조건을 표시한 두 개 이상의 경로가 필요합니다."
                    )
    for w in s.screens:
        if w.node_id not in nodes or nodes[w.node_id].type != "screen":
            issue(w.id, "와이어프레임이 유효한 화면 노드에 연결되어야 합니다.")
        for b in w.blocks:
            if b.target_screen_id and b.target_screen_id not in screens:
                issue(b.id, "이동 대상 와이어프레임이 없습니다.")
    if (
        not s.prd.sections
        or not s.requirements
        or not s.features
        or not s.flow.nodes
        or not s.screens
    ):
        issue("snapshot", "PRD·요구사항·기능·흐름·와이어프레임을 모두 작성해 주세요.")
    if s.prd.assumptions:
        issue("prd", "확인이 필요한 가정이 포함되어 있습니다.", "warning")
    return issues


def changes(before: dict, after: dict) -> list[dict]:
    def flatten(s):
        out = {
            "prd:roles": s["prd"]["roles"],
            "prd:platforms": s["prd"]["platforms"],
            "prd:assumptions": s["prd"]["assumptions"],
            "prd:title": s["prd"]["title"],
        }
        for prefix, items in [
            ("prd", s["prd"]["sections"]),
            ("requirement", s["requirements"]),
            ("feature", s["features"]),
            ("node", s["flow"]["nodes"]),
            ("edge", s["flow"]["edges"]),
            ("screen", s["screens"]),
        ]:
            for item in items:
                out[prefix + ":" + item["id"]] = item
        if s.get("implementation"):
            out["implementation"] = s["implementation"]
        return out

    a, b = flatten(before), flatten(after)
    return [
        {
            "key": k,
            "kind": "added" if k not in a else "removed" if k not in b else "changed",
            "before": a.get(k),
            "after": b.get(k),
        }
        for k in sorted(a.keys() | b.keys())
        if a.get(k) != b.get(k)
    ]
