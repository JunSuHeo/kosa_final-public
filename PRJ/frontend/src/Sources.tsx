import { useState } from "react";
import { GitBranch, Plus, X } from "lucide-react";
import { api } from "./api";
import type { CodeEvidence, Snapshot, Source, SourcePreview } from "./types";

export const sourceStatus = (source: Source) => {
  if (source.last_error) return "접근 실패";
  return source.status ? { queued: "대기", running: "분석 중", ready: "준비 완료", failed: "분석 실패" }[source.status] : "미분석";
};

const exclusionLabels: Record<string, string> = {
  non_regular: "심볼릭 링크·하위 저장소",
  excluded_directory: "제외 디렉터리",
  excluded_file_type: "제외 파일 형식",
  file_limit: "개별 파일 상한",
  sensitive_or_invalid_name: "민감하거나 지원되지 않는 이름",
  analysis_limit: "읽기 범위 상한",
  tree_truncated: "원격 트리 일부만 제공됨",
  binary: "비텍스트",
  sensitive_content: "민감 패턴 감지",
};

export function SourcePicker({
  sources, selected, onSelect, refresh, onError,
}: {
  sources: Source[];
  selected: Source | undefined;
  onSelect: (id: string) => void;
  refresh: () => Promise<void>;
  onError: (error: unknown) => void;
}) {
  const [kind, setKind] = useState<Source["kind"]>("local");
  const [working, setWorking] = useState(false);
  const [registering, setRegistering] = useState(false);
  async function run(action: () => Promise<void>) {
    setWorking(true);
    try {
      await action();
    } catch (error) {
      onError(error);
    } finally {
      setWorking(false);
    }
  }
  return (
    <section className="source-picker" aria-label="기준 프로젝트">
      <div className="source-picker-heading">
        <label htmlFor="source-choice"><GitBranch size={14} aria-hidden="true" /> 어떤 프로젝트를 기획할까요?</label>
        <button type="button" className="source-register-toggle" aria-expanded={registering} aria-controls="source-registration"
          onClick={() => setRegistering(!registering)}>
          {registering ? <X size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
          {registering ? "등록 닫기" : "기준 프로젝트 등록"}
        </button>
      </div>
      <select id="source-choice" value={selected?.id || ""} onChange={(event) => onSelect(event.target.value)}>
        <option value="">연결할 업무를 선택해 주세요</option>
        {sources.map((source) => <option key={source.id} value={source.id}>{source.name} · {sourceStatus(source)}</option>)}
      </select>
      {selected && (
        <div className="source-details">
          <strong>{selected.name} · {sourceStatus(selected)}</strong>
          <div>{selected.repository} · {selected.ref} {selected.commit_sha && <code>{selected.commit_sha}</code>}</div>
          {selected.description && <p>{selected.description}</p>}
          {selected.working_tree_dirty && <p>미커밋 변경 감지. 기준 커밋의 내용만 분석합니다.</p>}
          {(selected.last_error || selected.error) && <p role="alert">{selected.last_error || selected.error}</p>}
          <div className="source-actions">
            <button className="secondary" disabled={working} onClick={() => run(async () => {
              await api(`/api/sources/${selected.id}/analyze`, {});
              await refresh();
            })}>{selected.current_snapshot_id ? "최신 커밋 확인" : "코드 분석 시작"}</button>
            {selected.status === "failed" && selected.current_snapshot_id && (
              <button className="secondary" disabled={working} onClick={() => run(async () => {
                await api(`/api/sources/${selected.id}/snapshots/${selected.current_snapshot_id}/retry`, {});
                await refresh();
              })}>같은 커밋 다시 분석</button>
            )}
          </div>
        </div>
      )}
      <form id="source-registration" className="source-registration" hidden={!registering} onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          run(async () => {
            const { analysisPaths, ...fields } = Object.fromEntries(form);
            const source = await api<Source>("/api/sources", {
              ...fields, analysis_paths: String(analysisPaths || "").split(",").map((path) => path.trim()).filter(Boolean),
            });
            onSelect(source.id);
            setRegistering(false);
            await refresh();
            await api(`/api/sources/${source.id}/analyze`, {});
            await refresh();
          });
        }}>
          <label>연결 유형
            <select name="kind" value={kind} onChange={(event) => setKind(event.target.value as Source["kind"])}>
              <option value="local">로컬 저장소</option><option value="github">GitHub</option>
            </select>
          </label>
          <label>이름 <input name="name" required maxLength={150} /></label>
          <label>저장소 <input name="repository" required maxLength={300} placeholder={kind === "local" ? "허용 루트 아래의 상대 경로" : "https://github.com/owner/repository"} /></label>
          <label>브랜치 <input key={kind} name="ref" required maxLength={250} defaultValue={kind === "local" ? "HEAD" : "main"} /></label>
          <label>분석 우선 경로 <input name="analysisPaths" placeholder="예: frontend/src, tests" /></label>
          <label>설명 <input name="description" maxLength={1000} /></label>
          <p className="subtle">GitHub 비공개 저장소는 관리자에게 연결된 계정별 읽기 권한이 필요합니다.</p>
          <button className="secondary" disabled={working}>등록하고 분석</button>
      </form>
    </section>
  );
}

export function Evidence({ evidence, selected }: { evidence: CodeEvidence[]; selected?: string | null }) {
  return evidence.map((item) => (
    <details id={item.id} className="source-evidence" key={item.id} open={selected === item.id || undefined}>
      <summary><code>{item.path}:{item.start_line}–{item.end_line}</code> · {item.id}</summary>
      <small>SHA-256 {item.sha256}</small>
      <pre>{item.quote}</pre>
    </details>
  ));
}

export function CodePreview({ preview, onConfirm, working }: {
  preview: SourcePreview;
  onConfirm: () => void;
  working: boolean;
}) {
  const { context, model } = preview;
  return (
    <section className="code-preview" aria-label="전달할 코드 범위">
      <h3>전달할 코드 범위</h3>
      <p>{context.name} · {context.repository} · {context.ref} · <code>{context.commit_sha}</code></p>
      {!!context.analysis_paths.length && <p>분석 우선 경로 {context.analysis_paths.join(", ")}</p>}
      <p>분석 파일 {context.files_analyzed}개 · 선택 발췌 {context.evidence.length}개</p>
      <ul>{Object.entries(context.excluded).map(([reason, count]) =>
        <li key={reason}>{exclusionLabels[reason] || reason} {count}개</li>
      )}</ul>
      <p>{model
        ? `아래 코드가 ${model.provider} / ${model.model}에 전송됩니다. 기획·검토 기록에 발췌가 보관되며 공급자 보관은 연결 정책을 따릅니다.`
        : "로컬 데모에서는 외부 AI 공급자에 코드를 전송하지 않습니다. 기획·검토 기록에 발췌가 보관됩니다."}</p>
      <Evidence evidence={context.evidence} />
      <button className="primary" disabled={working} onClick={onConfirm}>코드 범위 확인하고 기획 시작</button>
    </section>
  );
}

export function ImplementationDocument({ snapshot, selected, update }: {
  snapshot: Snapshot;
  selected: string | null;
  update?: (edit: (snapshot: Snapshot) => void) => void;
}) {
  const plan = snapshot.implementation;
  const source = snapshot.source_context;
  if (!source) return null;
  const text = (label: string, value: string, onChange: (draft: NonNullable<Snapshot["implementation"]>, value: string) => void) =>
    update ? <textarea aria-label={label} value={value} onChange={(event) => {
      const next = event.target.value;
      update((draft) => { if (draft.implementation) onChange(draft.implementation, next); });
    }} /> : <p>{value}</p>;
  return (
    <article id="source-implementation" className="implementation-document">
      <h2>구현 지침</h2>
      <p>{source.name} · <code>{source.commit_sha}</code></p>
      {plan ? (
        <>
          <h3>현재 동작</h3>{text("현재 동작", plan.current_behavior, (draft, value) => { draft.current_behavior = value; })}
          <h3>변경 후 동작</h3>{text("변경 후 동작", plan.proposed_behavior, (draft, value) => { draft.proposed_behavior = value; })}
          {([
            ["확정 정책", plan.confirmed_policy], ["유지 조건", plan.preserve], ["예외", plan.exceptions],
            ["추정", plan.assumptions], ["미결정", plan.unresolved],
          ] as const).map(([label, items]) => <section key={label}><h3>{label}</h3><ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul></section>)}
          <h3>적용 목록</h3>
          <ul>{plan.scope.map((item, i) => <li key={i}>{item.area} [{item.disposition}] {item.reason} · {item.evidence_ids.join(", ")}</li>)}</ul>
          <h3>구현 순서</h3>
          <ol>{plan.tasks.map((task, i) => <li key={task.id} id={task.id}>
            <strong>{task.id}</strong>{text(task.id + " 구현", task.implementation, (draft, value) => { draft.tasks[i].implementation = value; })}
            <p>기존 대상 {task.existing_targets.join(", ")} · 신규 제안 {task.proposed_targets.join(", ")}</p>
            <p>재사용 {task.reuse}</p>
            <p>요구사항 {task.requirement_ids.join(", ")} · 수용 기준 {task.acceptance_ids.join(", ")}</p>
            <p>근거 {task.evidence_ids.join(", ")}</p>
          </li>)}</ol>
          <h3>수용 테스트</h3>
          <ul>{plan.acceptance.map((item) => <li key={item.id} id={item.id}>{item.id} {item.scenario}</li>)}</ul>
        </>
      ) : <p>초안이 준비되면 현재 동작과 구현·검수 계획을 볼 수 있습니다.</p>}
      <h3>고정 코드 근거</h3>
      <Evidence evidence={source.evidence} selected={selected} />
    </article>
  );
}
