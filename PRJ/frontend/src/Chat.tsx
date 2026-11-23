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
import { readTabDraft, removeTabDraft, tabDraftKey, useTabDraft } from "./drafts";

export const busyStatuses = ["queued", "running", "awaiting_answers"];
const stages = [
  ["questions", "방향 확인"],
  ["prd", "기획 내용 정리"],
  ["features", "기능 상세 작성"],
  ["flow", "업무 흐름 연결"],
  ["wireframes", "화면 시안 작성"],
  ["implementation", "전달 자료 정리"],
  ["validation", "내용 연결 확인"],
];
export function Progress({ job }: { job: Job }) {
  const phases =
    job.kind === "discuss"
      ? [["discuss", "말씀하신 업무를 정리하고 있어요"]]
      : job.kind === "revise" || job.kind === "repair"
        ? [
            [
              job.kind,
              job.kind === "repair"
                ? "시안과 업무 연결 오류 정리"
                : "요청한 항목 수정",
            ],
            ["validation", "연결과 변경 검증"],
          ]
        : stages;
  const current = phases.findIndex(([key]) => key === job.stage);
  return (
    <div className="generation-progress">
      <div className="eyebrow">
        <LoaderCircle size={13} className="spin" />{" "}
        {job.kind === "discuss"
          ? "말씀하신 내용을 정리하는 중"
          : job.kind === "repair"
            ? "기획 연결을 정리하는 중"
            : job.kind === "revise"
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
  draftScope,
}: {
  draftScope: string;
  job: Job;
  onAnswer: (answers: Record<string, string>) => Promise<boolean>;
  working: boolean;
}) {
  const [draft, setDraft, clearDraft] = useTabDraft(
    tabDraftKey(draftScope, "questions", job.id),
    { step: 0, answers: {} as Record<string, string> },
  );
  const { step, answers } = draft;
  const setStep = (step: number) => setDraft({ ...draft, step });
  const setAnswers = (answers: Record<string, string>) => setDraft({ ...draft, answers });
  const submit = async (answers: Record<string, string>) => {
    if (await onAnswer(answers)) clearDraft();
  };
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
              : submit(
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
          submit(Object.fromEntries(job.questions.map((x) => [x.key, ""])))
        }
      >
        AI가 가정하고 바로 진행
      </button>
    </div>
  );
}

type DialogueQuestion = { key: string; title: string; options: string[] };
function DialogueQuestionCard({
  question,
  onSend,
  working,
  draftKey,
  onDraftChange,
}: {
  draftKey: string;
  onDraftChange: (key: string, pending: boolean) => void;
  question: DialogueQuestion;
  onSend: (text: string) => Promise<boolean>;
  working: boolean;
}) {
  const [draft, setDraft, clearDraft] = useTabDraft(
    draftKey, { choice: null as string | null, custom: "", sent: false },
  );
  const { choice, custom, sent } = draft;
  const setChoice = (choice: string) => setDraft({ ...draft, choice });
  const setCustom = (custom: string) => setDraft({ ...draft, custom });
  useEffect(() => {
    onDraftChange(draftKey, !sent && !!(choice || custom.trim()));
  }, [draftKey, choice, custom, sent, onDraftChange]);
  const [sending, setSending] = useState(false);
  const answer = choice === "custom" ? custom.trim() : choice;
  if (sent) return null;
  return (
    <div
      className="question-card dialogue-question"
      aria-label="업무 확인 질문"
    >
      <div className="eyebrow">함께 정할 내용</div>
      <h3>{question.title}</h3>
      <div className="question-options">
        {question.options.map((option, index) => (
          <button
            key={index}
            className={choice === String(index) ? "chosen" : ""}
            aria-pressed={choice === String(index)}
            disabled={working || sending}
            onClick={() => setChoice(String(index))}
          >
            {option}
            {choice === String(index) && <Check size={15} />}
          </button>
        ))}
        <button
          className={choice === "undecided" ? "chosen" : ""}
          aria-pressed={choice === "undecided"}
          disabled={working || sending}
          onClick={() => setChoice("undecided")}
        >
          아직 미정이에요
        </button>
        <button
          className={choice === "custom" ? "chosen" : ""}
          aria-pressed={choice === "custom"}
          disabled={working || sending}
          onClick={() => setChoice("custom")}
        >
          직접 입력{choice === "custom" && <Check size={15} />}
        </button>
      </div>
      {choice === "custom" && (
        <textarea
          aria-label="질문 직접 답변"
          maxLength={4000}
          placeholder="우리 업무에 맞는 답변을 적어 주세요"
          value={custom}
          disabled={working || sending}
          onChange={(e) => setCustom(e.target.value)}
        />
      )}
      <div className="question-footer">
        <span>자유롭게 대화를 이어가도 좋아요</span>
        <button
          className="primary small"
          disabled={!answer || working || sending}
          onClick={async () => {
            if (!answer || sending) return;
            const value =
              choice === "custom"
                ? custom.trim()
                : choice === "undecided"
                  ? "아직 미정이에요"
                  : question.options[Number(choice)];
            setSending(true);
            try {
              if (await onSend(`${question.title}\n답변: ${value}`)) {
                clearDraft();
                setDraft({ choice: null, custom: "", sent: true });
                onDraftChange(draftKey, false);
              }
            } finally {
              setSending(false);
            }
          }}
        >
          답변 보내기
        </button>
      </div>
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
  onGenerate,
  disabled = false,
  working,
  draftScope,
  onUnsentChange,
}: {
  draftScope: string;
  onUnsentChange?: (pending: boolean) => void;
  bundle: Bundle;
  health: Health;
  selected: { id: string; title: string } | null;
  onClear: () => void;
  onSend: (text: string) => Promise<boolean>;
  onAnswer: (a: Record<string, string>) => Promise<boolean>;
  onCancel: () => void;
  onReview: () => void;
  onRetry: () => void;
  onGenerate: () => void;
  disabled?: boolean;
  working: boolean;
}) {
  const [text, setText] = useTabDraft(tabDraftKey(draftScope, "chat", "input"), "");
  const [pendingQuestions, setPendingQuestions] = useState<Record<string, boolean>>({});
  const composing = useRef(false);
  const questionDraftChanged = useRef((key: string, pending: boolean) => {
    setPendingQuestions((current) => current[key] === pending ? current : { ...current, [key]: pending });
  }).current;
  const bottom = useRef<HTMLDivElement>(null);
  const job = bundle.job;
  const busy = !!job && busyStatuses.includes(job.status);
  const locked = busy || disabled;
  const brief = bundle.project.conversation_brief;
  const discussion = job?.partial.discussion as
    | { reply?: string; suggestions?: string[]; questions?: DialogueQuestion[] }
    | undefined;
  const currentQuestions = !locked && job?.kind === "discuss" && job.status === "completed"
    ? discussion?.questions || [] : [];
  const unsent = !!text.trim() || currentQuestions.some((question) =>
    pendingQuestions[tabDraftKey(draftScope, "dialogue", `${job?.id}:${question.key}`)],
  );
  useEffect(() => { onUnsentChange?.(unsent); }, [unsent, onUnsentChange]);
  const questionSuffix = currentQuestions.map((question) =>
    `\n\n${question.title}\n${question.options.join(" / ")}`,
  ).join("");
  const latestAssistant = bundle.messages.map((message) => message.role).lastIndexOf("assistant");
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "end" });
  }, [bundle.messages.length, job?.status]);
  const send = async () => {
    if (text.trim() && !working && !locked) {
      const sent = text;
      const sentKey = tabDraftKey(draftScope, "chat", "input");
      if (await onSend(sent.trim())) {
        const saved = readTabDraft<string | null>(sentKey, null);
        if (saved === sent) removeTabDraft(sentKey);
        if (saved === sent || saved === null)
          setText((current) => (current === sent ? "" : current));
      }
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
          <h3>업무를 함께 정리해요.</h3>
          <p>
            현재 업무와 바꾸고 싶은 점을 이야기해 주세요.
            <br />
            업무 내용이 정리되면 초안을 만들 수 있어요.
          </p>
        </div>
        {bundle.messages.map((message, index) => (
          <div key={message.id} className={`message ${message.role}`}>
            {message.role === "assistant" && (
              <div className="message-name">
                <Sparkles size={12} /> 기획 파트너
              </div>
            )}
            <div>{index === latestAssistant && questionSuffix && message.content.endsWith(questionSuffix)
              ? message.content.slice(0, -questionSuffix.length)
              : message.content}</div>
          </div>
        ))}
        {job?.status === "awaiting_answers" && (
          <Questions
            key={job.id}
            draftScope={draftScope}
            job={job}
            onAnswer={onAnswer}
            working={working}
          />
        )}{" "}
        {job && ["queued", "running"].includes(job.status) && (
          <Progress job={job} />
        )}{" "}
        {currentQuestions.map((question) => (
          <DialogueQuestionCard
            key={`${job?.id}:${question.key}`}
            draftKey={tabDraftKey(draftScope, "dialogue", `${job?.id}:${question.key}`)}
            onDraftChange={questionDraftChanged}
            question={question}
            onSend={onSend}
            working={working}
          />
        ))}
        {bundle.proposal && (
          <button
            className="review-chat-card"
            data-proposal-id={bundle.proposal.id}
            onClick={onReview}
          >
            <span>
              <Check size={17} /> 초안이 준비됐어요
            </span>
            <small>변경 내용을 확인하거나 대화로 더 다듬어 보세요</small>
            <ChevronRight size={18} />
          </button>
        )}
        {job && ["failed", "cancelled"].includes(job.status) && (
          <div className="job-error">
            <strong>
              {job.status === "failed"
                ? "이번 작업을 완료하지 못했어요"
                : "실행이 취소됐어요"}
            </strong>
            <p>
              {job.error || "이전 초안과 현업 확인본은 그대로 남아 있어요."}
            </p>
            <button
              className="secondary small"
              onClick={onRetry}
              disabled={working || disabled || unsent}
            >
              다시 시도
            </button>
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="composer-area">
        {brief && (
          <details className="conversation-brief">
            <summary>지금까지 정리한 업무</summary>
            <dl>
              <dt>현재 업무</dt>
              <dd>{brief.current_work || "확인 중"}</dd>
              <dt>불편한 점</dt>
              <dd>{brief.problem || "확인 중"}</dd>
              <dt>원하는 변화</dt>
              <dd>{brief.desired_change || "확인 중"}</dd>
              {brief.confirmed_facts.length > 0 && (
                <>
                  <dt>기존 시스템에서 확인</dt>
                  <dd>{brief.confirmed_facts.join("\n")}</dd>
                </>
              )}
              {brief.user_statements.length > 0 && (
                <>
                  <dt>말씀해 주신 내용</dt>
                  <dd>{brief.user_statements.join("\n")}</dd>
                </>
              )}
              {brief.open_questions.length > 0 && (
                <>
                  <dt>더 확인할 내용</dt>
                  <dd>{brief.open_questions.join("\n")}</dd>
                </>
              )}
            </dl>
          </details>
        )}
        {!busy &&
        !discussion?.questions?.length &&
        discussion?.suggestions?.length ? (
          <div className="chat-suggestions">
            {discussion.suggestions.map((suggestion) => (
              <button
                className="secondary small"
                key={suggestion}
                onClick={() => setText(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}
        {selected && (
          <div className="mention">
            <span>선택한 항목 수정하기 · {selected.title}</span>
            <button aria-label="항목 선택 해제" onClick={onClear}>
              <X size={12} />
            </button>
          </div>
        )}
        <div className={`composer ${locked ? "is-locked" : ""}`}>
          <textarea
            aria-label="업무 대화 입력"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onCompositionStart={() => { composing.current = true; }}
            onCompositionEnd={() => { composing.current = false; }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !composing.current && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) {
                e.preventDefault();
                send();
              }
            }}
            maxLength={8000}
            disabled={disabled}
            placeholder={
              disabled
                ? "편집을 마치거나 현재 기획으로 돌아온 뒤 대화해 주세요"
                : busy
                  ? "답변을 확인하고 기획을 만드는 중이에요"
                  : "업무 설명이나 바꾸고 싶은 점을 적어 주세요"
            }
          />
          <div className="composer-bottom">
            <span className="model-label">
              <span className="status-dot" />
              {health.ai_mode === "mock" ? "로컬 데모" : "업무 기획 AI"}
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
                aria-label="업무 대화 보내기"
                disabled={locked || !text.trim() || working}
                onClick={send}
              >
                <ArrowUp size={18} />
              </button>
            )}
          </div>
        </div>
        <button
          className="primary draft-action"
          disabled={locked || working || !brief || unsent}
          onClick={onGenerate}
        >
          <Sparkles size={16} />
          {bundle.proposal || bundle.project.current_version
            ? "수정안 만들기"
            : "기획 초안 만들기"}
        </button>
        {unsent && <p className="composer-unsent" role="status">입력한 내용을 먼저 보내면 초안에 반영할 수 있어요.</p>}
        <div className="composer-hint">
          {health.ai_mode === "mock"
            ? "데모 모드 · 예시 결과로 동작합니다"
            : "AI가 작성한 내용은 검토 후 확정해 주세요"}
        </div>
      </div>
    </>
  );
}
