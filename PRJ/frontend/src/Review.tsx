import { useEffect, useState } from "react";
import { AlertTriangle, Check, CheckCheck, Sparkles } from "lucide-react";
import type { Change, Proposal, Snapshot, Tab } from "./types";
import RoleReview, { type RoleReviewProps } from "./RoleReview";

const labels: Record<string, string> = {
  title: "이름",
  label: "표시 문구",
  content: "내용",
  description: "업무 설명",
  actor: "업무 담당자",
  preconditions: "업무 시작 조건",
  steps: "처리 순서",
  exceptions: "예외 처리",
  acceptance: "완료 조건",
  priority: "중요도",
  roles: "업무 담당자",
  platforms: "사용 환경",
  assumptions: "확인할 업무 기준",
  blocks: "화면 구성",
  columns: "표 제목",
  rows: "표 내용",
  device: "사용 화면",
  section: "업무 구분",
};
function readable(value: unknown): string {
  if (value == null) return "없음";
  if (typeof value === "string")
    return (
      (
        {
          P0: "필수",
          P1: "중요",
          P2: "추후",
          desktop: "PC",
          mobile: "모바일",
        } as Record<string, string>
      )[value] || value
    );
  if (Array.isArray(value))
    return value.map(readable).filter(Boolean).join("\n");
  if (typeof value === "object")
    return Object.entries(value as Record<string, unknown>)
      .filter(([key]) => key in labels)
      .map(([key, content]) => `${labels[key]}: ${readable(content)}`)
      .join("\n");
  return String(value);
}
function businessComparison(change: Change) {
  if (change.before && change.after && typeof change.before === "object" && typeof change.after === "object" && !Array.isArray(change.before)) {
    const before = change.before as Record<string, unknown>;
    const after = change.after as Record<string, unknown>;
    return Object.keys(labels).filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
      .map((key) => ({ label: labels[key], before: readable(before[key]), after: readable(after[key]) }));
  }
  return [{ label: "업무 내용", before: readable(change.before), after: readable(change.after) }];
}
const metadata: Record<string, string> = {
  "prd:roles": "업무 담당자",
  "prd:platforms": "사용 환경",
  "prd:assumptions": "확인할 업무 기준",
  "prd:title": "기획 이름",
};
function changeTitle(change: Change) {
  const item = (change.after || change.before) as {
    title?: string;
    label?: string;
  } | null;
  return metadata[change.key] || item?.title || item?.label || "업무 처리 경로";
}
function documentItems(snapshot: Snapshot) {
  return [
    ...snapshot.prd.sections.map((x) => ({
      ...x,
      tab: "prd" as Tab,
      description: x.content,
    })),
    ...snapshot.requirements.map((x) => ({ ...x, tab: "features" as Tab })),
    ...snapshot.features.map((x) => ({ ...x, tab: "features" as Tab })),
    ...snapshot.flow.nodes.map((x) => ({
      ...x,
      tab: "flow" as Tab,
      description: x.section,
    })),
    ...snapshot.screens.map((x) => ({
      ...x,
      tab: "wireframes" as Tab,
      description: x.blocks
        .map((b) => b.label)
        .filter(Boolean)
        .join(" · "),
    })),
    ...snapshot.screens.flatMap((x) =>
      x.blocks.map((b) => ({
        id: b.id,
        title: b.label,
        description: "",
        tab: "wireframes" as Tab,
      })),
    ),
  ];
}
function tabForChange(change: Change): Tab {
  const prefix = change.key.split(":")[0];
  return prefix === "prd"
    ? "prd"
    : ["feature", "requirement"].includes(prefix)
      ? "features"
      : prefix === "screen"
        ? "wireframes"
        : "flow";
}

type BusinessProps = {
  proposal: Proposal | null;
  confirmed: Snapshot;
  currentVersion: number;
  onView: (tab: Tab, id?: string) => void;
  onDiscuss: (id?: string) => void;
  onDecide: (decision: "approve" | "reject", ack: boolean) => void;
  onRepair: () => void;
  working: boolean;
  canEdit?: boolean;
  canConfirm?: boolean;
};
function ChangeReview({
  proposal,
  confirmed,
  currentVersion,
  onView,
  onDiscuss,
  onDecide,
  onRepair,
  working,
  canEdit = true,
  canConfirm = true,
}: BusinessProps) {
  const [ack, setAck] = useState(false);
  const snapshot = proposal?.candidate || confirmed;
  const items = documentItems(snapshot);
  const warnings =
    proposal?.issues.filter((x) => x.severity === "warning") || [];
  const blocking =
    proposal?.issues.filter((x) => x.severity === "blocking") || [];
  const changes =
    proposal?.diff.filter(
      (x) =>
        !["implementation", "design_profile", "source_context"].includes(x.key),
    ) || [];
  const removed = changes.filter((x) => x.kind === "removed");
  const removedBlocks = confirmed.screens.flatMap((screen) =>
    screen.blocks
      .filter(
        (block) =>
          !snapshot.screens.some((s) =>
            s.blocks.some((b) => b.id === block.id),
          ),
      )
      .map((block) => ({ title: block.label, screen: screen.title })),
  );
  const name = (id: string) =>
    items.find((x) => x.id === id)?.title ||
    (
      { prd: "기획 내용", flow: "업무 흐름", snapshot: "기획 전체" } as Record<
        string,
        string
      >
    )[id] ||
    "관련 업무 문서";
  const locateIssue = (id: string) => {
    const item = items.find((x) => x.id === id);
    const edge = snapshot.flow.edges.find((x) => x.id === id);
    onView(
      item?.tab ||
        (id === "prd" ? "prd" : edge || id === "flow" ? "flow" : "prd"),
      item?.id || edge?.source,
    );
  };
  const guides: { tab: Tab; title: string; description: string }[] = [
    {
      tab: "prd",
      title: "기획 내용",
      description:
        "현재 업무와 바꾸려는 내용이 요청한 방향과 맞는지 살펴보세요.",
    },
    {
      tab: "features",
      title: "담당자·처리 순서·업무 규칙",
      description:
        "누가 처리하는지, 어떤 순서와 기준으로 처리하는지 확인해 주세요.",
    },
    {
      tab: "flow",
      title: "업무 흐름",
      description:
        "시작부터 완료까지의 순서와 예외 상황에서 이어지는 업무를 살펴보세요.",
    },
    {
      tab: "wireframes",
      title: "화면 시안",
      description: "업무에 필요한 정보와 입력란, 버튼이 있는지 확인해 주세요.",
    },
  ];
  return (
    <>
      <div className="panel-heading">
        <div>
          <CheckCheck size={18} />
          <strong>내용 확인</strong>
        </div>
      </div>
      {!proposal && !currentVersion ? (
        <div className="side-empty">
          <CheckCheck size={30} />
          <h3>아직 확인할 문서가 없어요</h3>
          <p>
            기획 파트너와 업무를 정리한 뒤 ‘기획 초안 만들기’를 눌러 주세요.
          </p>
          <button className="primary" onClick={() => onDiscuss()}>
            업무 대화로 이동
          </button>
        </div>
      ) : (
        <div
          className="review-content business-review"
          data-proposal-id={proposal?.id || ""}
        >
          <span className="eyebrow">
            {proposal
              ? proposal.base_version
                ? `현업 확인본 v${proposal.base_version} 이후 수정안`
                : "첫 기획 초안"
              : `현업 확인본 v${currentVersion} · 읽기 전용`}
          </span>
          <h3>
            {proposal
              ? "문서를 보며 업무 내용을 확인해 주세요"
              : "마지막으로 저장한 업무 내용이에요"}
          </h3>
          <p>
            {proposal
              ? "요청한 업무가 반영됐는지 살펴보고, 필요한 부분은 기획 파트너와 수정할 수 있어요."
              : "저장된 확인본은 그대로 보관됩니다. 변경이 필요하면 대화로 새 수정안을 만들어 주세요."}
          </p>
          {proposal && proposal.base_version > 0 && (
            <section className="review-changed">
              <h4>마지막 확인본에서 달라진 내용</h4>
              {changes.length ? (
                changes.map((change) => (
                  <div className="review-change-row" key={change.key}>
                    <strong>{changeTitle(change)}</strong>
                    <p>
                      {change.kind === "removed"
                        ? "이번 초안에서 제외됐어요. 아래 확인 사항에서 이전 내용을 살펴보세요."
                        : change.kind === "added"
                          ? "이번 초안에 새로 담았어요."
                          : "이번 초안에서 내용이 달라졌어요."}
                    </p>
                    <div className="business-comparison">
                      {businessComparison(change).map((field) => (
                        <section key={field.label}>
                          <h5>{field.label}</h5>
                          <dl>
                            <div><dt>이전 업무</dt><dd>{field.before || "없음"}</dd></div>
                            <div><dt>이번 업무</dt><dd>{field.after || "없음"}</dd></div>
                          </dl>
                        </section>
                      ))}
                    </div>
                    {change.kind !== "removed" && (
                      <button
                        className="text-button"
                        onClick={() =>
                          onView(
                            tabForChange(change),
                            items.find(
                              (x) =>
                                x.id ===
                                change.key.slice(change.key.indexOf(":") + 1),
                            )?.id,
                          )
                        }
                      >
                        내용 보기
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <p>문서의 업무 내용은 마지막 확인본과 같아요.</p>
              )}
            </section>
          )}
          <h4>
            {proposal
              ? proposal.base_version
                ? "전체 문서 살펴보기"
                : "이번에 정리한 업무"
              : "저장한 문서 살펴보기"}
          </h4>
          {guides.map((guide, index) => {
            const entries = items.filter(
              (item) =>
                item.tab === guide.tab &&
                (guide.tab !== "features" ||
                  snapshot.features.some((x) => x.id === item.id)) &&
                (guide.tab !== "wireframes" ||
                  snapshot.screens.some((x) => x.id === item.id)),
            );
            return (
              <section className="review-guide" key={guide.tab}>
                <h4>
                  <span>{index + 1}</span>
                  {guide.title}
                </h4>
                <p>{guide.description}</p>
                <button
                  className="secondary small"
                  onClick={() => onView(guide.tab, entries[0]?.id)}
                >
                  내용 보기
                </button>
                <details>
                  <summary>문서에 담긴 내용</summary>
                  {entries.length ? (
                    entries.map((item) => (
                      <div className="review-document-item" key={item.id}>
                        <strong>{item.title}</strong>
                        <p>
                          {item.description.length > 220
                            ? item.description.slice(0, 220) + "…"
                            : item.description}
                        </p>
                        <div className="review-item-actions">
                          <button
                            className="text-button"
                            onClick={() => onView(item.tab, item.id)}
                          >
                            내용 보기
                          </button>
                          <button
                            className="text-button"
                            disabled={working || !canEdit}
                            onClick={() => onDiscuss(item.id)}
                          >
                            이 내용 수정하기
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p>아직 작성된 내용이 없어요.</p>
                  )}
                </details>
              </section>
            );
          })}
          {!proposal && (
            <button
              className="secondary"
              disabled={working || !canEdit}
              onClick={() => onDiscuss()}
            >
              기획 파트너와 수정하기
            </button>
          )}
          {proposal && (
            <>
              <h4>업무상 확인해 주세요</h4>
              {warnings
                .filter((x) => x.target !== "implementation")
                .map((issue, index) => (
                  <div className="issue warning" key={index}>
                    <AlertTriangle size={16} />
                    <div>
                      <strong>{name(issue.target)}</strong>
                      <p>
                        {issue.target === "prd"
                          ? "아래 내용은 아직 확인이 필요한 업무 기준이에요. 실제 업무와 맞는지 살펴봐 주세요."
                          : issue.target === "snapshot"
                            ? "기존 내용 중 이번 초안에서 제외한 항목이 있어요. 업무에 필요한 내용이 빠지지 않았는지 확인해 주세요."
                            : issue.message === "예외 동작을 보강해 주세요."
                              ? "평소와 다르게 처리해야 하는 상황을 더 정해야 해요."
                              : issue.message === "검수 조건이 비어 있습니다."
                                ? "어떤 상태가 되면 업무가 완료되는지 더 정해야 해요."
                                : "이 항목의 업무 처리 기준을 확인해 주세요."}
                      </p>
                      {issue.target === "prd" && (
                        <ul>
                          {snapshot.prd.assumptions.map((text, i) => (
                            <li key={i}>{text}</li>
                          ))}
                        </ul>
                      )}
                      {issue.target === "snapshot" && (
                        <ul>
                          {removed.map((change) => (
                            <li key={change.key}>
                              {changeTitle(change)}
                              <p>{readable(change.before)}</p>
                            </li>
                          ))}
                          {removedBlocks.map((block, i) => (
                            <li key={`block-${i}`}>
                              {block.screen} · {block.title}
                            </li>
                          ))}
                        </ul>
                      )}
                      <button
                        className="text-button"
                        onClick={() => locateIssue(issue.target)}
                      >
                        해당 문서 보기
                      </button>
                      {items.some((x) => x.id === issue.target) && (
                        <button
                          className="text-button"
                          disabled={working || !canEdit}
                          onClick={() => onDiscuss(issue.target)}
                        >
                          이 내용 수정하기
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              {warnings.some((x) => x.target === "implementation") && (
                <p>
                  기존 시스템에서 확인하지 못한 범위는 전달 자료에 남겨
                  두었어요. IT 담당자의 추가 확인이 필요해요.
                </p>
              )}
              {!warnings.length && (
                <p>
                  시스템 검사에서 추가 확인 사항이 발견되지 않았어요. 실제
                  업무와 맞는지는 문서를 보고 확인해 주세요.
                </p>
              )}
              {blocking.length > 0 && (
                <section className="review-blockers">
                  <h4>저장 전에 정리가 필요해요</h4>
                  <p>
                    문서와 화면 사이에 연결이 빠졌거나 서로 맞지 않는 부분이
                    있어 저장을 기다리고 있어요. AI에 정리를 요청해 주세요.
                  </p>
                  {[...new Set(blocking.map((x) => x.target))].map((target) => (
                    <div className="review-blocker-item" key={target}>
                      <p>확인이 필요한 문서: {name(target)}</p>
                      <button
                        className="text-button"
                        onClick={() => locateIssue(target)}
                      >
                        해당 문서 보기
                      </button>
                    </div>
                  ))}
                  <button
                    className="secondary"
                    disabled={working || !canEdit}
                    onClick={onRepair}
                  >
                    <Sparkles size={16} />
                    AI로 정리하기
                  </button>
                  <small>
                    정리가 끝나면 변경된 업무 내용을 다시 확인해 주세요.
                  </small>
                </section>
              )}
              <details className="review-diff">
                <summary>자세한 변경 내역</summary>
                <div className="diff-counts">
                  {(["added", "changed", "removed"] as const).map((kind) => (
                    <span key={kind} className={kind}>
                      {
                        { added: "추가", changed: "수정", removed: "삭제" }[
                          kind
                        ]
                      }{" "}
                      {changes.filter((x) => x.kind === kind).length}
                    </span>
                  ))}
                </div>
                <div className="diff-list">
                  {changes.map((change) => (
                    <details key={change.key}>
                      <summary>{changeTitle(change)}</summary>
                      <div className="diff-detail">
                        {change.before != null && (
                          <div className="before">
                            <span>이전 내용</span>
                            <pre>{readable(change.before)}</pre>
                          </div>
                        )}
                        {change.after != null && (
                          <div className="after">
                            <span>이번 내용</span>
                            <pre>{readable(change.after)}</pre>
                          </div>
                        )}
                      </div>
                    </details>
                  ))}
                </div>
              </details>
            </>
          )}
        </div>
      )}
      {proposal && (
        <div className="decision-footer">
          {warnings.length > 0 && (
            <label className="ack">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
              />{" "}
              위 확인 사항과 가정을 살펴봤어요
            </label>
          )}
          <div>
            <button
              className="secondary"
              disabled={working || !canEdit}
              onClick={() => onDecide("reject", false)}
            >
              이 초안 사용 안 함
            </button>
            <button
              className="primary"
              disabled={
                working ||
                !canConfirm ||
                blocking.length > 0 ||
                (warnings.length > 0 && !ack)
              }
              onClick={() => onDecide("approve", ack)}
            >
              <Check size={16} />
              현업 확인본 저장
            </button>
          </div>
          <small>
            {working
              ? "진행 중인 작업이 끝나면 저장할 수 있어요."
              : blocking.length
                ? "AI가 문서와 화면의 연결을 정리한 뒤 저장할 수 있어요."
                : warnings.length && !ack
                  ? "업무상 확인 사항을 살펴보고 위 항목을 체크해 주세요."
                  : "저장한 확인본도 새 수정안으로 보완할 수 있어요."}
          </small>
        </div>
      )}
    </>
  );
}
export default function Review(
  props: RoleReviewProps & BusinessProps & { busy: boolean; visit: number },
) {
  const [view, setView] = useState<"changes" | "roles">("changes");
  useEffect(() => setView("changes"), [props.visit]);
  return (
    <>
      <div className="review-mode" role="group" aria-label="확인 방식">
        <button
          className={view === "changes" ? "active" : ""}
          onClick={() => setView("changes")}
        >
          업무 내용 확인
        </button>
        <button
          className={view === "roles" ? "active" : ""}
          onClick={() => setView("roles")}
        >
          IT 상세 검토
        </button>
      </div>
      {view === "changes" ? (
        <ChangeReview
          key={props.proposal?.id || "confirmed"}
          {...props}
          working={props.working || props.busy || !!props.disabled}
        />
      ) : (
        <>
          {!!props.proposal?.issues.length && (
            <details className="review-technical">
              <summary>시스템 검사 상세</summary>
              {props.proposal.issues.map((issue, i) => (
                <p key={i}>{issue.message}</p>
              ))}
            </details>
          )}
          <RoleReview
            key={`${props.projectId}:${props.proposalId || props.version}`}
            {...props}
            disabled={props.disabled || props.canEdit === false}
          />
        </>
      )}
    </>
  );
}
