import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCheck,
  GitCompareArrows,
  ShieldCheck,
} from "lucide-react";
import type { Proposal } from "./types";
import RoleReview, { type RoleReviewProps } from "./RoleReview";

function readable(value: unknown): string {
  if (value === null || value === undefined) return "없음";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.join("\n");
  if (typeof value === "object") {
    const item = value as Record<string, unknown>;
    return Object.entries(item)
      .filter(([k]) => !["id", "x", "y"].includes(k))
      .map(
        ([key, v]) =>
          `${key}: ${typeof v === "object" ? JSON.stringify(v, null, 2) : v}`,
      )
      .join("\n");
  }
  return String(value);
}

function ChangeReview({
  proposal,
  onDecide,
  working,
}: {
  proposal: Proposal | null;
  onDecide: (decision: "approve" | "reject", ack: boolean) => void;
  working: boolean;
}) {
  const [ack, setAck] = useState(false);
  useEffect(() => setAck(false), [proposal?.id]);
  if (!proposal)
    return (
      <>
        <div className="panel-heading">
          <strong>변경 검토</strong>
          <ShieldCheck size={16} />
        </div>
        <div className="side-empty">
          <CheckCheck size={30} />
          <h3>검토할 수정안이 없어요</h3>
          <p>
            AI에게 수정을 요청하거나 문서를 직접 편집하면 변경 내용을 여기서
            확인할 수 있어요.
          </p>
        </div>
      </>
    );
  const blocking = proposal.issues.some((i) => i.severity === "blocking");
  const warnings = proposal.issues.some((i) => i.severity === "warning");
  return (
    <>
      <div className="panel-heading">
        <div>
          <GitCompareArrows size={17} />
          <strong>변경 검토</strong>
        </div>
        <span className="count-pill">{proposal.diff.length}</span>
      </div>
      <div className="review-content">
        <div className="eyebrow">확정본 v{proposal.base_version} 기준</div>
        <h3>{proposal.summary}</h3>
        <p className="subtle">승인하면 새 버전으로 저장됩니다.</p>
        <div className="diff-counts">
          {(["added", "changed", "removed"] as const).map((kind, i) => (
            <span className={kind} key={kind}>
              {["+", "~", "−"][i]}{" "}
              {proposal.diff.filter((d) => d.kind === kind).length}
            </span>
          ))}
        </div>
        <h4>연결과 완성도 검사</h4>
        {!proposal.issues.length ? (
          <div className="valid-check">
            <Check size={16} /> 모든 연결이 올바릅니다.
          </div>
        ) : (
          proposal.issues.map((issue, i) => (
            <div className={`issue ${issue.severity}`} key={i}>
              <AlertTriangle size={15} />
              <div>
                <strong>
                  {issue.severity === "blocking" ? "수정 필요" : "확인 필요"}
                </strong>
                <p>{issue.message}</p>
                <small>{issue.target}</small>
              </div>
            </div>
          ))
        )}
        <h4>변경된 항목</h4>
        <div className="diff-list">
          {proposal.diff.map((change) => (
            <details key={change.key}>
              <summary>
                <span className={`diff-dot ${change.kind}`} />
                <span>
                  {typeof change.after === "object" &&
                  change.after &&
                  "title" in change.after
                    ? String(change.after.title)
                    : change.key}
                </span>
                <small>
                  {
                    { added: "추가", changed: "수정", removed: "삭제" }[
                      change.kind
                    ]
                  }
                </small>
              </summary>
              <div className="diff-detail">
                {change.before !== null && change.before !== undefined && (
                  <div className="before">
                    <span>이전</span>
                    <pre>{readable(change.before)}</pre>
                  </div>
                )}
                {change.after !== null && change.after !== undefined && (
                  <div className="after">
                    <span>수정안</span>
                    <pre>{readable(change.after)}</pre>
                  </div>
                )}
              </div>
            </details>
          ))}
        </div>
      </div>
      <div className="decision-footer">
        {warnings && (
          <label className="ack">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />
            경고와 확인이 필요한 가정을 검토했어요
          </label>
        )}
        <div>
          <button
            className="secondary"
            disabled={working}
            onClick={() => onDecide("reject", false)}
          >
            거절
          </button>
          <button
            className="primary"
            disabled={working || blocking || (warnings && !ack)}
            onClick={() => onDecide("approve", ack)}
          >
            <Check size={16} /> 승인하고 확정
          </button>
        </div>
        {blocking && (
          <small>수정 필요 항목을 해결한 후 승인할 수 있어요.</small>
        )}
      </div>
    </>
  );
}

export default function Review(
  props: RoleReviewProps & {
    proposal: Proposal | null;
    onDecide: (decision: "approve" | "reject", ack: boolean) => void;
    working: boolean;
  },
) {
  const [view, setView] = useState<"changes" | "roles">("changes");
  return (
    <>
      <div className="review-mode" role="group" aria-label="검토 방식">
        <button
          className={view === "changes" ? "active" : ""}
          onClick={() => setView("changes")}
        >
          변경 검토
        </button>
        <button
          className={view === "roles" ? "active" : ""}
          onClick={() => setView("roles")}
        >
          역할별 AI 검토
        </button>
      </div>
      {view === "changes" ? (
        <ChangeReview
          proposal={props.proposal}
          onDecide={props.onDecide}
          working={props.working}
        />
      ) : (
        <RoleReview
          key={`${props.projectId}:${props.proposalId || props.version}`}
          {...props}
        />
      )}
    </>
  );
}
