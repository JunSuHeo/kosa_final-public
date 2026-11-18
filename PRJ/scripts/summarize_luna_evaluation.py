"""Build a reproducible structural/cost summary and a separate human score sheet."""

import json
from pathlib import Path
from evaluate_luna import ROOT, usage

records = [json.loads(p.read_text()) for p in sorted(ROOT.glob("*.json"))]
summary = {"expected_runs": 6, "finished_runs": sum(bool(r.get("finished")) for r in records), "runs": []}
rows = []
human = ["# Luna 사람 품질 평가", "", "평가 조건과 점수 기준은 [evaluation-plan.md](evaluation-plan.md)를 따른다. 아래 빈칸은 실제 사용자가 채운다. 자동 구조 검사와 별개이며 미작성은 미평가다.", "", "| 실행 | 요청 반영 1~5 | 일관성 1~5 | 사용 가능성 1~5 | 검토 타당성 1~5 | 근거와 사유 |", "| --- | --- | --- | --- | --- | --- |"]
for r in records:
    calls = usage(r)
    agents = r.get("review", {}).get("agents", [])
    unknown = sum(a["status"] == "failed" and not a.get("usage") for a in agents)
    unknown += sum(r.get(stage, {}).get("job", {}).get("status") == "failed" for stage in ("generation", "revision"))
    known = sum(c.get("tokens", {}).get("cost") or 0 for c in calls)
    entry = {"case": r["case"], "project_id": r["project_id"], "finished": bool(r.get("finished")), "structural_pass": r.get("structural_pass"), "checks": r.get("checks", {}), "reported_calls": len(calls), "unreported_failed_calls": unknown, "reported_cost_usd_lower_bound": round(known, 8), "reported_tokens_lower_bound": sum(c.get("tokens", {}).get("total_tokens", 0) for c in calls), "elapsed_seconds": r.get("elapsed_seconds"), "failed_roles": [a["role"] for a in agents if a["status"] == "failed"], "human_review": r.get("human_review")}
    summary["runs"].append(entry)
    rows.append(f"| {r['case']} | {'통과' if r.get('structural_pass') else '실패' if r.get('finished') else '진행 중'} | {entry['reported_calls']} | {unknown} | {known:.6f} | {r.get('elapsed_seconds', '—')} |")
    human.append(f"| {r['case']} | 미평가 | 미평가 | 미평가 | 미평가 | |")
summary["structural_passes"] = sum(r["structural_pass"] is True for r in summary["runs"])
summary["reported_cost_usd_lower_bound"] = round(sum(r["reported_cost_usd_lower_bound"] for r in summary["runs"]), 8)
summary["unreported_failed_calls"] = sum(r["unreported_failed_calls"] for r in summary["runs"])
summary["reported_calls"] = sum(r["reported_calls"] for r in summary["runs"])
summary["reported_tokens_lower_bound"] = sum(r["reported_tokens_lower_bound"] for r in summary["runs"])
summary["exact_edit_passes"] = sum(r.get("checks", {}).get("exact_edit") is True for r in records)
summary["completed_roles"] = sum(a["status"] == "completed" for r in records for a in r.get("review", {}).get("agents", []))
summary["human_review_complete"] = len(records) == 6 and all(r.get("human_review") is not None for r in records)
feedback_path = Path("docs/luna-user-feedback.json")
if feedback_path.exists():
    summary["overall_user_feedback"] = json.loads(feedback_path.read_text())
Path("docs/luna-evaluation-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
report = ["# Luna 반복 평가 결과", "", "실제 OpenRouter 호출, 3개 도메인 × 2회. 실패 사례를 포함하며 사람 품질 평가는 별도다.", "", "| 실행 | 구조 결과 | 보고 호출 수 | 비용 미확인 실패 수 | 보고 비용 USD 하한 | 시간(초) |", "| --- | --- | --- | --- | --- | --- |", *rows, "", f"완료 {summary['finished_runs']}/6, 구조 통과 {summary['structural_passes']}/6. 공급자 보고 비용 합계 하한 US${summary['reported_cost_usd_lower_bound']:.6f}, 비용 미확인 실패 {summary['unreported_failed_calls']}회.", "", f"요청 필드만 수정 {summary['exact_edit_passes']}/6, 역할 검토 최초 완료 {summary['completed_roles']}/30. 저장된 usage {summary['reported_calls']}회, 보고 토큰 하한 {summary['reported_tokens_lower_bound']:,}개. 비용 미확인 실패를 포함한 실제 호출은 {summary['reported_calls'] + summary['unreported_failed_calls']}회다.", "", "근거 검증 실패 역할은 현재 서버가 usage를 저장하지 않아 전체 실제 청구액을 확정할 수 없다. 실패 역할의 호출 수와 비용을 0으로 간주하지 않는다. 예산 예약액은 실제 비용으로 집계하지 않는다.", "", "단일 Luna smoke·역할 재시도는 이 6회 평가와 별도다. [원시 집계](luna-evaluation-summary.json), [사람 평가표](luna-human-review.md)."]
Path("docs/luna-evaluation-report.md").write_text("\n".join(report) + "\n")
if "overall_user_feedback" in summary:
    with Path("docs/luna-evaluation-report.md").open("a") as output:
        feedback = summary["overall_user_feedback"]
        output.write(f"\n사용자 총평: {feedback['score']}/{feedback['scale_max']}점. {feedback['comment']}. 전체 결과 점수이며 실행별·항목별 점수는 아니다. [총평 기록](luna-user-feedback.json).\n")
for r in records:
    human += ["", "## " + r["case"], "", f"[제품에서 조회](http://localhost:5174/?project={r['project_id']}) · [동결 실행 근거](luna-evaluation/{r['case']}.json)", "", r["idea"], ""]
    snapshot = r.get("generation", {}).get("proposal", {})
    if snapshot:
        human += ["생성 기능: " + ", ".join(f["title"] for f in snapshot["candidate"]["features"]), ""]
    human += ["구조 검사: " + json.dumps(r.get("checks", {}), ensure_ascii=False), ""]
    for agent in r.get("review", {}).get("agents", []):
        human += [f"### {agent['role']} ({agent['status']})", ""]
        if agent.get("error"):
            human += [agent["error"], ""]
        for finding in (agent.get("result") or {}).get("findings", []):
            human += ["- " + finding["title"], "  - 근거: " + "; ".join(f"{e['target_id']}: {e['quote']}" for e in finding["evidence"]), "  - 이유: " + finding["rationale"], "  - 제안: " + finding["recommendation"]]
# Do not overwrite scores already entered by the user.
human_path = Path("docs/luna-human-review.md")
if not human_path.exists():
    human_path.write_text("\n".join(human) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, ensure_ascii=False))
