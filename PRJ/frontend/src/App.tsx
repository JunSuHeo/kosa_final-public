import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  GitBranch,
  GitCompareArrows,
  History,
  LayoutDashboard,
  LayoutTemplate,
  LoaderCircle,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { api, ApiError, download, setToken } from "./api";
import type {
  Bundle,
  Health,
  Panel,
  Project,
  Revision,
  Snapshot,
  Source,
  SourcePreview,
  SourceSelection,
  Tab,
} from "./types";
import Chat, { busyStatuses } from "./Chat";
import Review from "./Review";
import { Canvas, FeaturesView, Inspector, PrdDocument } from "./Documents";
import Wireframes from "./Wireframes";
import { CodePreview, ImplementationDocument, SourcePicker } from "./Sources";

const tabs: { id: Tab; label: string; icon: typeof FileText }[] = [
  { id: "prd", label: "PRD", icon: FileText },
  { id: "features", label: "기능명세서", icon: LayoutDashboard },
  { id: "flow", label: "유저플로우", icon: GitBranch },
  { id: "wireframes", label: "와이어프레임", icon: LayoutTemplate },
];
function hasArtifact(snapshot: Snapshot, tab: Tab) {
  const content = {
    prd: snapshot.prd.sections.length,
    features: snapshot.requirements.length || snapshot.features.length,
    flow: snapshot.flow.nodes.length,
    wireframes: snapshot.screens.length,
    implementation: snapshot.implementation,
  };
  return Boolean(content[tab]);
}
const panels: { id: Panel; label: string; icon: typeof FileText }[] = [
  { id: "chat", label: "채팅", icon: MessageSquare },
  { id: "review", label: "검토", icon: GitCompareArrows },
  { id: "documents", label: "문서", icon: FolderOpen },
  { id: "versions", label: "버전", icon: History },
];
const examples = [
  {
    title: "팀 일정 관리",
    tag: "업무 도구",
    idea: "작은 팀이 프로젝트 일정과 할 일을 함께 관리하는 웹 서비스. 담당자와 마감일을 지정하고 진행 상태를 한눈에 확인하고 싶어요.",
    icon: LayoutDashboard,
  },
  {
    title: "동네 취미 모임",
    tag: "커뮤니티",
    idea: "동네에서 같은 취미를 가진 사람들이 소규모 모임을 만들고 참여하는 모바일 앱을 기획해줘.",
    icon: MessageSquare,
  },
  {
    title: "나만의 독서 기록",
    tag: "라이프스타일",
    idea: "읽은 책과 인상 깊은 문장을 기록하고 나의 독서 습관을 돌아보는 모바일 앱을 만들고 싶어요.",
    icon: FileText,
  },
];
const projectFromURL = () =>
  new URLSearchParams(window.location.search).get("project");
const relativeTime = (date: string) => {
  const mins = Math.floor((Date.now() - new Date(date).getTime()) / 60000);
  return mins < 1
    ? "방금 전"
    : mins < 60
      ? `${mins}분 전`
      : mins < 1440
        ? `${Math.floor(mins / 60)}시간 전`
        : new Date(date).toLocaleDateString("ko-KR");
};

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`logo ${compact ? "compact" : ""}`}>
      <span className="logo-mark">
        <i />
        <i />
        <i />
      </span>
      {!compact && (
        <>
          <strong>기획실</strong>
          <small>STUDIO</small>
        </>
      )}
    </div>
  );
}

function Home({
  projects,
  health,
  onOpen,
  onCreate,
  working,
  onError,
}: {
  projects: Project[];
  health: Health;
  onOpen: (id: string) => void;
  onCreate: (idea: string, source?: SourceSelection) => void;
  onError: (error: unknown) => void;
  working: boolean;
}) {
  const params = new URLSearchParams(window.location.search);
  const [sourceId, setSourceId] = useState(params.get("source") || "");
  const [forkId, setForkId] = useState(params.get("from") || "");
  const origin = projects.find((p) => p.id === forkId && p.source_id === sourceId);
  const [idea, setIdea] = useState(origin?.idea || "");
  const [search, setSearch] = useState("");
  useEffect(() => {
    if (origin) setIdea((current) => current || origin.idea);
  }, [origin]);
  const [sources, setSources] = useState<Source[]>([]);
  const [preview, setPreview] = useState<SourcePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const selectedSource = sources.find((source) => source.id === sourceId);
  const ready = selectedSource?.status === "ready" && !selectedSource.last_error
    && selectedSource.current_snapshot_id !== origin?.code_snapshot_id;
  const shownProjects = projects.filter((p) => (p.source_id || "") === sourceId);
  const refreshSources = useCallback(async () => setSources(await api<Source[]>("/api/sources")), []);
  useEffect(() => { refreshSources().catch(onError); }, [refreshSources, onError]);
  const analyzing = sources.some((source) => source.status === "queued" || source.status === "running");
  useEffect(() => {
    if (!analyzing) return;
    const timer = setInterval(() => refreshSources().catch(onError), 1400);
    return () => clearInterval(timer);
  }, [analyzing, refreshSources, onError]);
  const changeSource = (id: string) => {
    setSourceId(id);
    setForkId("");
    setPreview(null);
    window.history.replaceState({}, "", id ? `/?source=${encodeURIComponent(id)}` : "/");
  };
  const start = async () => {
    if (!sourceId) return onCreate(idea.trim());
    if (!ready || !selectedSource.current_snapshot_id || previewing) return;
    setPreviewing(true);
    try {
      setPreview(await api<SourcePreview>(
        `/api/sources/${sourceId}/snapshots/${selectedSource.current_snapshot_id}/preview`,
        { idea: idea.trim() },
      ));
    } catch (error) {
      onError(error);
    } finally {
      setPreviewing(false);
    }
  };
  const shownPreview = preview?.context.source_id === sourceId &&
    preview.context.snapshot_id === selectedSource?.current_snapshot_id ? preview : null;
  return (
    <div className="home">
      <header className="home-header">
        <Logo />
        <div className="home-header-right">
          <span className="environment-tag">
            <span className="status-dot" />
            {health.ai_mode === "mock" ? "로컬 데모" : "AI 연결됨"}
          </span>
          <span className="avatar">나</span>
        </div>
      </header>
      <main className="home-main">
        <div className="home-hero">
          <span className="hero-badge">
            <Sparkles size={13} /> 생각의 다음 단계를 함께
          </span>
          <h1>
            어떤 제품을
            <br />
            <span>만들고 싶으세요?</span>
          </h1>
          <p>
            아이디어 하나에서 시작해 보세요.
            <br />
            PRD부터 화면 설계까지, 기획 파트너가 함께할게요.
          </p>
        </div>
        <div className="planning-composer">
          <SourcePicker sources={sources} selected={selectedSource} onSelect={changeSource} refresh={refreshSources} onError={onError} />
          {origin && <p className="source-fork">이전 기획에서 분기 · {origin.title}</p>}
          <form
            className="idea-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (idea.trim().length >= 3) void start();
            }}
          >
            <textarea
              aria-label="만들고 싶은 제품 아이디어"
              value={idea}
              onChange={(e) => { setIdea(e.target.value); setPreview(null); }}
              disabled={previewing || working}
              placeholder={sourceId ? "기준 프로젝트에 추가하거나 개선할 기능을 입력하세요" : "예: 우리 팀의 일정과 할 일을 한눈에 관리하는 서비스를 만들고 싶어"}
              maxLength={8000}
            />
            <div>
              <span>
                <Sparkles size={14} /> 아이디어를 구체적으로 적을수록 좋아요
              </span>
              <button
                className="primary"
                disabled={working || previewing || idea.trim().length < 3 || (!!sourceId && !ready)}
              >
                {working ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <ArrowUpRightIcon />
                )}{" "}
                {sourceId ? "코드 범위 확인" : "기획 시작하기"}
              </button>
            </div>
          </form>
        </div>
        {shownPreview && <CodePreview preview={shownPreview} working={working || !ready} onConfirm={() =>
          onCreate(idea.trim(), { source_id: sourceId, code_snapshot_id: shownPreview.context.snapshot_id,
            ...(origin ? { forked_from: origin.id } : {}), code_consent: shownPreview.fingerprint })
        } />}
        {!sourceId && <>
        <div className="example-label">이런 아이디어로 시작해 볼까요?</div>
        <div className="examples">
          {examples.map(({ title, tag, idea: sample, icon: Icon }) => (
            <button
              className="example-card"
              key={title}
              onClick={() => setIdea(sample)}
            >
              <span className="example-icon">
                <Icon size={18} />
              </span>
              <div>
                <small>{tag}</small>
                <strong>{title}</strong>
              </div>
              <ArrowRight size={16} />
            </button>
          ))}
        </div>
        </>}
        <section className="projects-section">
          <div className="projects-heading">
            <h2>
              {selectedSource ? `${selectedSource.name} 기획 작업` : "나의 프로젝트"} <span>{shownProjects.length}</span>
            </h2>
            <div className="search-field">
              <Search size={14} />
              <input
                aria-label="프로젝트 검색"
                placeholder="프로젝트 검색"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
          {shownProjects.length ? (
            <div className="project-grid">
              {shownProjects
                .filter((p) =>
                  p.title.toLowerCase().includes(search.toLowerCase()),
                )
                .map((p) => (
                  <button
                    className="project-card"
                    key={p.id}
                    onClick={() => onOpen(p.id)}
                  >
                    <div className="project-card-top">
                      <span className="project-icon">
                        <FileText size={20} />
                      </span>
                      <ChevronRight size={16} />
                    </div>
                    <h3>{p.title}</h3>
                    <p>{p.idea}</p>
                    <div>
                      <span className="version-tag">
                        {p.current_version
                          ? `확정 v${p.current_version}`
                          : "작성 중"}
                      </span>
                      <small>{relativeTime(p.updated_at)}</small>
                    </div>
                  </button>
                ))}
            </div>
          ) : (
            <div className="empty-projects">
              <FolderOpen size={23} />
              <p>아직 시작한 프로젝트가 없어요.</p>
              <span>위에 아이디어를 적고 첫 기획을 만들어 보세요.</span>
            </div>
          )}
        </section>
      </main>
      <footer className="home-footer">
        <span>기획실 STUDIO</span>
        <span>아이디어와 구현 사이, 더 명확한 기획.</span>
        {health.auth_mode === "mock" && (
          <span>로컬 인증 · 운영 환경 사용 금지</span>
        )}
      </footer>
    </div>
  );
}

function ArrowUpRightIcon() {
  return <ArrowRight size={16} />;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [authed, setAuthed] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(projectFromURL);
  const idRef = useRef(projectId);
  idRef.current = projectId;
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [tab, setTab] = useState<Tab>("prd");
  const [panel, setPanel] = useState<Panel>("chat");
  const [sideOpen, setSideOpen] = useState(true);
  const [candidate, setCandidate] = useState(true);
  const [historical, setHistorical] = useState<Revision | null>(null);
  const historyRequest = useRef(0);
  const [edit, setEdit] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [exportMenu, setExportMenu] = useState(false);
  const [title, setTitle] = useState("");
  const [checkedSource, setCheckedSource] = useState<{ projectId: string; commit_sha?: string; error?: string } | null>(null);
  const proposalRef = useRef<string | null>(null);
  const generationRequest = useRef(0);
  const handleError = useCallback((e: unknown) => {
    if (e instanceof DOMException && e.name === "AbortError") return;
    if (e instanceof ApiError && e.status === 401) {
      setToken("");
      setAuthed(false);
    }
    setError(e instanceof Error ? e.message : "작업을 완료하지 못했습니다.");
  }, []);
  const run = async (fn: () => Promise<void>) => {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      handleError(e);
    } finally {
      setWorking(false);
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    api<Health>("/health", undefined, undefined, controller.signal)
      .then((h) => {
        setHealth(h);
        if (h.auth_mode === "mock") {
          setToken("local:demo-user");
          setAuthed(true);
        } else setAuthed(!!sessionStorage.getItem("studio-token"));
      })
      .catch(handleError);
    return () => controller.abort();
  }, [handleError]);
  const refreshProjects = useCallback(
    async () => setProjects(await api<Project[]>("/api/projects")),
    [],
  );
  const refresh = useCallback(async () => {
    const id = idRef.current;
    if (!id) return;
    const request = ++generationRequest.current;
    const result = await api<Bundle>(`/api/projects/${id}`);
    if (idRef.current !== id || request !== generationRequest.current) return;
    setBundle(result);
    setTitle(result.project.title);
    if (result.proposal?.id && result.proposal.id !== proposalRef.current) {
      setCandidate(true);
      setHistorical(null);
      proposalRef.current = result.proposal.id;
    }
  }, []);
  useEffect(() => {
    if (authed) refreshProjects().catch(handleError);
  }, [authed, refreshProjects, handleError]);
  useEffect(() => {
    setBundle(null);
    setHistorical(null);
    setEdit(null);
    setSelected(null);
    setCandidate(true);
    proposalRef.current = null;
    historyRequest.current++;
    if (projectId && authed) refresh().catch(handleError);
  }, [projectId, authed, refresh, handleError]);
  const busy = !!bundle?.job && busyStatuses.includes(bundle.job.status);
  useEffect(() => {
    if (
      !projectId ||
      !authed ||
      !busy ||
      bundle?.job?.status === "awaiting_answers"
    )
      return;
    const timer = setInterval(() => refresh().catch(handleError), 1300);
    return () => clearInterval(timer);
  }, [projectId, authed, busy, bundle?.job?.status, refresh, handleError]);
  useEffect(() => {
    const back = () => {
      setProjectId(projectFromURL());
      setTab("prd");
    };
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);
  const navigate = (id: string | null, origin?: Project) => {
    const source = origin?.source_id;
    window.history.pushState({}, "", id ? `/?project=${id}`
      : source ? `/?source=${source}&from=${origin.id}` : "/");
    idRef.current = id;
    setProjectId(id);
    setTab("prd");
    setPanel("chat");
    setSideOpen(true);
    setError("");
    if (!id) refreshProjects().catch(handleError);
  };
  const create = (idea: string, source?: SourceSelection) =>
    run(async () => {
      const p = await api<Project>("/api/projects", {
        id: crypto.randomUUID(),
        idea,
        ...source,
      });
      await refreshProjects();
      navigate(p.id);
    });
  const update = (fn: (s: Snapshot) => void) =>
    setEdit((previous) => {
      if (!previous) return previous;
      const next = structuredClone(previous);
      fn(next);
      return next;
    });
  const changeTab = (next: Tab) => {
    setTab(next);
    setSelected(null);
    setExportMenu(false);
  };
  const snapshot =
    edit ||
    historical?.snapshot ||
    (candidate && bundle?.proposal
      ? bundle.proposal.candidate
      : bundle?.revision.snapshot);
  const basis = snapshot?.source_context;
  const visibleTabs = basis ? [...tabs, { id: "implementation" as const, label: "구현 지침", icon: FileText }] : tabs;
  const comparison = checkedSource?.projectId === projectId ? checkedSource : null;
  const isPast =
    !!historical && historical.version !== bundle?.project.current_version;
  const visibleVersion =
    historical?.version ?? bundle?.project.current_version ?? 0;
  const viewIsCandidate = !!bundle?.proposal && candidate && !historical;
  const hasAnyArtifact = snapshot && visibleTabs.some(({ id }) => hasArtifact(snapshot, id));
  const openDraft = (review = false) => {
    const draft = bundle?.proposal?.candidate;
    if (!draft || edit) return;
    historyRequest.current++;
    setHistorical(null);
    setCandidate(true);
    const firstAvailable = visibleTabs.find(({ id }) => hasArtifact(draft, id));
    if (!hasArtifact(draft, tab) && firstAvailable) changeTab(firstAvailable.id);
    if (review || !firstAvailable) {
      setPanel("review");
      setSideOpen(true);
    }
  };
  const select = (id: string) => {
    setSelected(id || null);
  };
  useEffect(() => {
    if (panel === "review" && (tab === "prd" || tab === "implementation") && selected) {
      document.getElementById(selected)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [panel, tab, selected]);
  const selectedItem =
    selected && snapshot
      ? [
          ...snapshot.prd.sections,
          ...snapshot.requirements,
          ...snapshot.features,
          ...snapshot.flow.nodes,
          ...snapshot.screens,
          ...snapshot.screens.flatMap((s) =>
            s.blocks.map((b) => ({ id: b.id, title: b.label })),
          ),
        ].find((x) => x.id === selected)
      : null;
  const submitAnswers = (answers: Record<string, string>) =>
    run(async () => {
      if (!bundle?.job) return;
      await api(`/api/projects/${projectId}/jobs/${bundle.job.id}/answers`, {
        base_version: bundle.job.base_version,
        answers,
      });
      await refresh();
    });
  const send = (request: string) =>
    run(async () => {
      if (!bundle) return;
      await api(`/api/projects/${projectId}/jobs`, {
        id: crypto.randomUUID(),
        base_version: bundle.project.current_version,
        request,
        target_id: selected,
      });
      setCandidate(false);
      setHistorical(null);
      await refresh();
    });
  const decide = (decision: "approve" | "reject", ack: boolean) =>
    run(async () => {
      if (!bundle?.proposal) return;
      await api(
        `/api/projects/${projectId}/proposals/${bundle.proposal.id}/${decision}`,
        {
          expected_version: bundle.project.current_version,
          acknowledge_warnings: ack,
        },
      );
      setCandidate(false);
      setHistorical(null);
      setEdit(null);
      await refresh();
      await refreshProjects();
    });
  const save = () =>
    run(async () => {
      if (!edit || !bundle) return;
      await api(`/api/projects/${projectId}/proposals`, {
        base_version: bundle.project.current_version,
        snapshot: edit,
        summary: "문서와 화면 직접 편집",
      });
      setEdit(null);
      setPanel("review");
      setSideOpen(true);
      await refresh();
    });
  const past = (version: number) =>
    run(async () => {
      const request = ++historyRequest.current;
      const id = projectId;
      const rev = await api<Revision>(
        `/api/projects/${id}/revisions/${version}`,
      );
      if (request !== historyRequest.current || id !== idRef.current) return;
      setHistorical(rev);
      setCandidate(false);
      setEdit(null);
      setSelected(null);
    });
  const exportFile = (format: "json" | "markdown") =>
    run(async () => {
      await download(
        `/api/projects/${projectId}/revisions/${visibleVersion}/export?format=${format}`,
      );
      setExportMenu(false);
    });
  if (!health)
    return (
      <div className="boot-screen">
        <Logo />
        <LoaderCircle className="spin" size={22} />
        {error && (
          <div role="alert">
            {error}
            <button
              className="secondary"
              onClick={() => window.location.reload()}
            >
              다시 연결
            </button>
          </div>
        )}
      </div>
    );
  if (!authed)
    return (
      <div className="login-screen">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              const result = await api<{ access_token: string }>(
                "/api/auth/login",
                { email: loginEmail, password: loginPassword },
              );
              setToken(result.access_token);
              setLoginPassword("");
              setAuthed(true);
            });
          }}
        >
          <Logo />
          <h1>생각을 이어갈 시간이에요.</h1>
          <p>등록된 계정으로 로그인해 주세요.</p>
          <label>
            이메일
            <input
              type="email"
              required
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
            />
          </label>
          <label>
            비밀번호
            <input
              type="password"
              required
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="danger-text">
              {error}
            </p>
          )}
          <button className="primary" disabled={working}>
            로그인 <ArrowRight size={16} />
          </button>
        </form>
      </div>
    );
  return (
    <>
      {error && (
        <div className="error-toast" role="alert">
          <span>{error}</span>
          <button aria-label="오류 알림 닫기" onClick={() => setError("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {!projectId ? (
        <Home
          projects={projects}
          health={health}
          onOpen={navigate}
          onError={handleError}
          onCreate={create}
          working={working}
        />
      ) : !bundle || !snapshot ? (
        <div className="boot-screen">
          <Logo />
          <LoaderCircle className="spin" />
          <button className="secondary" onClick={() => navigate(null)}>
            프로젝트 목록
          </button>
        </div>
      ) : (
        <div className="studio">
          <nav className="rail" aria-label="작업 도구">
            <button
              className="rail-logo"
              aria-label="프로젝트 목록"
              onClick={() => navigate(null)}
            >
              <Logo compact />
            </button>
            <div className="rail-items">
              {panels.map(({ id, label, icon: Icon }) => (
                <button
                  className={panel === id && sideOpen ? "active" : ""}
                  key={id}
                  onClick={() => {
                    setPanel(id);
                    setSideOpen(panel !== id || !sideOpen);
                  }}
                  title={label}
                  aria-label={label}
                >
                  <Icon size={21} />
                  <span>{label}</span>
                  {id === "review" && bundle.proposal && (
                    <i className="notification-dot" />
                  )}
                </button>
              ))}
            </div>
            <div className="rail-bottom">
              <button
                aria-label="새 프로젝트"
                onClick={() => navigate(null)}
                title="새 프로젝트"
              >
                <Plus size={21} />
                <span>새 기획</span>
              </button>
              <div
                className="avatar"
                title={health.auth_mode === "mock" ? "로컬 사용자" : "로그인됨"}
              >
                나
              </div>
            </div>
          </nav>
          {sideOpen && (
            <aside className="side-panel">
              {panel === "chat" ? (
                <Chat
                  bundle={bundle}
                  health={health}
                  selected={selectedItem || null}
                  onClear={() => setSelected(null)}
                  onSend={send}
                  onAnswer={submitAnswers}
                  onCancel={() =>
                    run(async () => {
                      await api(
                        `/api/projects/${projectId}/jobs/${bundle.job!.id}/cancel`,
                        {},
                      );
                      await refresh();
                    })
                  }
                  onReview={() => openDraft(true)}
                  onRetry={() =>
                    run(async () => {
                      await api(`/api/projects/${projectId}/jobs`, {
                        id: crypto.randomUUID(),
                        base_version: bundle.project.current_version,
                        kind: bundle.project.current_version
                          ? "revise"
                          : "generate",
                        request: bundle.job?.request || bundle.project.idea,
                      });
                      await refresh();
                    })
                  }
                  working={working}
                />
              ) : panel === "review" ? (
                <Review
                  proposal={bundle.proposal}
                  projectId={bundle.project.id}
                  proposalId={viewIsCandidate ? bundle.proposal!.id : null}
                  version={viewIsCandidate ? bundle.proposal!.base_version : visibleVersion}
                  disabled={!!edit}
                  onLocate={(id) => {
                    if (!snapshot) return;
                    if (snapshot.prd.sections.some((s) => s.id === id)) setTab("prd");
                    else if ([...snapshot.features, ...snapshot.requirements].some((s) => s.id === id)) setTab("features");
                    else if (snapshot.screens.some((s) => s.id === id || s.blocks.some((b) => b.id === id))) setTab("wireframes");
                    else if (id === "source-implementation" ||
                      snapshot.source_context?.evidence.some((item) => item.id === id) ||
                      snapshot.implementation?.tasks.some((item) => item.id === id) ||
                      snapshot.implementation?.acceptance.some((item) => item.id === id)) setTab("implementation");
                    else setTab("flow");
                    setSelected(id);
                  }}
                  onDecide={decide}
                  working={working}
                />
              ) : panel === "versions" ? (
                <>
                  <div className="panel-heading">
                    <div>
                      <History size={17} />
                      <strong>버전 기록</strong>
                    </div>
                    <span className="count-pill">
                      {bundle.revisions.length}
                    </span>
                  </div>
                  <div className="versions-list">
                    <p>확정된 기획은 버전마다 보관됩니다.</p>
                    {basis && <p>코드 기준 <code>{basis.commit_sha}</code></p>}
                    {bundle.revisions.map((rev) => (
                      <button
                        key={rev.version}
                        className={
                          visibleVersion === rev.version && !viewIsCandidate
                            ? "selected"
                            : ""
                        }
                        disabled={working || !!edit}
                        onClick={() => past(rev.version)}
                      >
                        <div className="version-line">
                          <strong>v{rev.version}</strong>
                          {rev.version === bundle.project.current_version && (
                            <span className="version-tag">현재 확정본</span>
                          )}
                        </div>
                        <span>{rev.summary}</span>
                        <small>
                          {new Date(rev.created_at).toLocaleString("ko-KR")}
                        </small>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <div className="panel-heading">
                    <div>
                      <FolderOpen size={17} />
                      <strong>문서 탐색</strong>
                    </div>
                  </div>
                  <div className="document-nav">
                    {visibleTabs.map(({ id, label, icon: Icon }) => (
                      <button
                        className={tab === id ? "active" : ""}
                        key={id}
                        onClick={() => changeTab(id)}
                      >
                        <Icon size={16} />
                        {label}
                        <ChevronRight size={14} />
                      </button>
                    ))}
                    <div className="eyebrow">PRD 항목</div>
                    {snapshot.prd.sections.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => {
                          setTab("prd");
                          setSelected(s.id);
                          setTimeout(
                            () =>
                              document
                                .getElementById(s.id)
                                ?.scrollIntoView({
                                  behavior: "smooth",
                                  block: "center",
                                }),
                            60,
                          );
                        }}
                      >
                        <span className="nav-dot" />
                        {s.title}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </aside>
          )}
          <main className="workspace">
            <header className="workspace-header">
              <button
                className="icon-button panel-toggle"
                aria-label="패널 접기 펼치기"
                onClick={() => setSideOpen(!sideOpen)}
              >
                {sideOpen ? (
                  <PanelLeftClose size={18} />
                ) : (
                  <PanelLeftOpen size={18} />
                )}
              </button>
              <input
                className="project-title"
                aria-label="프로젝트 제목"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                onBlur={() => {
                  if (title.trim() && title !== bundle.project.title)
                    run(async () => {
                      await api(
                        `/api/projects/${projectId}`,
                        { title: title.trim() },
                        "PATCH",
                      );
                      await refresh();
                    });
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                }}
              />
              <div className="header-status">
                <span className="status-dot" />
                {busy ? "생성 중" : "저장됨"}
              </div>
              <span className="avatar small-avatar">나</span>
            </header>
            {basis && (
              <div className="workspace-source">
                <span><strong>{basis.name}</strong> · <code title={basis.commit_sha}>{basis.commit_sha}</code></span>
                <button className="secondary small" disabled={working} onClick={() => run(async () => {
                  const result = await api<{ commit_sha?: string; error?: string }>(`/api/sources/${basis.source_id}/analyze`, {});
                  setCheckedSource({ projectId: bundle.project.id, ...result });
                })}>최신 코드 확인</button>
                {comparison?.error && <span role="status">{comparison.error}</span>}
                {comparison?.commit_sha && (
                  comparison.commit_sha === basis.commit_sha ? <span role="status">현재 기준과 동일</span> :
                    <>
                      <span role="status">새 커밋 <code>{comparison.commit_sha}</code></span>
                      <button className="secondary small" onClick={() => navigate(null, bundle.project)}>새 코드 기준으로 분기</button>
                    </>
                )}
                {bundle.project.forked_from && <button className="text-button" onClick={() => navigate(bundle.project.forked_from)}>이전 기획 보기</button>}
              </div>
            )}
            <div
              className="workspace-tabs"
              role="tablist"
              aria-label="기획 산출물"
            >
              {visibleTabs.map(({ id, label, icon: Icon }) => (
                <button
                  role="tab"
                  aria-selected={tab === id}
                  key={id}
                  className={tab === id ? "active" : ""}
                  onClick={() => changeTab(id)}
                >
                  <Icon size={15} />
                  {label}
                  {hasArtifact(snapshot, id) && (
                    <span className="tab-ready" />
                  )}
                </button>
              ))}
              <div className="tab-spacer" />
              <div className="export-wrap">
                <button
                  className="secondary small"
                  disabled={viewIsCandidate || !visibleVersion || !!edit}
                  onClick={() => setExportMenu(!exportMenu)}
                  title={
                    viewIsCandidate
                      ? "확정본을 선택한 후 내보낼 수 있어요"
                      : "선택한 확정 버전 내보내기"
                  }
                >
                  <ArrowDownToLine size={14} />
                  <span>내보내기</span>
                  <ChevronDown size={12} />
                </button>
                {exportMenu && (
                  <div className="dropdown">
                    {basis && <small className="export-basis">{basis.name} · <code>{basis.commit_sha.slice(0, 12)}</code></small>}
                    <button onClick={() => exportFile("markdown")}>
                      <FileText size={15} />
                      Markdown (.md)
                    </button>
                    <button onClick={() => exportFile("json")}>
                      <FileText size={15} />
                      JSON (.json)
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="version-bar">
              <div className="snapshot-switch">
                <button
                  disabled={!!edit}
                  className={!viewIsCandidate ? "active" : ""}
                  onClick={() => {
                    historyRequest.current++;
                    setHistorical(null);
                    setCandidate(false);
                  }}
                >
                  확정본 v{bundle.project.current_version}
                </button>
                {bundle.proposal && (
                  <button
                    disabled={!!edit}
                    className={viewIsCandidate ? "active candidate" : ""}
                    onClick={() => openDraft()}
                  >
                    검토 중인 초안
                    <span />
                  </button>
                )}
                {isPast && (
                  <span className="history-badge">
                    과거 버전 v{historical.version} · 읽기 전용
                  </span>
                )}
              </div>
              <div className="version-actions">
                {edit ? (
                  <>
                    <span className="editing-state">
                      <span />
                      직접 편집 중
                    </span>
                    <button
                      className="text-button"
                      disabled={working}
                      onClick={() => setEdit(null)}
                    >
                      취소
                    </button>
                    <button
                      className="primary small"
                      disabled={working}
                      onClick={save}
                    >
                      <Check size={14} />
                      수정안 검토
                    </button>
                  </>
                ) : isPast ? (
                  <button
                    className="secondary small"
                    disabled={working || busy || !!bundle.proposal}
                    onClick={() =>
                      run(async () => {
                        await api(`/api/projects/${projectId}/proposals`, {
                          base_version: bundle.project.current_version,
                          snapshot: historical!.snapshot,
                          summary: `v${historical!.version} 복원 제안`,
                        });
                        setHistorical(null);
                        setPanel("review");
                        setSideOpen(true);
                        await refresh();
                      })
                    }
                  >
                    이 버전으로 복원 제안
                  </button>
                ) : (
                  <button
                    className="text-button"
                    disabled={working || busy || !hasAnyArtifact}
                    onClick={() => setEdit(structuredClone(snapshot))}
                  >
                    <Pencil size={13} />
                    직접 편집
                  </button>
                )}
              </div>
            </div>
            {!hasArtifact(snapshot, tab) ? (
              <div className="workspace-empty">
                <div className="empty-orbit">
                  <FileText size={32} />
                  <span>
                    <Sparkles size={15} />
                  </span>
                </div>
                {hasAnyArtifact || viewIsCandidate ? (
                  <>
                    <h1>이 탭에 표시할 산출물이 없어요.</h1>
                    <p>{hasAnyArtifact ? "내용이 있는 탭은 위에 점으로 표시돼요." : "검토 패널에서 생성 결과와 해결할 항목을 확인해 주세요."}</p>
                  </>
                ) : (
                  <>
                    <span className="eyebrow">YOUR NEXT PRODUCT STARTS HERE</span>
                    <h1>아이디어가 기획이 되는 공간.</h1>
                    <p>
                      왼쪽에서 기획 파트너와 방향을 맞추면
                      <br />
                      PRD부터 와이어프레임까지 이곳에 채워집니다.
                    </p>
                  </>
                )}
                <div className="output-path">
                  {visibleTabs.map(({ id, label, icon: Icon }, i) => (
                    <div key={id}>
                      <span>
                        <Icon size={18} />
                        {label}
                      </span>
                      {i < visibleTabs.length - 1 && <ChevronRight size={14} />}
                    </div>
                  ))}
                </div>
                {bundle.job &&
                  ["queued", "running"].includes(bundle.job.status) && (
                    <span className="subtle">
                      <LoaderCircle size={14} className="spin" /> 기획 파트너가
                      준비하고 있어요.
                    </span>
                  )}
                {bundle.proposal && (
                  <button
                    className="primary"
                    disabled={!!edit}
                    onClick={() => openDraft()}
                  >
                    생성된 초안 보기
                    <ArrowRight size={16} />
                  </button>
                )}
              </div>
            ) : (
              <div className="workspace-body">
                <div className="artifact-view">
                  {tab === "prd" ? (
                    <PrdDocument
                      snapshot={snapshot}
                      editing={!!edit}
                      update={update}
                      onSelect={(id) => {
                        select(id);
                        setPanel("chat");
                        setSideOpen(true);
                      }}
                    />
                  ) : tab === "features" ? (
                    <FeaturesView
                      snapshot={snapshot}
                      selected={selected}
                      onSelect={select}
                      editing={!!edit}
                      update={update}
                    />
                  ) : tab === "flow" ? (
                    <>
                      <div className="view-toolbar">
                        <span className="flow-toolbar-title">
                          <GitBranch size={16} />
                          사용자의 여정을 한눈에
                        </span>
                        <span className="toolbar-count">
                          노드 {snapshot.flow.nodes.length} · 연결{" "}
                          {snapshot.flow.edges.length}
                        </span>
                      </div>
                      <Canvas
                        key="flow"
                        snapshot={snapshot}
                        mode="flow"
                        selected={selected}
                        onSelect={select}
                        editing={!!edit}
                        update={update}
                      />
                    </>
                  ) : tab === "implementation" ? (
                    <div className="document-scroll">
                      <ImplementationDocument snapshot={snapshot} selected={selected} update={edit ? update : undefined} />
                    </div>
                  ) : (
                    <Wireframes
                      key={bundle.project.id}
                      snapshot={snapshot}
                      screenPreviews={bundle.screen_previews}
                      editing={!!edit}
                      update={update}
                      onSelectItem={select}
                      focusId={selected}
                      onFlow={() => changeTab("flow")}
                    />
                  )}
                </div>
                {selected && ["features", "flow"].includes(tab) && (
                  <Inspector
                    snapshot={snapshot}
                    selected={selected}
                    tab={tab}
                    editing={!!edit}
                    update={update}
                    onClose={() => setSelected(null)}
                    onAsk={() => {
                      setPanel("chat");
                      setSideOpen(true);
                    }}
                    onTab={changeTab}
                  />
                )}
              </div>
            )}
            <footer className="workspace-footer">
              <span>
                {health.auth_mode === "mock" ? "로컬 인증" : "Supabase 인증"}
                <i />{" "}
                {health.ai_mode === "mock"
                  ? "AI 데모 모드"
                  : health.model.replace("openai/", "")}
              </span>
              <span>
                <ShieldCheck size={12} />{" "}
                {edit
                  ? "수정 내용은 승인 후 확정됩니다"
                  : viewIsCandidate
                    ? "검토 중인 초안 · 아직 확정되지 않았어요"
                    : `확정본 v${visibleVersion}`}
              </span>
            </footer>
          </main>
        </div>
      )}
    </>
  );
}
