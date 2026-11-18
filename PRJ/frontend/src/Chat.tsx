import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  Check,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Sparkles,
  Square,
  X,
} from "lucide-react";
import type { Bundle, Health, Job } from "./types";

export const busyStatuses = ["queued", "running", "awaiting_answers"];
const stages = [
  ["questions", "방향 확인"],
  ["prd", "PRD"],
  ["features", "기능명세"],
  ["flow", "유저플로우"],
  ["wireframes", "와이어프레임"],
];
export function Progress({ job }: { job: Job }) {
  const phases =
    job.kind === "revise"
      ? [
          ["revise", "요청한 항목 수정"],
          ...(job.code_snapshot_id ? [["implementation", "코드 기반 구현 지침"]] : []),
          ["validation", "연결과 변경 검증"],
        ]
      : stages;
  const current = phases.findIndex(([key]) => key === job.stage);
  return (
    <div className="generation-progress">
      <div className="eyebrow">
        <LoaderCircle size={13} className="spin" />{" "}
        {job.kind === "revise"
          ? "수정 요청을 반영하는 중"
          : "연결된 기획을 만드는 중"}
      </div>
      {phases.map(([key, label], i) => (
        <div key={key} className={i === current ? "current" : ""}>
          {i < current || job.stage === "validation" ? (
            <Check size={13} />
          ) : i === current ? (
            <LoaderCircle size={13} className="spin" />
          ) : (
            <span className="step-dot" />
          )}
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

function Questions({
  job,
  onAnswer,
  working,
}: {
  job: Job;
  onAnswer: (answers: Record<string, string>) => void;
  working: boolean;
}) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const q = job.questions[step];
  if (!q) return null;
  return (
    <div className="question-card">
      <div className="eyebrow">
        방향 맞추기{" "}
        <span>
          {step + 1} / {job.questions.length}
        </span>
      </div>
      <h3>{q.title}</h3>
      <div className="question-options">
        {q.options.map((option) => (
          <button
            key={option}
            className={answers[q.key] === option ? "chosen" : ""}
            onClick={() => setAnswers({ ...answers, [q.key]: option })}
          >
            {option}
            {answers[q.key] === option && <Check size={15} />}
          </button>
        ))}
      </div>
      <input
        aria-label="질문 직접 답변"
        placeholder="직접 입력해도 좋아요"
        value={q.options.includes(answers[q.key]) ? "" : answers[q.key] || ""}
        onChange={(e) => setAnswers({ ...answers, [q.key]: e.target.value })}
      />
      <div className="question-footer">
        <button
          className="icon-button"
          aria-label="이전 질문"
          disabled={!step || working}
          onClick={() => setStep(step - 1)}
        >
          <ChevronLeft size={17} />
        </button>
        <span>
          {answers[q.key]
            ? "선택한 답변으로 진행"
            : "모르면 건너뛰어도 괜찮아요"}
        </span>
        <button
          className="primary small"
          disabled={working}
          onClick={() =>
            step < job.questions.length - 1
              ? setStep(step + 1)
              : onAnswer(
                  Object.fromEntries(
                    job.questions.map((x) => [x.key, answers[x.key] || ""]),
                  ),
                )
          }
        >
          {step < job.questions.length - 1 ? (
            <ChevronRight size={17} />
          ) : (
            "기획 시작"
          )}
        </button>
      </div>
      <button
        className="text-button skip"
        disabled={working}
        onClick={() =>
          onAnswer(Object.fromEntries(job.questions.map((x) => [x.key, ""])))
        }
      >
        AI가 가정하고 바로 진행
      </button>
    </div>
  );
}

export default function Chat({
  bundle,
  health,
  selected,
  onClear,
  onSend,
  onAnswer,
  onCancel,
  onReview,
  onRetry,
  working,
}: {
  bundle: Bundle;
  health: Health;
  selected: { id: string; title: string } | null;
  onClear: () => void;
  onSend: (text: string) => void;
  onAnswer: (a: Record<string, string>) => void;
  onCancel: () => void;
  onReview: () => void;
  onRetry: () => void;
  working: boolean;
}) {
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const job = bundle.job;
  const busy = !!job && busyStatuses.includes(job.status);
  const locked = busy || !!bundle.proposal || !bundle.project.current_version;
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [bundle.messages.length, job?.status]);
  const send = () => {
    if (text.trim() && !working && !locked) {
      onSend(text.trim());
      setText("");
    }
  };
  return (
    <>
      <div className="panel-heading">
        <div>
          <Sparkles size={17} />
          <strong>기획 파트너</strong>
        </div>
        <span className="subtle">AI</span>
      </div>
      <div className="chat-history">
        <div className="chat-intro">
          <span className="assistant-avatar">
            <Sparkles size={17} />
          </span>
          <h3>생각을 함께 구체화해요.</h3>
          <p>
            아이디어를 정리하고, 연결된 기획을
            <br />한 단계씩 만들어 갈게요.
          </p>
        </div>
        {bundle.messages.map((message) => (
          <div key={message.id} className={`message ${message.role}`}>
            {message.role === "assistant" && (
              <div className="message-name">
                <Sparkles size={12} /> 기획 파트너
              </div>
            )}
            <div>{message.content}</div>
          </div>
        ))}
        {job?.status === "awaiting_answers" && (
          <Questions
            key={job.id}
            job={job}
            onAnswer={onAnswer}
            working={working}
          />
        )}{" "}
        {job && ["queued", "running"].includes(job.status) && (
          <Progress job={job} />
        )}{" "}
        {bundle.proposal && (
          <button className="review-chat-card" onClick={onReview}>
            <span>
              <Check size={17} /> 초안이 준비됐어요
            </span>
            <small>
              {bundle.proposal.diff.length}개 변경 · 검토하고 확정하기
            </small>
            <ChevronRight size={18} />
          </button>
        )}
        {job &&
          ["failed", "cancelled"].includes(job.status) &&
          !bundle.proposal && (
            <div className="job-error">
              <strong>
                {job.status === "failed"
                  ? "생성을 완료하지 못했어요"
                  : "실행이 취소됐어요"}
              </strong>
              <p>{job.error || "확정된 기획은 그대로 유지됩니다."}</p>
              <button
                className="secondary small"
                onClick={onRetry}
                disabled={working}
              >
                다시 시도
              </button>
            </div>
          )}
        <div ref={bottom} />
      </div>
      <div className="composer-area">
        {selected && (
          <div className="mention">
            <span>@ {selected.title}</span>
            <button aria-label="항목 선택 해제" onClick={onClear}>
              <X size={12} />
            </button>
          </div>
        )}
        <div className={`composer ${locked ? "is-locked" : ""}`}>
          <textarea
            aria-label="AI 수정 요청"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            disabled={locked || working}
            placeholder={
              bundle.proposal
                ? "초안을 먼저 검토하고 확정해 주세요"
                : busy
                  ? "답변을 확인하고 기획을 만드는 중이에요"
                  : "어떤 부분을 함께 다듬어 볼까요?"
            }
          />
          <div className="composer-bottom">
            <span className="model-label">
              <span className="status-dot" />
              {health.ai_mode === "mock"
                ? "로컬 데모"
                : health.model.replace("openai/", "")}
            </span>
            {busy ? (
              <button
                className="icon-button stop"
                aria-label="AI 실행 취소"
                onClick={onCancel}
                disabled={working}
              >
                <Square size={13} />
              </button>
            ) : (
              <button
                className="send-button"
                aria-label="수정 요청 보내기"
                disabled={locked || !text.trim() || working}
                onClick={send}
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </div>
        <div className="composer-hint">
          {health.ai_mode === "mock"
            ? "데모 모드 · 예시 결과로 동작합니다"
            : "AI가 작성한 내용은 검토 후 확정해 주세요"}
        </div>
      </div>
    </>
  );
}
