import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  LoaderCircle,
  Play,
  RotateCcw,
} from "lucide-react";
import { api } from "./api";
import type { RoleReport, ReviewRole } from "./types";

const roles: { id: ReviewRole; name: string; checks: string[] }[] = [
  {
    id: "developer",
    name: "개발자",
    checks: [
      "데이터·상태 전이",
      "API·동시성",
      "실패·복구",
      "산출물 구현 일관성",
    ],
  },
  {
    id: "planner",
    name: "기획자",
    checks: ["문제·목표", "범위·우선순위", "정책·비즈니스 규칙", "성공 지표"],
  },
  {
    id: "security",
    name: "보안",
    checks: [
      "인증·소유권",
      "개인정보 생명주기",
      "입력·악용",
      "권한별 정보 노출",
    ],
  },
  {
    id: "ux",
    name: "UI/UX",
    checks: [
      "정보 구조·탐색",
      "행동·화면 연결",
      "빈 화면·로딩·오류",
      "접근성·모바일",
    ],
  },
  {
    id: "qa",
    name: "QA",
    checks: [
      "수용 기준",
      "정상·예외·경계",
      "상태·역할별 테스트",
      "회귀·정합성",
    ],
  },
];
const statuses: Record<string, string> = {
  queued: "대기",
  running: "검토 중",
  completed: "완료",
  failed: "실패",
};

export type RoleReviewProps = {
  projectId: string;
  proposalId: string | null;
  version: number;
  disabled: boolean;
  onLocate: (id: string) => void;
};

export default function RoleReview({
  projectId,
  proposalId,
  version,
  disabled,
  onLocate,
}: RoleReviewProps) {
  const [report, setReport] = useState<RoleReport | null>(null);
  const [role, setRole] = useState<ReviewRole>("developer");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const alive = useRef(true);
  const path = `/api/projects/${projectId}/reviews`;
  const target = proposalId ? { proposal_id: proposalId } : { version };
  const query = proposalId ? `proposal_id=${proposalId}` : `version=${version}`;
  const available = !!proposalId || version > 0;
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    if (!available) {
      setLoading(false);
      return () => {
        alive.current = false;
      };
    }
    api<RoleReport | null>(
      `${path}?${query}`,
      undefined,
      undefined,
      controller.signal,
    )
      .then((r) => {
        if (alive.current) setReport(r);
      })
      .catch((e) => {
        if (!controller.signal.aborted && alive.current) setError(e.message);
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, [path, query, available]);
  const active = report?.status === "queued" || report?.status === "running";
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      api<RoleReport | null>(
        `${path}?${query}`,
        undefined,
        undefined,
        controller.signal,
      )
        .then((r) => {
          if (!controller.signal.aborted) {
            setReport(r);
            setError("");
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        });
    }, 1600);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [active, path, query]);
  const submit = async (retryRole?: ReviewRole) => {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      const r = await api<RoleReport>(
        retryRole ? `${path}/${report!.id}/retry` : path,
        retryRole ? { role: retryRole } : target,
      );
      if (alive.current) setReport(r);
    } catch (e) {
      if (alive.current)
        setError(
          e instanceof Error ? e.message : "검토를 시작하지 못했습니다.",
        );
    } finally {
      if (alive.current) setWorking(false);
    }
  };
  const agent = report?.agents.find((a) => a.role === role);
  const definition = roles.find((r) => r.id === role)!;
  const done =
    report?.agents.filter((a) => a.status === "completed").length || 0;
  return (
    <div className="role-review-content">
      <div className="eyebrow">
        {proposalId ? `수정안 · 확정본 v${version} 기준` : `확정본 v${version}`}
      </div>
      {report?.commit_sha && <p className="subtle">코드 기준 <code>{report.commit_sha}</code></p>}
      <h3>다섯 관점으로 더 단단한 기획</h3>
      <p className="role-intro">
        역할마다 독립적으로 읽고, 근거와 수정 방향을 제안합니다.
      </p>
      <div className="role-selector" role="group" aria-label="검토 역할">
        {roles.map((r) => {
          const a = report?.agents.find((x) => x.role === r.id);
          return (
            <button
              key={r.id}
              className={role === r.id ? "active" : ""}
              onClick={() => setRole(r.id)}
              aria-pressed={role === r.id}
            >
              <span>{r.name}</span>
              {a ? (
                <small className={`agent-status ${a.status}`}>
                  {a.status === "running" && (
                    <LoaderCircle size={10} className="spin" />
                  )}
                  {statuses[a.status]}
                </small>
              ) : (
                <small>검토 기준</small>
              )}
            </button>
          );
        })}
      </div>
      <div className="role-checklist">
        <strong>{definition.name}가 살펴보는 것</strong>
        <ul>
          {(agent?.result?.reviewed_checks || definition.checks).map((c) => (
            <li key={c}>
              <Check size={12} />
              {c}
            </li>
          ))}
        </ul>
      </div>
      {!report && (
        <button
          className="primary start-role-review"
          disabled={working || loading || disabled || !available}
          onClick={() => submit()}
        >
          <Play size={14} />
          다섯 역할 검토 시작
        </button>
      )}
      {!available && (
        <p className="subtle">기획 초안이 준비되면 검토할 수 있어요.</p>
      )}
      {disabled && (
        <p className="subtle">직접 편집 중에는 수정안을 먼저 저장해 주세요.</p>
      )}
      {loading && <p className="subtle">검토 결과를 불러오고 있어요.</p>}
      {error && (
        <p className="role-error" role="alert">
          {error}
        </p>
      )}
      {report && (
        <div className="role-progress" aria-live="polite">
          <span>
            {active && <LoaderCircle size={12} className="spin" />}
            {done}/5 역할 완료
          </span>
          <span>{report.ai_mode === "mock" ? "로컬 데모" : "AI 검토"}</span>
        </div>
      )}
      {!!agent?.attempts?.length && <p className="subtle">검토 시도 {agent.attempts.length}회</p>}
      {agent?.status === "failed" && (
        <div className="role-failure">
          <AlertTriangle size={18} />
          <p>{agent.error}</p>
          <button
            className="secondary"
            disabled={working || active || disabled}
            onClick={() => submit(role)}
          >
            <RotateCcw size={13} />이 역할만 재시도
          </button>
        </div>
      )}
      {agent && ["queued", "running"].includes(agent.status) && (
        <p className="role-waiting">
          {definition.name}가 기획 문서와 화면을{" "}
          {agent.status === "queued"
            ? "검토할 차례를 기다리고 있어요."
            : "검토하고 있어요."}
        </p>
      )}
      {agent?.result && agent.status === "completed" && (
        <>
          <p className="role-summary">{agent.result.summary}</p>
          <div className="role-findings">
            {agent.result.findings.length === 0 && (
              <div className="valid-check">
                <Check size={15} />이 관점에서 추가 지적이 없어요.
              </div>
            )}
            {agent.result.findings.map((f, i) => (
              <article className={`role-finding ${f.severity}`} key={i}>
                <span className="finding-severity">
                  {
                    {
                      critical: "중요",
                      warning: "확인 필요",
                      suggestion: "개선 제안",
                    }[f.severity]
                  }
                </span>
                <h4>{f.title}</h4>
                <p>{f.rationale}</p>
                {f.evidence.map((e, j) => (
                  <button
                    className="finding-evidence"
                    key={j}
                    onClick={() => onLocate(e.target_id)}
                    title="관련 항목 보기"
                  >
                    <q>{e.quote}</q>
                    <span>
                      {e.target_id}
                      <ArrowUpRight size={12} />
                    </span>
                  </button>
                ))}
                <strong className="finding-label">수정 제안</strong>
                <p>{f.recommendation}</p>
                <strong className="finding-label">수정 후 확인</strong>
                <ul>
                  {f.acceptance.map((a, j) => (
                    <li key={j}>{a}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </>
      )}
      <p className="role-note">
        AI 검토는 기획에 대한 제안입니다. 문서 연결 검사와 승인 조건은 별도로
        적용되며, 검토만으로 기획이 바뀌지 않습니다.
      </p>
    </div>
  );
}
