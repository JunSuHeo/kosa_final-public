import copy
import json
from pathlib import Path
import httpx
from .config import settings
from .schema import Questions, Prd, Features, Flow, Wireframes, DraftSnapshot, SourceDraft, ImplementationPlan, Discussion, DiscussionV1

class ModelError(RuntimeError):
    """Sanitized message safe to show in the UI."""

    def __init__(self, message, *, usage=None):
        super().__init__(message)
        self.usage = usage


PROMPT_VERSION = "studio.v1"
STAGE_MODELS = {
    "discuss": Discussion,
    "questions": Questions,
    "prd": Prd,
    "features": Features,
    "flow": Flow,
    "wireframes": Wireframes,
    "implementation": ImplementationPlan,
    "revise": DraftSnapshot,
    "repair": DraftSnapshot,
}


def strict_schema(model):
    schema = model.model_json_schema()

    def walk(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object":
                value["additionalProperties"] = False
                value["required"] = list(value.setdefault("properties", {}))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(schema)
    return schema


def generate(stage: str, context: dict, job: dict):
    source = context.get("source_context")
    result_model = SourceDraft if source and stage in {"revise", "repair"} else STAGE_MODELS[stage]
    version = job.get("prompt_version", PROMPT_VERSION)
    if stage == "discuss" and version != "business.v2":
        result_model = DiscussionV1
    if job["ai_mode"] == "mock":
        result = mock_result(stage, context)
        if stage == "discuss" and version != "business.v2":
            result.pop("questions", None)
        return result_model.model_validate(result).model_dump(), {"mode": "mock", "stage": stage}
    if version not in {"studio.v1", "business.v1", "business.v2"}:
        raise ModelError("지원되지 않는 기획 지침 버전입니다. 새 대화를 시작해 주세요.")
    prompt_file = Path(__file__).resolve().parents[2] / f"prompts/{version}.md"
    if not prompt_file.exists():
        prompt_file = Path(f"/prompts/{version}.md")
    system = (
        prompt_file.read_text()
        + "\n현재 단계: "
        + stage
        + ". 이 단계의 schema에 해당하는 결과만 반환하세요."
    )
    if source:
        source_prompt = prompt_file.with_name("source.v1.md")
        system += "\n" + source_prompt.read_text()
    return structured_completion(stage, context, job, system, result_model, version)


def structured_completion(stage, context, job, system, result_model, prompt_version, max_tokens=16000):
    s = settings()
    if (job["provider"], job["model"], job["ai_mode"]) != (
        s.llm_provider,
        s.model,
        s.ai_mode,
    ):
        raise ModelError("모델 설정이 바뀌었습니다. 새 실행을 시작해 주세요.")
    payload = json.dumps(context, ensure_ascii=False)
    schema = strict_schema(result_model)
    headers = {
        "Authorization": "Bearer " + s.api_key,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=s.llm_timeout_seconds) as client:
        if s.llm_provider == "openrouter":
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": job["model"],
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": payload},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": stage,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    "max_tokens": max_tokens,
                    "reasoning": {"effort": "low"},
                    "provider": {"require_parameters": True},
                },
            )
        else:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json={
                    "model": job["model"],
                    "instructions": system,
                    "input": payload,
                    "store": False,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": stage,
                            "strict": True,
                            "schema": schema,
                        }
                    },
                    "max_output_tokens": max_tokens,
                    "reasoning": {"effort": "low"},
                },
            )
    if response.status_code >= 400:
        raise ModelError(
            f"모델 공급자 응답 오류 (HTTP {response.status_code}). 서버 키·모델·한도를 확인해 주세요."
        )
    data = response.json()
    usage = {
        "stage": stage, "provider": job["provider"], "model": job["model"],
        "prompt_version": prompt_version, "response_id": data.get("id"),
        "tokens": data.get("usage", {}),
    }
    if s.llm_provider == "openrouter":
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ModelError("모델 응답이 완료되지 않았습니다.", usage=usage)
        content = choice["message"].get("content")
    else:
        if data.get("status") != "completed":
            raise ModelError("모델 응답이 완료되지 않았습니다.", usage=usage)
        content = "".join(
            p.get("text", "")
            for item in data.get("output", [])
            for p in item.get("content", [])
            if p.get("type") == "output_text"
        )
    if not content:
        raise ModelError("모델이 구조화된 결과를 반환하지 않았습니다.", usage=usage)
    try:
        return result_model.model_validate_json(content).model_dump(), usage
    except ValueError:
        raise ModelError("모델 결과가 지정된 응답 형식과 일치하지 않습니다.", usage=usage) from None


def mock_result(stage, ctx):
    """Explicit local UI fixture. Never used as a fallback for live generation."""
    idea = ctx.get("idea", "새로운 제품")
    answers = ctx.get("answers", {})
    title = idea.split("\n")[0][:55]
    actor = answers.get("audience") or "일반 사용자"
    device = "mobile" if "모바일" in answers.get("platform", "") else "desktop"
    source = ctx.get("source_context")
    if stage == "discuss":
        previous = ctx.get("conversation_brief") or {}
        statements = previous.get("user_statements", []) + [ctx["request"]]
        return {"reply": "말씀하신 업무 내용을 정리했어요. " + ctx["request"][:250] + "\n아래 질문에 답하거나 자유롭게 대화를 이어가 주세요. 준비되면 ‘기획 초안 만들기’를 눌러 주세요.",
                "brief": {"current_work": previous.get("current_work") or (source or {}).get("name", "현재 업무"),
                          "problem": previous.get("problem") or ctx["request"], "desired_change": ctx["request"],
                          "actors": previous.get("actors", []), "rules": previous.get("rules", []),
                          "exceptions": previous.get("exceptions", []), "confirmed_facts": previous.get("confirmed_facts", []),
                          "user_statements": statements[-20:], "open_questions": ["담당자와 예외 처리 기준 확인"]},
                "suggestions": [],
                "questions": [{"key": "next_business_decision",
                               "title": "예외가 발생하면 어떻게 처리할까요?" if len(statements) > 1 else "이 업무의 확인과 승인은 누가 하나요?",
                               "options": ["담당자가 확인 후 다시 요청해요", "팀장에게 전달해요", "아직 정하지 않았어요"] if len(statements) > 1 else ["담당자가 직접 처리해요", "담당자가 요청하고 팀장이 승인해요", "아직 정하지 않았어요"]}]}
    if source and stage == "questions":
        return {"questions": [
            {"key": "scope", "title": "변경 정책의 범위를 어디까지 적용할까요?",
             "options": ["요청한 기능만", "관련 기능도 포함"]},
        ]}
    if stage == "implementation":
        item = next(iter(source["evidence"]), None)
        refs = [item["id"]] if item else []
        targets = [item["path"]] if item else []
        return {
            "current_behavior": f"로컬 데모. 선택된 근거 {', '.join(targets) or '없음'}",
            "proposed_behavior": ctx["request"], "confirmed_policy": [],
            "preserve": ["기존 동작을 유지한다."], "exceptions": [], "assumptions": [],
            "unresolved": ["로컬 데모. 실제 코드 동작과 적용 범위를 확인해야 한다."],
            "scope": [{"area": source["name"], "disposition": "unverified",
                       "reason": "로컬 데모", "evidence_ids": refs}],
            "tasks": [{"id": "TASK-1", "requirement_ids": [ctx["generated"]["features"]["requirements"][0]["id"]],
                       "evidence_ids": refs, "acceptance_ids": ["AC-1"], "existing_targets": targets,
                       "proposed_targets": [], "reuse": "기존 동작 확인", "implementation": ctx["request"]}],
            "acceptance": [{"id": "AC-1", "scenario": "변경 후 요구한 흐름과 기존 흐름을 재현한다."}],
        }
    if stage == "questions":
        return {
            "questions": [
                {
                    "key": "audience",
                    "title": "이 제품을 주로 누가 사용하나요?",
                    "options": ["팀 구성원", "개인 사용자", "운영 관리자"],
                },
                {
                    "key": "goal",
                    "title": "가장 먼저 해결할 문제는 무엇인가요?",
                    "options": [
                        "반복 업무 줄이기",
                        "진행 상황 한눈에 보기",
                        "필요한 정보 빠르게 찾기",
                    ],
                },
                {
                    "key": "platform",
                    "title": "어떤 환경에서 사용하나요?",
                    "options": ["데스크톱 웹", "모바일 앱", "웹과 모바일"],
                },
            ]
        }
    if stage == "prd":
        items = [
            ("intro", "개요", "한 줄 정의", title),
            (
                "goal",
                "개요",
                "제품 목표",
                f"{actor}가 {answers.get('goal') or '핵심 작업을 간단하게 완료하기'}를 달성하도록 돕습니다.",
            ),
            ("background", "개요", "배경", idea),
            (
                "problem",
                "문제 및 해결 방안",
                "사용자 문제",
                "정보와 작업이 여러 곳에 흩어져 현재 상태를 파악하고 다음 행동을 결정하는 데 시간이 걸립니다.",
            ),
            (
                "solution",
                "문제 및 해결 방안",
                "해결 방안",
                "작업을 한 공간에 모으고 생성·상세 확인·수정·완료를 이어서 수행합니다.",
            ),
            (
                "difference",
                "문제 및 해결 방안",
                "차별점",
                "목록과 상세를 연결해 맥락 전환을 줄이고 변경 내역을 남깁니다.",
            ),
            ("audience", "타겟 및 시나리오", "타겟 사용자", actor),
            (
                "scenario",
                "타겟 및 시나리오",
                "사용자 시나리오",
                "사용자가 대시보드에서 현황을 확인하고 새 항목을 작성한 뒤 상세 화면에서 내용을 검토하고 저장합니다.",
            ),
            (
                "metric",
                "성공과 리스크",
                "핵심 지표",
                "핵심 작업 완료율, 작업 완료까지 걸리는 시간, 재방문율을 측정합니다. 목표 수치는 사용자 검증 후 정합니다.",
            ),
            (
                "risk",
                "성공과 리스크",
                "리스크",
                "중복 입력, 저장 실패, 권한이 없는 정보 노출을 방지해야 합니다.",
            ),
        ]
        return {
            "title": title,
            "sections": [
                {"id": "prd-" + i, "group": g, "title": t, "content": c}
                for i, g, t, c in items
            ],
            "roles": [actor],
            "platforms": [answers.get("platform") or "데스크톱 웹"],
            "assumptions": [
                "로컬 데모용 예시입니다. 실제 제품 내용은 live 모델로 생성해 주세요."
            ],
        }
    if stage == "features":
        names = ["현황과 목록 확인", "새 항목 작성", "상세 조회와 수정"]
        requirements, features = [], []
        for i, name in enumerate(names, 1):
            requirements.append(
                {
                    "id": f"req-{i}",
                    "title": name,
                    "description": f"{actor}가 {name} 작업을 완료할 수 있어야 합니다.",
                    "priority": "P0",
                    "acceptance": [
                        "본인 데이터만 표시됩니다.",
                        "실패 원인과 다시 시도할 방법을 안내합니다.",
                    ],
                }
            )
            features.append(
                {
                    "id": f"feat-{i}",
                    "requirement_id": f"req-{i}",
                    "title": name,
                    "description": f"{title}에서 {name} 기능을 제공합니다.",
                    "actor": actor,
                    "preconditions": ["사용자가 로그인한 상태입니다."],
                    "steps": [
                        "화면에서 대상과 현재 상태를 확인합니다.",
                        "필요한 내용을 입력하거나 항목을 선택합니다.",
                        "작업 결과를 확인합니다.",
                    ],
                    "exceptions": [
                        "저장 실패 시 입력을 유지하고 다시 시도할 수 있습니다.",
                        "접근 권한이 없으면 정보를 노출하지 않습니다.",
                    ],
                    "acceptance": [
                        "필수 입력 누락을 안내합니다.",
                        "새로고침 후 저장한 내용이 유지됩니다.",
                    ],
                }
            )
        return {"requirements": requirements, "features": features}
    if stage == "flow":
        nodes = [
            {
                "id": "node-start",
                "type": "start",
                "title": "서비스 진입",
                "section": "시작",
                "feature_ids": [],
                "x": 80,
                "y": 180,
            },
            {
                "id": "node-home",
                "type": "screen",
                "title": "홈 대시보드",
                "section": "핵심 작업",
                "feature_ids": ["feat-1"],
                "x": 390,
                "y": 180,
            },
            {
                "id": "node-create",
                "type": "screen",
                "title": "새 항목 작성",
                "section": "핵심 작업",
                "feature_ids": ["feat-2"],
                "x": 700,
                "y": 180,
            },
            {
                "id": "node-check",
                "type": "decision",
                "title": "입력이 올바른가요?",
                "section": "입력 검증",
                "feature_ids": ["feat-2"],
                "x": 1010,
                "y": 180,
            },
            {
                "id": "node-detail",
                "type": "screen",
                "title": "상세와 수정",
                "section": "결과 확인",
                "feature_ids": ["feat-3"],
                "x": 1320,
                "y": 180,
            },
            {
                "id": "node-error",
                "type": "action",
                "title": "입력 오류 안내",
                "section": "입력 검증",
                "feature_ids": ["feat-2"],
                "x": 1010,
                "y": 430,
            },
            {
                "id": "node-end",
                "type": "end",
                "title": "작업 완료",
                "section": "결과 확인",
                "feature_ids": [],
                "x": 1630,
                "y": 180,
            },
        ]
        pairs = [
            ("start", "home", ""),
            ("home", "create", "새로 만들기"),
            ("create", "check", "저장"),
            ("check", "detail", "정상"),
            ("check", "error", "오류"),
            ("error", "create", "다시 입력"),
            ("detail", "end", "완료"),
        ]
        return {
            "nodes": nodes,
            "edges": [
                {
                    "id": f"edge-{i}",
                    "source": "node-" + a,
                    "target": "node-" + b,
                    "label": l,
                }
                for i, (a, b, l) in enumerate(pairs)
            ],
        }
    if stage == "wireframes":

        def blocks(prefix, specs):
            return [
                {
                    "id": f"block-{prefix}-{i}",
                    "type": kind,
                    "label": label,
                    "content": content,
                    "target_screen_id": target,
                }
                for i, (kind, label, content, target) in enumerate(specs)
            ]

        return {
            "screens": [
                {
                    "id": "screen-home",
                    "node_id": "node-home",
                    "title": "홈 대시보드",
                    "device": device,
                    "blocks": blocks(
                        "home",
                        [
                            ("navigation", title[:20], "홈 · 내 작업 · 설정", None),
                            (
                                "heading",
                                "오늘의 작업을 시작해 볼까요?",
                                "지금 필요한 정보를 한눈에 확인하세요.",
                                None,
                            ),
                            ("stat", "진행 중", "3개의 작업", None),
                            ("button", "새로 만들기", "", "screen-create"),
                            (
                                "card",
                                "최근 작업",
                                "첫 번째 작업 · 오늘 업데이트",
                                "screen-detail",
                            ),
                            (
                                "list",
                                "내 작업 목록",
                                "진행 중인 항목\n검토가 필요한 항목\n완료한 항목",
                                None,
                            ),
                        ],
                    ),
                },
                {
                    "id": "screen-create",
                    "node_id": "node-create",
                    "title": "새 항목 작성",
                    "device": device,
                    "blocks": blocks(
                        "create",
                        [
                            (
                                "navigation",
                                "새로 만들기",
                                "홈으로 돌아가기",
                                "screen-home",
                            ),
                            (
                                "heading",
                                "새로운 작업",
                                "필요한 정보를 입력해 주세요.",
                                None,
                            ),
                            ("input", "제목", "어떤 작업인가요?", None),
                            (
                                "input",
                                "상세 내용",
                                "목표와 필요한 내용을 적어 주세요.",
                                None,
                            ),
                            (
                                "card",
                                "저장 전 확인",
                                "필수 항목을 입력해야 저장할 수 있습니다.",
                                None,
                            ),
                            ("button", "저장하고 확인하기", "", "screen-detail"),
                        ],
                    ),
                },
                {
                    "id": "screen-detail",
                    "node_id": "node-detail",
                    "title": "상세와 수정",
                    "device": device,
                    "blocks": blocks(
                        "detail",
                        [
                            (
                                "navigation",
                                "작업 상세",
                                "목록으로 돌아가기",
                                "screen-home",
                            ),
                            (
                                "heading",
                                "첫 번째 작업",
                                "진행 중 · 방금 업데이트",
                                None,
                            ),
                            (
                                "card",
                                "상세 정보",
                                "작성한 내용과 현재 상태를 확인합니다.",
                                None,
                            ),
                            (
                                "list",
                                "진행 체크리스트",
                                "필수 정보 확인\n담당자 확인\n최종 검토",
                                None,
                            ),
                            ("button", "목록으로 돌아가기", "", "screen-home"),
                        ],
                    ),
                },
            ]
        }
    if stage in {"revise", "repair"}:
        result = copy.deepcopy(ctx["snapshot"])
        result.pop("design_profile", None)
        if stage == "revise":
            request = ctx.get("request", "수정")
            target = ctx.get("target_id")
            selected_block = next((b for screen in result["screens"] for b in screen["blocks"] if b["id"] == target), None)
            if selected_block:
                selected_block["label"] = request[:100]
                return result
            selected = next(
                (x for x in result["prd"]["sections"] if x["id"] == target),
                result["prd"]["sections"][1],
            )
            selected["content"] += "\n\n수정 요청 반영(로컬 데모): " + request
        else:
            # The mock repair resolves a missing screen target without rewriting unrelated content.
            screens = {s["id"] for s in result["screens"]}
            for screen in result["screens"]:
                for block in screen["blocks"]:
                    if block["target_screen_id"] and block["target_screen_id"] not in screens:
                        block["target_screen_id"] = None
        return result
    raise ValueError("알 수 없는 생성 단계")
