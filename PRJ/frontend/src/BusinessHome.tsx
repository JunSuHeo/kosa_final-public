import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowRight,
  FileText,
  FolderOpen,
  Home as HomeIcon,
  LoaderCircle,
  Search,
  Settings2,
} from "lucide-react";
import { api } from "./api";
import { accountService } from "./accounts";
import { tabDraftKey, useTabDraft } from "./drafts";
import type {
  Health,
  PlanningIntent,
  Project,
  BusinessSource as Source,
} from "./types";

export const intentLabels: Record<PlanningIntent, string> = {
  new_feature: "신규 기능",
  improve: "기존 기능 개선",
  process: "업무 프로세스 변경",
};
export function Brand() {
  return (
    <div className="brand">
      <span className="brand-symbol">H</span>
      <div>
        <strong>H-PlanIT</strong>
        <span>에이치플래닛</span>
      </div>
    </div>
  );
}
export function sourceAvailable(source: Source, health: Health) {
  return (
    !!source.publication_id &&
    (health.ai_mode === "mock"
      ? !source.published_model
      : source.published_model?.provider === health.provider &&
        source.published_model?.model === health.model)
  );
}
export default function BusinessHome({
  accountMenu,
  navigation,
  canCreate,
  canManage,
  canAssign,
  canRead,
  projects,
  health,
  onOpen,
  onStart,
  onSettings,
  onError,
}: {
  accountMenu: ReactNode;
  navigation: ReactNode;
  canCreate: boolean;
  canManage: boolean;
  canAssign: boolean;
  canRead: boolean;
  projects: Project[];
  health: Health;
  onOpen: (id: string) => void;
  onStart: (source: Source, intent: PlanningIntent) => void;
  onSettings: () => void;
  onError: (e: unknown) => void;
}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceId, setSourceId] = useState(
    new URLSearchParams(location.search).get("source") || "",
  );
  const [query, setQuery] = useState("");
  useEffect(() => {
    let active = true;
    api<Source[]>("/api/sources")
      .then((data) => {
        if (active) setSources(data);
      })
      .catch(onError)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [onError]);
  useEffect(() => {
    let active = true;
    const refreshSources = () => {
      void api<Source[]>("/api/sources")
        .then((data) => {
          if (active) setSources(data);
        })
        .catch(onError);
    };
    const unsubscribe =
      health.auth_mode === "mock"
        ? accountService.subscribe(refreshSources)
        : () => {};
    window.addEventListener("focus", refreshSources);
    return () => {
      active = false;
      unsubscribe();
      window.removeEventListener("focus", refreshSources);
    };
  }, [health.auth_mode, onError]);
  useEffect(() => {
    if (
      sourceId &&
      canManage &&
      sources.some((s) => s.id === sourceId && s.can_manage)
    )
      void api(`/api/sources/${sourceId}/check`, {}).catch(onError);
  }, [sourceId, canManage, sources, onError]);
  const shown = projects.filter(
    (p) =>
      (!sourceId || p.source_id === sourceId) &&
      `${p.title} ${p.idea}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="business-home">
      <header className="business-header">
        <div className="header-brand">
          {navigation}
          <Brand />
        </div>
        <div className="business-header-actions">
          {!navigation && (canManage || canAssign) && (
            <button className="secondary" onClick={onSettings}>
              <Settings2 size={16} />{" "}
              {canManage ? "업무 연결 설정" : "업무 배정"}
            </button>
          )}
          {accountMenu}
        </div>
      </header>
      <main className="business-home-main">
        <div className="page-heading">
          <span className="eyebrow">업무 기획</span>
          <h1>어떤 업무를 기획하시겠어요?</h1>
          <p>업무를 선택하고, 바꾸고 싶은 내용을 이야기해 주세요.</p>
        </div>
        <section className="home-step" aria-label="업무 선택">
          <h2>
            기획할 업무 선택
          </h2>
          {loading ? (
            <p role="status">
              <LoaderCircle className="spin" size={16} /> 업무를 불러오는
              중이에요.
            </p>
          ) : sources.length ? (
            <div className="business-grid">
              {sources.map((source) => {
                const available = sourceAvailable(source, health);
                return (
                  <button
                    key={source.id}
                    data-source-id={source.id}
                    className="business-card"
                    disabled={!canCreate || !available}
                    onClick={() => onStart(source, "improve")}
                  >
                    <span className="business-card-top">
                      <FolderOpen size={23} />
                      <span className="business-status">
                        {available ? "대화 시작하기" : "연결 준비 필요"}
                      </span>
                    </span>
                    <strong>{source.name}</strong>
                    <p>
                      {source.description ||
                        "이 업무의 기존 기능을 바탕으로 기획합니다."}
                    </p>
                    {source.published_at && (
                      <small>
                        게시 기준 ·{" "}
                        {new Date(source.published_at).toLocaleDateString(
                          "ko-KR",
                        )}
                      </small>
                    )}
                    {!available && (
                      <small>IT 담당자의 업무 연결 준비가 필요합니다.</small>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="home-empty">
              <FolderOpen size={28} />
              <h3>연결된 업무가 없어요</h3>
              <p>IT 담당자에게 기획할 업무의 연결을 요청해 주세요.</p>
            </div>
          )}
        </section>
        <section className="my-plans">
          <div className="projects-heading">
            <h2>
              내 기획 <span>{shown.length}</span>
            </h2>
            <div className="plan-filters">
              <select aria-label="내 기획 업무 필터" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
                <option value="">모든 업무</option>
                {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
              </select>
              {sourceId && <button className="text-button" onClick={() => setSourceId("")}>필터 초기화</button>}
            <div className="search-field">
              <Search size={16} />
              <input
                aria-label="기획 검색"
                placeholder="기획 검색"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            </div>
          </div>
          {!canRead ? (
            <p className="access-notice">
              기획 조회 권한이 없습니다. 관리자에게 문의해 주세요.
            </p>
          ) : shown.length ? (
            <div className="project-grid">
              {shown.map((project) => {
                const progress = {
                  conversation: ["대화 중", "대화 이어가기"],
                  awaiting_answers: ["답변 기다리는 중", "질문에 답하기"],
                  generating: ["초안 만드는 중", "진행 확인하기"],
                  review_ready: ["초안 준비됨", "초안 확인하기"],
                  failed: ["작업 중단됨", "다시 시도하기"],
                  confirmed: ["현업 확인 완료", "확인본 보기"],
                }[project.progress_status || (project.current_version ? "confirmed" : "conversation")];
                return (
                <button
                  className="project-card"
                  key={project.id}
                  onClick={() => onOpen(project.id)}
                >
                  <div className="project-card-top">
                    <FileText size={21} />
                    <ArrowRight size={17} />
                  </div>
                  <h3>{project.title}</h3>
                  <p>{project.idea}</p>
                  <div>
                    <span className="version-tag">
                      {progress[0]}
                    </span>
                    <small>
                      {new Date(project.updated_at).toLocaleDateString("ko-KR")}
                    </small>
                  </div>
                  <span className="project-next-action">{progress[1]} <ArrowRight size={14} /></span>
                </button>
              ); })}
            </div>
          ) : (
            <div className="home-empty">
              <FileText size={26} />
              <p>
                {query
                  ? "검색한 기획이 없어요."
                  : "아직 작성한 기획이 없어요. 업무를 선택해 시작해 보세요."}
              </p>
            </div>
          )}
        </section>
      </main>
      <footer className="business-footer">
        H-PlanIT
        {health.auth_mode === "mock" && (
          <span>
            로컬 인증 ·{" "}
            {health.ai_mode === "mock" ? "예시 AI 결과" : "실제 AI 연결"}
          </span>
        )}
      </footer>
    </div>
  );
}

export function Intake({
  accountMenu,
  navigation,
  health,
  onHome,
  onCreate,
  onError,
  working,
  draftOwner,
}: {
  draftOwner: string;
  health: Health;
  onHome: () => void;
  accountMenu: ReactNode;
  navigation: ReactNode;
  onCreate: (text: string, source: Source, intent: PlanningIntent) => Promise<boolean>;
  onError: (e: unknown) => void;
  working: boolean;
}) {
  const [source, setSource] = useState<Source | null>(null);
  const [loaded, setLoaded] = useState(false);
  const params = new URLSearchParams(location.search);
  const sourceId = params.get("source");
  const initialIntent = (
    (params.get("intent") || "") in intentLabels
      ? params.get("intent")
      : "improve"
  ) as PlanningIntent;
  const [draft, setDraft, clearDraft] = useTabDraft(
    tabDraftKey(draftOwner, "intake", sourceId || "none"),
    { text: "", intent: initialIntent },
  );
  const { text, intent } = draft;
  useEffect(() => {
    api<Source[]>("/api/sources")
      .then((data) => setSource(data.find((s) => s.id === sourceId) || null))
      .catch(onError)
      .finally(() => setLoaded(true));
  }, [sourceId, onError]);
  return (
    <div className="intake-page">
      <header className="business-header">
        <div className="header-brand">
          {navigation}
          <Brand />
        </div>
        <div className="business-header-actions">
          <button className="secondary" onClick={onHome}>
            <HomeIcon size={16} /> 업무 선택
          </button>
          {accountMenu}
        </div>
      </header>
      <main className="intake-main">
        <span className="eyebrow">
          {source?.name || "업무 불러오는 중"} · {intentLabels[intent]}
        </span>
        <h1>바꾸고 싶은 업무를 이야기해 주세요.</h1>
        <div className="intake-greeting">
          <span className="assistant-avatar">H</span>
          <div>
            <strong>업무 기획 파트너</strong>
            <p>
              {source?.description ||
                "기존 업무를 바탕으로 기획을 함께 정리하겠습니다."}
              <br />
              지금 어떻게 일하고 있고, 어떤 점이 불편한가요?
            </p>
          </div>
        </div>
        {loaded && (!source || !sourceAvailable(source, health)) ? (
          <div className="job-error">
            <p>업무 연결 준비가 필요합니다. IT 담당자에게 요청해 주세요.</p>
            <button className="secondary" onClick={onHome}>
              업무 선택으로 돌아가기
            </button>
          </div>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!working && source && text.trim().length >= 3 && await onCreate(text.trim(), source, intent))
                clearDraft();
            }}
          >
            <label htmlFor="planning-intent">기획 유형 (선택)</label>
            <select id="planning-intent" value={intent} disabled={working} onChange={(e) => setDraft({ ...draft, intent: e.target.value as PlanningIntent })}>
              {Object.entries(intentLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <label htmlFor="first-message">업무 설명</label>
            <textarea
              id="first-message"
              value={text}
              onChange={(e) => setDraft({ ...draft, text: e.target.value })}
              maxLength={8000}
              placeholder="현재 업무와 바꾸고 싶은 점을 편하게 적어 주세요."
              disabled={working}
            />
            <div className="intake-actions">
              <span>입력한 내용은 이 탭에서 임시 저장됩니다.</span>
              <button
                className="primary"
                disabled={working || !source || text.trim().length < 3}
              >
                {working ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <ArrowRight size={16} />
                )}{" "}
                업무 대화 시작
              </button>
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
