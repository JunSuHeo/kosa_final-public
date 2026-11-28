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
  Home as HomeIcon,
  Settings2,
  LayoutDashboard,
  LayoutTemplate,
  LoaderCircle,
  MessageSquare,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { api, ApiError, download } from "./api";
import type {
  Bundle,
  Job,
  Health,
  Panel,
  Project,
  Revision,
  Snapshot,
  BusinessSource as Source,
  PlanningIntent,
  Tab,
} from "./types";
import Chat, { busyStatuses } from "./Chat";
import Review from "./Review";
import Login from "./Login";
import AccountMenu from "./AccountMenu";
import { useWorkspaceWidth } from "./WorkspaceDivider";
import AdminNavigation from "./AdminNavigation";
import UserManagement from "./UserManagement";
import AssignmentSettings from "./AssignmentSettings";
import { useAuth } from "./accounts/useAuth";
import { Canvas, FeaturesView, Inspector, PrdDocument } from "./Documents";
import Wireframes from "./Wireframes";
import { ImplementationDocument } from "./Sources";
import BusinessHome, { Brand, Intake } from "./BusinessHome";
import SourceSettings from "./SourceSettings";
import { clearTabDrafts, readTabDraft, removeTabDraft, tabDraftKey, writeTabDraft } from "./drafts";
import "./journey.css";

type EditorDraft = {
  baseVersion: number;
  proposalId: string | null;
  candidate: boolean;
  snapshot: Snapshot;
};

const tabs: { id: Tab; label: string; icon: typeof FileText }[] = [
  { id: "prd", label: "기획 내용", icon: FileText },
  { id: "features", label: "기능 상세", icon: LayoutDashboard },
  { id: "flow", label: "업무 흐름", icon: GitBranch },
  { id: "wireframes", label: "화면 시안", icon: LayoutTemplate },
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
  { id: "chat", label: "업무 대화", icon: MessageSquare },
  { id: "review", label: "내용 확인", icon: GitCompareArrows },
  { id: "documents", label: "자료", icon: FolderOpen },
  { id: "versions", label: "기록", icon: History },
];
const projectFromURL = () =>
  new URLSearchParams(window.location.search).get("project");
const projectRoute = () => {
  const query = new URLSearchParams(window.location.search);
  const requestedTab = query.get("tab");
  const tab = requestedTab === "implementation"
    ? requestedTab
    : tabs.find(({ id }) => id === requestedTab)?.id;
  return { tab, review: query.get("review") === "1", confirmed: query.get("confirmed") === "1" };
};
const pageFromURL = () =>
  new URLSearchParams(window.location.search).get("view") || "home";
function Logo({ compact = false }: { compact?: boolean }) {
  return compact ? <HomeIcon size={23} /> : <Brand />;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const {
    identity,
    authed,
    ready: authReady,
    notice: authNotice,
    login,
    logout,
    allowed,
    recovering,
    unavailable,
    retry,
  } = useAuth(health?.auth_mode);
  const accountRef = useRef(identity?.account.id);
  accountRef.current = identity?.account.id;
  const [adminNavOpen, setAdminNavOpen] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [page, setPage] = useState(pageFromURL);
  const [mobileView, setMobileView] = useState<"chat" | "artifacts">(() => projectRoute().tab ? "artifacts" : "chat");
  const [projectId, setProjectId] = useState<string | null>(projectFromURL);
  const idRef = useRef(projectId);
  idRef.current = projectId;
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [tab, setTab] = useState<Tab>(() => projectRoute().tab ?? "prd");
  const [panel, setPanel] = useState<Panel>(() => projectRoute().review ? "review" : "chat");
  const [reviewVisit, setReviewVisit] = useState(0);
  const [sideOpen, setSideOpen] = useState(true);
  const workspaceWidth = useWorkspaceWidth();
  const [candidate, setCandidate] = useState(true);
  const [historical, setHistorical] = useState<Revision | null>(null);
  const historyRequest = useRef(0);
  const [edit, setEdit] = useState<Snapshot | null>(null);
  const editBasis = useRef<Omit<EditorDraft, "snapshot"> | null>(null);
  const restoredProject = useRef<string | null>(null);
  const enteredProject = useRef<string | null>(null);
  const [staleEdit, setStaleEdit] = useState(false);
  const [hasUnsent, setHasUnsent] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [exportMenu, setExportMenu] = useState(false);
  const [title, setTitle] = useState("");
  const proposalRef = useRef<string | null>(null);
  const generationRequest = useRef(0);
  const logoutRef = useRef(logout);
  logoutRef.current = logout;
  const handleError = useCallback((e: unknown) => {
    if (e instanceof DOMException && e.name === "AbortError") return;
    if (e instanceof ApiError && e.status === 401) {
      void logoutRef.current({ explicit: false });
      setProjects([]);
      setBundle(null);
    }
    setError(e instanceof Error ? e.message : "작업을 완료하지 못했습니다.");
  }, []);
  const run = async (fn: () => Promise<void>) => {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      await fn();
      return true;
    } catch (e) {
      handleError(e);
      return false;
    } finally {
      setWorking(false);
    }
  };
  useEffect(() => {
    const controller = new AbortController();
    api<Health>("/health", undefined, undefined, controller.signal)
      .then((h) => {
        setHealth(h);
      })
      .catch(handleError);
    return () => controller.abort();
  }, [handleError]);
  const refreshProjects = useCallback(async () => {
    const request = generationRequest.current;
    const data = await api<Project[]>("/api/projects");
    if (request === generationRequest.current) setProjects(data);
  }, []);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const id = idRef.current;
    if (!id) return;
    const request = ++generationRequest.current;
    const result = await api<Bundle>(`/api/projects/${id}`, undefined, undefined, signal);
    if (signal?.aborted || idRef.current !== id || request !== generationRequest.current) return;
    setBundle(result);
    setTitle(result.project.title);
    if (result.proposal?.id && result.proposal.id !== proposalRef.current) {
      setCandidate(!projectRoute().confirmed || proposalRef.current !== null);
      setHistorical(null);
      proposalRef.current = result.proposal.id;
    }
  }, []);
  useEffect(() => {
    if (authed && allowed("plans.read")) refreshProjects().catch(handleError);
    if (!authed) {
      generationRequest.current++;
      historyRequest.current++;
      setProjects([]);
      setBundle(null);
      setEdit(null);
      setHistorical(null);
      setSelected(null);
      setAdminNavOpen(false);
    }
  }, [
    authed,
    identity?.account.id,
    identity?.policy,
    refreshProjects,
    handleError,
  ]);
  useEffect(() => {
    setBundle(null);
    setHistorical(null);
    setEdit(null);
    setSelected(null);
    setCandidate(!projectRoute().confirmed);
    restoredProject.current = null;
    enteredProject.current = null;
    setStaleEdit(false);
    setHasUnsent(false);
    proposalRef.current = null;
    historyRequest.current++;
    if (projectId && authed && allowed("plans.read"))
      refresh().catch(handleError);
  }, [projectId, authed, identity?.account.id, refresh, handleError]);
  const editorKey = identity && projectId
    ? tabDraftKey(identity.account.id, "edit", projectId) : null;
  useEffect(() => {
    if (!bundle || bundle.project.id !== projectId || !editorKey || restoredProject.current === editorKey) return;
    restoredProject.current = editorKey;
    const saved = readTabDraft<EditorDraft | null>(editorKey, null);
    if (!saved?.snapshot?.prd || !Array.isArray(saved.snapshot.prd.sections)) return;
    if (saved.baseVersion !== bundle.project.current_version ||
        saved.proposalId !== (bundle.proposal?.id || null)) {
      setStaleEdit(true);
      return;
    }
    editBasis.current = saved;
    setCandidate(saved.candidate);
    setEdit(saved.snapshot);
  }, [bundle, editorKey, projectId]);
  useEffect(() => {
    if (!bundle || bundle.project.id !== projectId || !editorKey || enteredProject.current === editorKey) return;
    enteredProject.current = editorKey;
    const active = bundle.job && busyStatuses.includes(bundle.job.status);
    if (!projectRoute().confirmed && bundle.proposal && !active && bundle.job?.status !== "failed" && !readTabDraft(editorKey, null)) {
      setPanel("review");
      setSideOpen(true);
      setCandidate(true);
    }
  }, [bundle, editorKey, projectId]);
  useEffect(() => {
    if (!authed || !projectId || !allowed("plans.read")) return;
    void refresh().catch(handleError);
  }, [authed, projectId, identity?.policy, refresh, handleError]);
  const busy = !!bundle?.job && busyStatuses.includes(bundle.job.status);
  useEffect(() => {
    if (
      !projectId ||
      !authed ||
      !busy ||
      bundle?.job?.status === "awaiting_answers"
    )
      return;
    const controller = new AbortController();
    // Starting another refresh before this one settles would discard its response.
    async function poll() {
      try {
        await refresh(controller.signal);
      } catch (error) {
        if (!controller.signal.aborted) handleError(error);
      }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 1300);
    }
    let timer = window.setTimeout(poll, 1300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [projectId, authed, identity?.account.id, busy, bundle?.job?.id, bundle?.job?.status, refresh, handleError]);
  useEffect(() => {
    const back = () => {
      idRef.current = projectFromURL();
      setProjectId(projectFromURL());
      setPage(pageFromURL());
      const route = projectRoute();
      setTab(route.tab ?? "prd");
      setPanel(route.review ? "review" : "chat");
      setMobileView(route.tab ? "artifacts" : "chat");
      if (!edit) {
        setCandidate(!route.confirmed);
        setHistorical(null);
      }
      setSelected(null);
      setExportMenu(false);
      setSideOpen(true);
    };
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, [edit]);
  const navigate = (id: string | null, origin?: Project, confirmed = false, replace = false) => {
    const source = origin?.source_id;
    window.history[replace ? "replaceState" : "pushState"](
      {},
      "",
      id
        ? `/?project=${id}${confirmed ? "&confirmed=1&tab=prd" : ""}`
        : source
          ? `/?source=${source}&from=${origin.id}`
          : "/",
    );
    idRef.current = id;
    setProjectId(id);
    setPage("home");
    setMobileView(confirmed ? "artifacts" : "chat");
    setTab("prd");
    setPanel("chat");
    setSideOpen(true);
    setError("");
    if (!id) refreshProjects().catch(handleError);
  };
  const openPage = (next: string, source?: Source, intent?: PlanningIntent) => {
    window.history.pushState(
      {},
      "",
      next === "home"
        ? "/"
        : `/?view=${next}${source ? `&source=${source.id}&intent=${intent || "improve"}` : ""}`,
    );
    idRef.current = null;
    setProjectId(null);
    setPage(next);
    setError("");
    if (next === "home") refreshProjects().catch(handleError);
  };
  useEffect(() => {
    if (!authed || !health) return;
    const needed =
      page === "accounts"
        ? "accounts.manage"
        : page === "permissions"
          ? "roles.manage"
          : page === "audit"
            ? "audit.read"
            : page === "assignments"
              ? "sources.assign"
              : page === "settings"
                ? "sources.manage"
                : page === "intake"
                  ? "plans.create"
                  : projectId
                    ? "plans.read"
                    : null;
    if (needed && !allowed(needed)) {
      window.history.replaceState({}, "", "/");
      idRef.current = null;
      setProjectId(null);
      setPage("home");
      setBundle(null);
      setEdit(null);
      setError("이 화면을 사용할 권한이 없어 업무 홈으로 이동했습니다.");
    }
  }, [authed, health, page, projectId, identity]);
  const create = async (idea: string, source: Source, intent: PlanningIntent) =>
    !!(await run(async () => {
      const owner = identity!.account.id;
      const key = tabDraftKey(owner, "intake", source.id);
      const payload = {
        idea,
        source_id: source.id,
        code_snapshot_id: source.published_snapshot_id,
        source_publication_id: source.publication_id,
        start_mode: "conversation",
        planning_intent: intent,
      };
      const draft = readTabDraft<{ text: string; intent: PlanningIntent; operation?: { id: string; payload: typeof payload } }>(key, { text: idea, intent });
      const operation = draft.operation && JSON.stringify(draft.operation.payload) === JSON.stringify(payload)
        ? draft.operation : { id: crypto.randomUUID(), payload };
      writeTabDraft(key, { ...draft, operation });
      const p = await api<Project>("/api/projects", { id: operation.id, ...operation.payload });
      // POST success is authoritative; list refresh must not turn it into a retry.
      if (accountRef.current !== owner) return;
      await refreshProjects().catch(handleError);
      const current = new URLSearchParams(location.search);
      if (accountRef.current === owner && !idRef.current && current.get("view") === "intake" && current.get("source") === source.id)
        navigate(p.id, undefined, false, true);
    }));
  const update = (fn: (s: Snapshot) => void) =>
    setEdit((previous) => {
      if (!previous) return previous;
      const next = structuredClone(previous);
      fn(next);
      if (editorKey && editBasis.current)
        writeTabDraft(editorKey, { ...editBasis.current, snapshot: next });
      return next;
    });
  const setArtifactRoute = (next: Tab | null, review: boolean, confirmed = false, replace = false) => {
    if (!projectId) return;
    const url = new URL(window.location.href);
    if (next) url.searchParams.set("tab", next);
    else url.searchParams.delete("tab");
    if (review) url.searchParams.set("review", "1");
    else url.searchParams.delete("review");
    if (confirmed) url.searchParams.set("confirmed", "1");
    else url.searchParams.delete("confirmed");
    if (url.href !== window.location.href) {
      window.history[replace ? "replaceState" : "pushState"]({}, "", url);
    }
  };
  const changeTab = (next: Tab, confirmed = !candidate) => {
    setArtifactRoute(next, panel === "review", confirmed);
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
  const visibleTabs = tabs;
  const isPast =
    !!historical && historical.version !== bundle?.project.current_version;
  const visibleVersion =
    historical?.version ?? bundle?.project.current_version ?? 0;
  const viewIsCandidate = !!bundle?.proposal && candidate && !historical;
  const hasAnyArtifact =
    snapshot && visibleTabs.some(({ id }) => hasArtifact(snapshot, id));
  const persistedArtifact = [bundle?.proposal?.candidate, bundle?.revision.snapshot]
    .some((value) => value && visibleTabs.some(({ id }) => hasArtifact(value, id)));
  const conversationStage = !persistedArtifact && !edit;
  const confirmedWithPending = !!bundle?.proposal && !viewIsCandidate;
  const availablePanels = conversationStage ? panels.filter(item => item.id === "chat") : panels;
  const startEditing = () => {
    if (!snapshot || !bundle || !editorKey || confirmedWithPending) return;
    editBasis.current = {
      baseVersion: bundle.project.current_version,
      proposalId: bundle.proposal?.id || null,
      candidate: viewIsCandidate,
    };
    const draft = structuredClone(snapshot);
    writeTabDraft(editorKey, { ...editBasis.current, snapshot: draft });
    setStaleEdit(false);
    setEdit(draft);
  };
  const discardEdit = () => {
    if (editorKey) removeTabDraft(editorKey);
    editBasis.current = null;
    setEdit(null);
    setStaleEdit(false);
  };
  const showReviewGuide = () => {
    setReviewVisit((value) => value + 1);
    setPanel("review");
    setSideOpen(true);
    setMobileView("chat");
  };
  const openReview = () => {
    if (edit) return;
    historyRequest.current++;
    setHistorical(null);
    setCandidate(!!bundle?.proposal);
    setSelected(null);
    setArtifactRoute(null, true, false, panel !== "review");
    setTab("prd");
    showReviewGuide();
  };
  const openDraft = () => {
    const draft = bundle?.proposal?.candidate;
    if (!draft || edit) return;
    historyRequest.current++;
    setHistorical(null);
    setCandidate(true);
    const firstAvailable = visibleTabs.find(({ id }) => hasArtifact(draft, id));
    if (!hasArtifact(draft, tab) && firstAvailable)
      changeTab(firstAvailable.id, false);
    else if (projectRoute().tab) setArtifactRoute(tab, panel === "review");
    if (!firstAvailable) openReview();
  };
  const viewReviewDocument = (next: Tab, id?: string) => {
    if (edit) return;
    historyRequest.current++;
    setHistorical(null);
    setCandidate(!!bundle?.proposal);
    setArtifactRoute(next, true);
    setTab(next);
    setSelected(id || null);
    setMobileView("artifacts");
  };
  const discussReviewItem = (id?: string) => {
    if (edit || busy || working) return;
    historyRequest.current++;
    setHistorical(null);
    setCandidate(!!bundle?.proposal);
    setSelected(id || null);
    setPanel("chat");
    setSideOpen(true);
    setMobileView("chat");
  };
  const select = (id: string) => {
    setSelected(id || null);
  };
  useEffect(() => {
    if (
      basis?.source_id &&
      bundle?.source_access?.can_manage &&
      allowed("sources.manage")
    )
      void api(`/api/sources/${basis.source_id}/check`, {}).catch(handleError);
  }, [
    basis?.source_id,
    bundle?.source_access?.can_manage,
    identity?.policy,
    handleError,
  ]);
  useEffect(() => {
    if (
      panel === "review" &&
      ["prd", "features", "implementation"].includes(tab) &&
      selected
    ) {
      document
        .getElementById(selected)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [panel, tab, selected, snapshot, mobileView]);
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
  const submitAnswers = async (answers: Record<string, string>) =>
    !!(await run(async () => {
      if (!bundle?.job) return;
      const owner = identity!.account.id;
      const id = projectId;
      const accepted = await api<Job>(`/api/projects/${projectId}/jobs/${bundle.job.id}/answers`, {
        base_version: bundle.job.base_version,
        answers,
      });
      if (accountRef.current === owner && idRef.current === id) {
        setBundle((previous) => previous && previous.project.id === id ? { ...previous, job: accepted } : previous);
        await refresh().catch(handleError);
      }
    }));
  const send = async (request: string) =>
    !!(await run(async () => {
      if (!bundle || !projectId || !identity) return;
      const owner = identity.account.id;
      const id = projectId;
      const key = tabDraftKey(`${owner}:${id}`, "request", "discuss");
      const payload = {
        base_version: bundle.project.current_version,
        kind: "discuss",
        request,
        target_id: selectedItem?.id || null,
        base_proposal_id: bundle.proposal?.id || null,
      };
      const previous = readTabDraft<{ id: string; payload: typeof payload } | null>(key, null);
      const operation = previous && JSON.stringify(previous.payload) === JSON.stringify(payload)
        ? previous : { id: crypto.randomUUID(), payload };
      writeTabDraft(key, operation);
      const accepted = await api<Job>(`/api/projects/${id}/jobs`, { id: operation.id, ...operation.payload });
      removeTabDraft(key);
      if (accountRef.current === owner && idRef.current === id) {
        setBundle((previous) => previous && previous.project.id === id ? { ...previous, job: accepted } : previous);
        await refresh().catch(handleError);
      }
    }));
  const blockUnsentInput = () => {
    const pending = identity && projectId && readTabDraft(
      tabDraftKey(`${identity.account.id}:${projectId}`, "chat", "input"), "",
    ).trim();
    const questions = bundle?.job?.partial.discussion as { questions?: { key: string }[] } | undefined;
    const pendingQuestion = identity && projectId && questions?.questions?.some((question) => {
      const saved = readTabDraft<{ choice: string | null; custom: string; sent: boolean } | null>(
        tabDraftKey(`${identity.account.id}:${projectId}`, "dialogue", `${bundle!.job!.id}:${question.key}`), null,
      );
      return saved && !saved.sent && !!(saved.choice || saved.custom.trim());
    });
    if (hasUnsent || pending || pendingQuestion) {
      setError("입력한 내용을 먼저 보내 주세요.");
      setPanel("chat");
      setSideOpen(true);
      setMobileView("chat");
      return true;
    }
    return false;
  };
  const writeDraft = (repair = false) => {
    if (blockUnsentInput()) return Promise.resolve(false);
    return run(async () => {
      if (!bundle || !identity || !projectId) return;
      const owner = identity.account.id;
      const id = projectId;
      const key = tabDraftKey(`${owner}:${id}`, "request", repair ? "repair" : "generate");
      const hasDraft = !!bundle.proposal || bundle.project.current_version > 0;
      const request = repair
        ? "지적된 연결 오류만 정리해 주세요."
        : bundle.messages.filter((message) => message.role === "user").at(-1)
            ?.content || bundle.project.idea;
      const payload = {
        base_version: bundle.project.current_version,
        kind: repair ? "repair" : hasDraft ? "revise" : "generate",
        request,
        target_id: repair ? null : selectedItem?.id || null,
        base_proposal_id: bundle.proposal?.id || null,
      };
      const previous = readTabDraft<{ id: string; payload: typeof payload } | null>(key, null);
      const operation = previous && JSON.stringify(previous.payload) === JSON.stringify(payload)
        ? previous : { id: crypto.randomUUID(), payload };
      writeTabDraft(key, operation);
      const accepted = await api<Job>(`/api/projects/${id}/jobs`, { id: operation.id, ...operation.payload });
      removeTabDraft(key);
      if (accountRef.current !== owner || idRef.current !== id) return;
      setBundle((previous) => previous && previous.project.id === id ? { ...previous, job: accepted } : previous);
      setPanel("chat");
      setSideOpen(true);
      await refresh().catch(handleError);
    });
  };
  const retryJob = () => {
    if (blockUnsentInput()) return Promise.resolve(false);
    return run(async () => {
      if (!bundle?.job || !identity || !projectId) return;
      const owner = identity.account.id;
      const id = projectId;
      const job = bundle.job;
      const key = tabDraftKey(`${owner}:${id}`, "request", `retry:${job.id}`);
      const payload = {
        base_version: bundle.project.current_version,
        kind: job.kind,
        base_proposal_id: job.base_proposal_id || null,
        target_id: (job.partial.target_id as string | null) || null,
        request: job.request || bundle.project.idea,
      };
      const previous = readTabDraft<{ id: string; payload: typeof payload } | null>(key, null);
      const operation = previous && JSON.stringify(previous.payload) === JSON.stringify(payload)
        ? previous : { id: crypto.randomUUID(), payload };
      writeTabDraft(key, operation);
      const accepted = await api<Job>(`/api/projects/${id}/jobs`, { id: operation.id, ...operation.payload });
      removeTabDraft(key);
      if (accountRef.current !== owner || idRef.current !== id) return;
      setBundle((previous) => previous && previous.project.id === id ? { ...previous, job: accepted } : previous);
      await refresh().catch(handleError);
    });
  };
  const decide = (decision: "approve" | "reject", ack: boolean) =>
    run(async () => {
      if (!bundle?.proposal || !identity) return;
      const owner = identity.account.id;
      const id = projectId;
      await api(
        `/api/projects/${projectId}/proposals/${bundle.proposal.id}/${decision}`,
        {
          expected_version: bundle.project.current_version,
          acknowledge_warnings: ack,
        },
      );
      if (accountRef.current !== owner || idRef.current !== id) return;
      setCandidate(false);
      setHistorical(null);
      setEdit(null);
      setSelected(null);
      await refresh();
      await refreshProjects();
    });
  const save = () =>
    run(async () => {
      if (!edit || !bundle || !editorKey || !identity) return;
      const owner = identity.account.id;
      const id = projectId;
      const savedEditorKey = editorKey;
      if (editBasis.current?.baseVersion !== bundle.project.current_version ||
          editBasis.current?.proposalId !== (bundle.proposal?.id || null)) {
        setStaleEdit(true);
        setEdit(null);
        return;
      }
      await api(`/api/projects/${projectId}/proposals`, {
        base_version: editBasis.current.baseVersion,
        snapshot: edit,
        base_proposal_id: editBasis.current?.proposalId || null,
        summary: "문서와 화면 직접 편집",
      });
      removeTabDraft(savedEditorKey);
      if (accountRef.current !== owner || idRef.current !== id) return;
      editBasis.current = null;
      setEdit(null);
      setStaleEdit(false);
      setSelected(null);
      setTab("prd");
      showReviewGuide();
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
  if (!health || !authReady)
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
    if (unavailable)
      return (
        <main className="boot-screen" aria-busy={recovering}>
          <Logo />
          <p role="alert">{authNotice || "로그인 상태를 확인하지 못했습니다. 다시 연결해 주세요."}</p>
          <button className="primary" disabled={recovering} onClick={() => void retry()}>
            {recovering ? "연결 확인 중…" : "다시 연결"}
          </button>
        </main>
      );
  if (!authed)
    return (
      <Login
        notice={error || authNotice}
        onLogin={async (identifier, password) => {
          setError("");
          await login(identifier, password);
        }}
      />
    );
  const accountMenu = (
    <AccountMenu
      name={identity?.account.loginId || "내 계정"}
      displayName={identity?.account.name}
      role={identity?.account.role}
      onLogout={() => {
        clearTabDrafts();
        void logout().then(() => window.location.replace("/"));
      }}
    />
  );
  const navigation =
    allowed("accounts.manage") ? (
      <button
        className="admin-navigation-toggle"
        aria-label="관리자 메뉴 열기"
        aria-expanded={adminNavOpen}
        onClick={() => setAdminNavOpen(true)}
      >
        <Menu size={22} />
      </button>
    ) : null;
  const editable =
    allowed("plans.edit") && bundle?.source_access?.can_use !== false;
  return (
    <>
      {authed && unavailable && (
        <div className="connection-notice" role="status">
          <span>{authNotice || "연결을 확인하고 있습니다. 작성 중인 내용은 유지됩니다."}</span>
          <button disabled={recovering} onClick={() => void retry()}>
            {recovering ? "연결 확인 중…" : "다시 연결"}
          </button>
        </div>
      )}
      {adminNavOpen && navigation && (
        <AdminNavigation
          page={page}
          onClose={() => setAdminNavOpen(false)}
          onNavigate={(next) => {
            setAdminNavOpen(false);
            openPage(next);
          }}
        />
      )}
      {error && (
        <div className="error-toast" role="alert">
          <span>{error}</span>
          <button aria-label="오류 알림 닫기" onClick={() => setError("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {!projectId ? (
        ["accounts", "permissions", "audit"].includes(page) &&
        identity &&
        allowed("accounts.manage") ? (
          <UserManagement
            page={page}
            identity={identity}
            navigation={navigation}
            accountMenu={accountMenu}
            onHome={() => openPage("home")}
            onError={handleError}
          />
        ) : page === "assignments" && allowed("sources.assign") ? (
          <AssignmentSettings
            navigation={navigation}
            accountMenu={accountMenu}
            onHome={() => openPage("home")}
            onError={handleError}
          />
        ) : page === "settings" && allowed("sources.manage") ? (
          <SourceSettings
            onAssignments={
              allowed("sources.assign")
                ? () => openPage("assignments")
                : undefined
            }
            navigation={navigation}
            accountMenu={accountMenu}
            onHome={() => openPage("home")}
            onError={handleError}
          />
        ) : page === "intake" && allowed("plans.create") ? (
          <Intake
            draftOwner={identity!.account.id}
            navigation={navigation}
            accountMenu={accountMenu}
            health={health}
            onHome={() => openPage("home")}
            onCreate={create}
            onError={handleError}
            working={working}
          />
        ) : (
          <BusinessHome
            navigation={navigation}
            accountMenu={accountMenu}
            canCreate={allowed("plans.create")}
            canManage={allowed("sources.manage")}
            canAssign={allowed("sources.assign")}
            canRead={allowed("plans.read")}
            projects={projects}
            health={health}
            onOpen={(id, confirmed) => navigate(id, undefined, confirmed)}
            onStart={(source, intent) => openPage("intake", source, intent)}
            onSettings={() =>
              openPage(allowed("sources.manage") ? "settings" : "assignments")
            }
            onError={handleError}
          />
        )
      ) : !bundle || !snapshot ? (
        <div className="boot-screen">
          <Logo />
          <LoaderCircle className="spin" />
          <button className="secondary" onClick={() => navigate(null)}>
            프로젝트 목록
          </button>
        </div>
      ) : (
        <div
          className="studio"
          data-stage={conversationStage ? "conversation" : "documents"}
          data-mobile-view={mobileView}
          data-wire-review={panel === "review" && tab === "wireframes" && !edit && !isPast}
          data-resizing={workspaceWidth.resizing}
          style={workspaceWidth.style}
        >
          <div className="mobile-switch">
            {navigation}
            <button aria-label="업무 선택" onClick={() => navigate(null)}>
              <HomeIcon size={20} />
            </button>
            <strong>{title}</strong>
            <button
              className={mobileView === "chat" ? "active" : ""}
              onClick={() => {
                setMobileView("chat");
                setSideOpen(true);
              }}
            >
              대화
            </button>
            <button
              className={mobileView === "artifacts" ? "active" : ""}
              onClick={() => setMobileView("artifacts")}
            >
              산출물
            </button>
            <select
              aria-label="기획 도구"
              value={panel}
              onChange={(e) => {
                if (e.target.value === "review") openReview();
                else {
                  setPanel(e.target.value as Panel);
                  setSideOpen(true);
                  setMobileView("chat");
                }
              }}
            >
              {availablePanels.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            {accountMenu}
          </div>
          <nav className="rail" aria-label="작업 도구">
            {navigation}
            <button
              className="rail-logo"
              aria-label="프로젝트 목록"
              onClick={() => navigate(null)}
            >
              <Logo compact />
            </button>
            <div className="rail-items">
              {availablePanels.map(({ id, label, icon: Icon }) => (
                <button
                  className={panel === id && sideOpen ? "active" : ""}
                  key={id}
                  onClick={() => {
                    if (id === "review") openReview();
                    else {
                      setPanel(id);
                      setSideOpen(panel !== id || !sideOpen);
                    }
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
                title="로그인됨"
              >
                나
              </div>
            </div>
          </nav>
          {sideOpen && (
            <aside className="side-panel">
              {bundle.source_access?.can_use === false && (
                <p className="access-notice">
                  업무 배정이 해제되어 새 대화와 생성을 진행할 수 없습니다. 기존
                  문서 조회와 확인본 내보내기는 가능합니다.
                </p>
              )}
              {!allowed("plans.edit") && (
                <p className="access-notice">
                  기획 수정 권한이 없습니다. 관리자에게 문의해 주세요.
                </p>
              )}
              {panel === "chat" ? (
                <Chat
                  key={bundle.project.id}
                  bundle={bundle}
                  onGenerate={() => void writeDraft()}
                  disabled={!!edit || isPast || !editable}
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
                  onReview={openReview}
                  onRetry={() => void retryJob()}
                  working={working}
                  draftScope={`${identity!.account.id}:${bundle.project.id}`}
                  onUnsentChange={setHasUnsent}
                />
              ) : panel === "review" ? (
                <Review
                  visit={reviewVisit}
                  proposal={bundle.proposal}
                  confirmed={bundle.revision.snapshot}
                  currentVersion={bundle.project.current_version}
                  onView={viewReviewDocument}
                  onDiscuss={discussReviewItem}
                  onRepair={() => void writeDraft(true)}
                  busy={busy}
                  projectId={bundle.project.id}
                  proposalId={viewIsCandidate ? bundle.proposal!.id : null}
                  version={
                    viewIsCandidate
                      ? bundle.proposal!.base_version
                      : visibleVersion
                  }
                  disabled={!!edit}
                  canEdit={editable}
                  canConfirm={allowed("plans.confirm")}
                  onLocate={(id) => {
                    const current =
                      bundle.proposal?.candidate || bundle.revision.snapshot;
                    const next: Tab = current.prd.sections.some(
                      (x) => x.id === id,
                    )
                      ? "prd"
                      : [...current.features, ...current.requirements].some(
                            (x) => x.id === id,
                          )
                        ? "features"
                        : current.screens.some(
                              (x) =>
                                x.id === id ||
                                x.blocks.some((b) => b.id === id),
                            )
                          ? "wireframes"
                          : id === "source-implementation" ||
                              current.source_context?.evidence.some(
                                (x) => x.id === id,
                              ) ||
                              current.implementation?.tasks.some(
                                (x) => x.id === id,
                              ) ||
                              current.implementation?.acceptance.some(
                                (x) => x.id === id,
                              )
                            ? "implementation"
                            : "flow";
                    viewReviewDocument(next, id);
                  }}
                  onDecide={decide}
                  working={working}
                />
              ) : panel === "versions" ? (
                <>
                  <div className="panel-heading">
                    <div>
                      <History size={17} />
                      <strong>확인본 기록</strong>
                    </div>
                    <span className="count-pill">
                      {bundle.revisions.length}
                    </span>
                  </div>
                  <div className="versions-list">
                    <p>내용을 확인해 저장한 기획은 버전마다 보관됩니다.</p>

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
                            <span className="version-tag">현재 확인본</span>
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
                      <strong>기획 자료</strong>
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
                    {basis && (
                      <button onClick={() => changeTab("implementation")}>
                        <Settings2 size={16} /> IT 전달자료
                      </button>
                    )}
                    <button onClick={() => openPage("settings")}>
                      <Settings2 size={16} /> 업무 연결 설정
                    </button>
                    <div className="eyebrow">기획 내용</div>
                    {snapshot.prd.sections.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => {
                          setTab("prd");
                          setSelected(s.id);
                          setTimeout(
                            () =>
                              document.getElementById(s.id)?.scrollIntoView({
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
          {sideOpen && workspaceWidth.divider}
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
                {edit ? "직접 편집 미저장" : hasUnsent ? "미전송 입력 임시 보관" :
                  bundle.job?.status === "awaiting_answers" ? "답변 대기" :
                  busy ? "기획 정리 중" : working ? "저장 중…" : "전송한 대화 저장됨"}
              </div>
              {accountMenu}
            </header>
            {basis && (
              <div className="workspace-source">
                <span>
                  <FolderOpen size={14} /> <strong>{basis.name}</strong>의
                  업무를 기획하고 있어요.
                </span>
              </div>
            )}
            {staleEdit && (
              <div className="draft-conflict" role="alert">
                <p>다른 기준 버전에서 작성한 임시 편집이 있습니다. 현재 문서에는 자동 적용하지 않았습니다.</p>
                <button className="secondary" onClick={discardEdit}>임시 편집 버리기</button>
              </div>
            )}
            <div className="journey-stage" role="status">
              {conversationStage ? "1 업무 대화 · 내용을 정리한 뒤 기획 초안을 만듭니다" :
                viewIsCandidate ? "2 초안 확인 · 업무와 맞는지 살펴보고 확인본으로 저장하세요" :
                  "3 현업 확인본 · 내려받거나 새 수정안을 만들 수 있습니다"}
            </div>
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
                  {hasArtifact(snapshot, id) && <span className="tab-ready" />}
                </button>
              ))}
              <div className="tab-spacer" />
              <div className="export-wrap">
                <button
                  className="secondary small"
                  disabled={
                    working ||
                    viewIsCandidate ||
                    !visibleVersion ||
                    !!edit ||
                    !allowed("plans.export")
                  }
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
                    {basis && (
                      <small className="export-basis">
                        {basis.name} · 현업 확인본 v{visibleVersion}
                      </small>
                    )}
                    <button onClick={() => exportFile("markdown")}>
                      <FileText size={15} />
                      문서 파일 (.md)
                    </button>
                    <button onClick={() => exportFile("json")}>
                      <FileText size={15} />
                      기획 데이터 (.json)
                    </button>
                  </div>
                )}
              </div>
            </div>
            {viewIsCandidate && (
              <div className="export-guide">
                <span>초안을 확인본으로 저장하면 내려받을 수 있어요.</span>
                <button className="text-button" onClick={openReview}>초안 내용 확인</button>
                {!!bundle.project.current_version && (
                  <button className="text-button" disabled={working || !allowed("plans.export")}
                    onClick={() => run(() => download(`/api/projects/${projectId}/revisions/${bundle.project.current_version}/export?format=markdown`))}>
                    확인본 v{bundle.project.current_version} 내려받기
                  </button>
                )}
              </div>
            )}
            {panel === "review" && (
              <div className="review-document-bar">
                <span>
                  {viewIsCandidate
                    ? "작성 중인 초안을 확인하고 있어요"
                    : isPast
                      ? "과거 확인본을 보고 있어요"
                      : visibleVersion
                        ? `현업 확인본 v${visibleVersion} · 읽기 전용`
                        : "아직 확인할 문서가 없어요"}
                </span>
                {selectedItem && !isPast && (
                  <button
                    className="text-button"
                    disabled={busy || working || !!edit || !editable}
                    onClick={() => discussReviewItem(selectedItem.id)}
                  >
                    이 내용 수정하기
                  </button>
                )}
                <button className="text-button" onClick={openReview}>
                  <span className="review-return-desktop">확인 안내로 돌아가기</span>
                  <span className="review-return-mobile">검토로 돌아가기</span>
                </button>
              </div>
            )}
            <div className="version-bar">
              <div className="snapshot-switch">
                <button
                  disabled={!!edit}
                  className={!viewIsCandidate ? "active" : ""}
                  onClick={() => {
                    historyRequest.current++;
                    setHistorical(null);
                    setCandidate(false);
                    if (projectRoute().tab) setArtifactRoute(tab, panel === "review", true);
                  }}
                >
                  {bundle.project.current_version
                    ? `현업 확인본 v${bundle.project.current_version}`
                    : "아직 확인본이 없어요"}
                </button>
                {bundle.proposal && (
                  <button
                    disabled={!!edit}
                    className={viewIsCandidate ? "active candidate" : ""}
                    onClick={() => openDraft()}
                  >
                    작성 중인 초안
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
                      onClick={discardEdit}
                    >
                      취소
                    </button>
                    <button
                      className="primary small"
                      disabled={working}
                      onClick={save}
                    >
                      <Check size={14} />
                      수정 내용 확인
                    </button>
                  </>
                ) : isPast ? (
                  <button
                    className="secondary small"
                    disabled={working || busy || !!bundle.proposal || !editable}
                    onClick={() =>
                      run(async () => {
                        await api(`/api/projects/${projectId}/proposals`, {
                          base_version: bundle.project.current_version,
                          snapshot: historical!.snapshot,
                          summary: `v${historical!.version} 복원 제안`,
                        });
                        openReview();
                        await refresh();
                      })
                    }
                  >
                    이 버전으로 복원 제안
                  </button>
                ) : (
                  <button
                    className="text-button"
                    disabled={working || busy || !hasAnyArtifact || !editable || staleEdit || confirmedWithPending}
                    onClick={startEditing}
                  >
                    <Pencil size={13} />
                    직접 편집
                  </button>
                )}
              </div>
            </div>
            {confirmedWithPending && !edit && <p className="journey-stage">작성 중인 초안을 선택한 뒤 편집해 주세요.</p>}
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
                    <p>
                      {hasAnyArtifact
                        ? "내용이 있는 탭은 위에 점으로 표시돼요."
                        : "검토 패널에서 생성 결과와 해결할 항목을 확인해 주세요."}
                    </p>
                  </>
                ) : (
                  <>
                    <span className="eyebrow">업무 정리</span>
                    <h1>업무를 정리하면 기획이 시작됩니다.</h1>
                    <p>
                      대화로 현재 업무와 바꾸고 싶은 내용을 정리한 뒤<br />
                      ‘기획 초안 만들기’를 눌러 주세요.
                    </p>
                    {bundle.project.conversation_brief && (
                      <div className="brief-summary">
                        <h3>지금까지 정리한 내용</h3>
                        <dl>
                          <dt>현재 업무</dt>
                          <dd>
                            {bundle.project.conversation_brief.current_work ||
                              "확인 중"}
                          </dd>
                          <dt>불편한 점</dt>
                          <dd>
                            {bundle.project.conversation_brief.problem ||
                              "확인 중"}
                          </dd>
                          <dt>원하는 변화</dt>
                          <dd>
                            {bundle.project.conversation_brief.desired_change ||
                              "확인 중"}
                          </dd>
                        </dl>
                      </div>
                    )}
                    {bundle.project.conversation_brief && (
                      <button
                        className="primary"
                        disabled={busy || working || hasUnsent}
                        onClick={() => void writeDraft()}
                      >
                        기획 초안 만들기 <ArrowRight size={16} />
                      </button>
                    )}
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
                      selected={selected}
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
                          업무 처리 순서를 한눈에
                        </span>
                        <span className="toolbar-count">
                          업무 단계 {snapshot.flow.nodes.length} · 흐름{" "}
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
                      <ImplementationDocument
                        snapshot={snapshot}
                        selected={selected}
                        update={edit ? update : undefined}
                      />
                    </div>
                  ) : (
                    <Wireframes
                      key={bundle.project.id}
                      snapshot={snapshot}
                      screenPreviews={bundle.screen_previews}
                      editing={!!edit}
                      update={update}
                      onSelectItem={(id) => {
                        select(id);
                        setPanel("chat");
                        setSideOpen(true);
                      }}
                      previousSnapshot={bundle.revision.snapshot}
                      changedBlockIds={bundle.changed_block_ids}
                      focusId={selected}
                      onFlow={() => changeTab("flow")}
                    />
                  )}
                </div>
                {selected &&
                  panel !== "review" &&
                  ["features", "flow"].includes(tab) && (
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
                  ? "수정 내용을 확인한 뒤 확인본으로 저장해 주세요"
                  : viewIsCandidate
                    ? "작성 중인 초안 · 아직 확인본으로 저장하지 않았어요"
                    : visibleVersion
                      ? `현업 확인본 v${visibleVersion}`
                      : "업무를 정리하고 있어요"}
              </span>
            </footer>
          </main>
        </div>
      )}
    </>
  );
}
