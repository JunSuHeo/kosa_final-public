from .source_review import source_issues
from .schema import changes, validate_snapshot


def review(before: dict, candidate: dict):
    issues = validate_snapshot(candidate) + source_issues(before, candidate)
    diff = changes(before, candidate)
    removed = [d["key"] for d in diff if d["kind"] == "removed"]
    before_blocks = {b["id"] for w in before["screens"] for b in w["blocks"]}
    after_blocks = {b["id"] for w in candidate["screens"] for b in w["blocks"]}
    removed.extend(sorted(before_blocks - after_blocks))
    if removed:
        issues.append(
            {
                "severity": "warning",
                "target": "snapshot",
                "message": f"기존 항목 {len(removed)}개가 삭제됩니다. 관련 동작을 확인해 주세요.",
            }
        )
    return issues, diff
