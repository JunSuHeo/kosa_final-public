"""Validation and export for repository-based implementation plans."""

HANDOFF = (
    "작업 공간의 저장소와 HEAD, 미커밋 변경을 먼저 확인하세요. "
    "현재 HEAD와 문서의 기준 커밋이 다르면 영향 파일과 명세 차이를 확인한 뒤 구현하세요. "
    "사용자 변경을 보존하고 과거 커밋으로 강제 이동하지 마세요."
)


def source_issues(before, candidate):
    basis = before.get("source_context")
    plan = candidate.get("implementation")
    issues = []

    def add(target, message, severity="blocking"):
        issues.append({"target": target, "message": message, "severity": severity})

    if basis != candidate.get("source_context") or (not basis and plan):
        add("source_context", "기획에 고정된 코드 기준과 근거를 변경할 수 없습니다.")
    if not basis:
        return issues
    if not plan:
        add("implementation", "기준 프로젝트의 구현 지침이 필요합니다.")
        return issues

    evidence = {item["id"]: item for item in basis["evidence"]}
    requirements = {item["id"] for item in candidate["requirements"]}
    acceptance = {item["id"] for item in plan["acceptance"]}
    task_ids = {task["id"] for task in plan["tasks"]}
    planning_ids = {
        item["id"] for item in (
            candidate["prd"]["sections"] + candidate["requirements"] + candidate["features"]
            + candidate["flow"]["nodes"] + candidate["flow"]["edges"] + candidate["screens"]
            + [block for screen in candidate["screens"] for block in screen["blocks"]]
        )
    }
    if (evidence.keys() | planning_ids) & (task_ids | acceptance) or (
        "source-implementation" in planning_ids | task_ids | acceptance or evidence.keys() & planning_ids
    ):
        add("implementation", "기획, 코드 근거와 구현 지침의 ID는 서로 달라야 합니다.")
    if (len(acceptance) != len(plan["acceptance"]) or len(task_ids) != len(plan["tasks"])
            or acceptance & task_ids or "" in acceptance | task_ids):
        add("implementation", "구현 작업과 수용 기준 ID는 비어 있지 않고 서로 달라야 합니다.")
    covered = set()
    for task in plan["tasks"]:
        refs = set(task["evidence_ids"])
        if refs - evidence.keys():
            add(task["id"], "이 코드 스냅샷에 없는 근거 ID입니다.")
        if set(task["requirement_ids"]) - requirements or set(task["acceptance_ids"]) - acceptance:
            add(task["id"], "요구사항 또는 수용 기준 ID를 찾을 수 없습니다.")
        covered.update(task["acceptance_ids"])
        for target in task["existing_targets"]:
            path, _, symbol = target.partition("#")
            matches = [evidence[k] for k in refs & evidence.keys() if evidence[k]["path"] == path]
            if not matches or (symbol and not any(symbol in item["quote"] for item in matches)):
                add(task["id"], "기존 파일 또는 심볼이 연결된 원문 근거와 일치하지 않습니다.")
        if not refs or not task["existing_targets"]:
            add(task["id"], "관련 기존 코드를 확인해야 구현 준비가 완료됩니다.", "warning")
    if acceptance - covered:
        add("implementation", "모든 수용 기준을 구현 작업에 연결해 주세요.")
    if basis["excluded"].get("analysis_limit") or basis["excluded"].get("tree_truncated"):
        add("implementation", "분석 상한으로 읽지 못한 코드가 있습니다.", "warning")
    for area in plan["scope"]:
        if set(area["evidence_ids"]) - evidence.keys():
            add("implementation", "적용 목록에 이 코드 스냅샷에 없는 근거 ID가 있습니다.")
        if not area["evidence_ids"] and area["disposition"] != "unverified":
            add("implementation", "적용 또는 제외를 확정할 코드 근거가 필요합니다.", "warning")
    if plan["unresolved"] or plan["assumptions"] or any(s["disposition"] == "unverified" for s in plan["scope"]):
        add("implementation", "추정 또는 확인이 필요한 범위가 있습니다.", "warning")
    return issues


def source_markdown(snapshot):
    source = snapshot.get("source_context")
    if not source:
        return []
    plan = snapshot["implementation"]
    issues = source_issues(snapshot, snapshot)
    lines = [
        "", "# 코딩 도구 인계", "", HANDOFF, "",
        f"- 기준 프로젝트: {source['name']}",
        f"- 저장소: {source['repository']}",
        f"- 기준 커밋: `{source['commit_sha']}`",
        f"- 분석: {source['snapshot_id']} · {source['analysis_version']} · {source['files_analyzed']}개 파일",
        f"- 근거: 선택 발췌 {len(source['evidence'])}개 · 분석 제외 {sum(source['excluded'].values())}개",
        "- 근거 및 미결정 확인 필요" if issues else "- 구조와 인용 검증 통과",
        "", "## 현재 동작", plan["current_behavior"], "## 변경 후 동작", plan["proposed_behavior"],
    ]
    for key, label in (
        ("confirmed_policy", "확정 정책"), ("preserve", "유지 조건"), ("exceptions", "예외"),
        ("assumptions", "추정"), ("unresolved", "미결정"),
    ):
        lines += ["", "## " + label] + ["- " + item for item in plan[key]]
    lines += ["", "## 적용 목록"]
    for item in plan["scope"]:
        lines.append(f"- {item['area']} [{item['disposition']}] {item['reason']} ({', '.join(item['evidence_ids'])})")
    lines += ["", "## 구현 순서"]
    for task in plan["tasks"]:
        lines += [
            "", f"### {task['id']}", task["implementation"],
            "- 기존 대상 " + ", ".join(task["existing_targets"]),
            "- 신규 제안 " + ", ".join(task["proposed_targets"]),
            "- 재사용 " + task["reuse"],
            "- 요구사항 " + ", ".join(task["requirement_ids"]),
            "- 근거 " + ", ".join(task["evidence_ids"]),
            "- 수용 기준 " + ", ".join(task["acceptance_ids"]),
        ]
    lines += ["", "## 수용 테스트"]
    for item in plan["acceptance"]:
        lines.append(f"- {item['id']} {item['scenario']}")
    used = {code for item in plan["tasks"] + plan["scope"] for code in item["evidence_ids"]}
    lines += ["", "## 코드 근거"]
    for item in source["evidence"]:
        if item["id"] in used:
            lines += [
                "", f"### {item['id']}",
                f"{item['path']}:{item['start_line']}–{item['end_line']} · SHA-256 {item['sha256']}",
                "", *(f"    {line}" for line in item["quote"].split("\n")), "",
            ]
    return lines
