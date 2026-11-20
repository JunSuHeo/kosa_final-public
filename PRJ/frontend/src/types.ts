export type Section = {
  id: string;
  group: string;
  title: string;
  content: string;
};
export type Requirement = {
  id: string;
  title: string;
  description: string;
  priority: "P0" | "P1" | "P2";
  acceptance: string[];
};
export type Feature = {
  id: string;
  requirement_id: string;
  title: string;
  description: string;
  actor: string;
  preconditions: string[];
  steps: string[];
  exceptions: string[];
  acceptance: string[];
};
export type FlowNode = {
  id: string;
  type: "start" | "screen" | "decision" | "action" | "end";
  title: string;
  section: string;
  feature_ids: string[];
  x: number;
  y: number;
};
export type FlowEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};
export type BlockType =
  | "heading"
  | "text"
  | "input"
  | "button"
  | "card"
  | "list"
  | "stat"
  | "navigation"
  | "table";
export type Block = {
  id: string;
  type: BlockType;
  label: string;
  content: string;
  target_screen_id: string | null;
  region?: "content" | "header" | "navigation" | "filters" | "actions";
  columns?: string[];
  rows?: string[][];
};
export type Screen = {
  id: string;
  node_id: string;
  title: string;
  device: "mobile" | "desktop";
  blocks: Block[];
  layout?: "form" | "list" | "detail" | "dashboard";
};
export type DesignProfile = {
  primary: string;
  background: string;
  surface: string;
  text: string;
  font: "system" | "sans" | "serif" | "mono";
  spacing: number;
  radius: number;
  shell: "header" | "sidebar" | "plain";
  evidence: string[];
};
export type ConversationBrief = {
  current_work: string;
  problem: string;
  desired_change: string;
  actors: string[];
  rules: string[];
  exceptions: string[];
  confirmed_facts: string[];
  user_statements: string[];
  open_questions: string[];
};
export type PlanningIntent = "new_feature" | "improve" | "process";
export type Snapshot = {
  prd: {
    title: string;
    sections: Section[];
    roles: string[];
    platforms: string[];
    assumptions: string[];
  };
  requirements: Requirement[];
  features: Feature[];
  flow: { nodes: FlowNode[]; edges: FlowEdge[] };
  screens: Screen[];
  source_context?: SourceContext;
  implementation?: Implementation;
  design_profile?: DesignProfile;
};
export type Project = {
  id: string;
  source_id: string | null;
  code_snapshot_id: string | null;
  forked_from: string | null;
  title: string;
  idea: string;
  current_version: number;
  created_at: string;
  updated_at: string;
  start_mode?: "generate" | "conversation";
  planning_intent?: PlanningIntent;
  conversation_brief?: ConversationBrief | null;
  source_publication_id?: string | null;
};
export type Question = { key: string; title: string; options: string[] };
export type Job = {
  id: string;
  code_snapshot_id?: string | null;
  status: string;
  stage: string;
  kind: "generate" | "revise" | "discuss" | "repair";
  base_version: number;
  request: string;
  error: string | null;
  questions: Question[];
  answers: Record<string, string>;
  partial: Record<string, unknown>;
  usage: unknown[];
  base_proposal_id?: string | null;
  prompt_version?: string;
};
export type Issue = {
  severity: "blocking" | "warning";
  target: string;
  message: string;
};
export type Change = {
  key: string;
  kind: "added" | "removed" | "changed";
  before: unknown;
  after: unknown;
};
export type Proposal = {
  id: string;
  base_version: number;
  candidate: Snapshot;
  summary: string;
  issues: Issue[];
  diff: Change[];
};
export type Revision = {
  version: number;
  summary: string;
  created_at: string;
  snapshot: Snapshot;
};
export type Bundle = {
  source_access?: { can_use: boolean; can_manage: boolean };
  project: Project;
  revision: Revision;
  proposal: Proposal | null;
  job: Job | null;
  messages: { id: number; role: "user" | "assistant"; content: string }[];
  revisions: Omit<Revision, "snapshot">[];
  screen_previews?: Record<string, string>;
  changed_block_ids?: string[];
};
export type Health = {
  status: string;
  auth_mode: string;
  ai_mode: string;
  provider: string;
  model: string;
  version: string;
};
export type Tab = "prd" | "features" | "flow" | "wireframes" | "implementation";
export type Panel = "chat" | "review" | "documents" | "versions";
export type ReviewRole = "developer" | "planner" | "security" | "ux" | "qa";
export type ReviewFinding = {
  severity: "critical" | "warning" | "suggestion";
  title: string;
  evidence: { target_id: string; quote: string }[];
  rationale: string;
  recommendation: string;
  acceptance: string[];
};
export type RoleReport = {
  id: string;
  proposal_id: string | null;
  version: number;
  snapshot_hash: string;
  commit_sha?: string;
  status: string;
  ai_mode: string;
  model: string;
  agents: {
    role: ReviewRole;
    status: string;
    attempts: { status: string; usage: unknown; error: string | null }[];
    result: {
      summary: string;
      reviewed_checks: string[];
      findings: ReviewFinding[];
    } | null;
    error: string | null;
  }[];
};

export type CodeEvidence = {
  id: string;
  path: string;
  sha256: string;
  start_line: number;
  end_line: number;
  quote: string;
};
export type SourceContext = {
  source_id: string;
  snapshot_id: string;
  name: string;
  repository: string;
  ref: string;
  commit_sha: string;
  analysis_version: string;
  files_analyzed: number;
  analysis_paths: string[];
  excluded: Record<string, number>;
  evidence: CodeEvidence[];
};
export type Source = {
  can_manage?: boolean;
  published_at?: string;
  id: string;
  name: string;
  description: string;
  kind: "local" | "github";
  repository: string;
  ref: string;
  current_snapshot_id: string | null;
  commit_sha: string | null;
  working_tree_dirty: boolean;
  status: "queued" | "running" | "ready" | "failed" | null;
  error: string | null;
  last_error: string | null;
  publication_id?: string | null;
  published_snapshot_id?: string | null;
  published_model?: { provider: string; model: string } | null;
  design_profile?: DesignProfile;
};
export type BusinessSource = Pick<
  Source,
  | "id"
  | "name"
  | "description"
  | "can_manage"
  | "publication_id"
  | "published_snapshot_id"
  | "published_model"
  | "published_at"
>;
export type SourcePreview = {
  context: SourceContext;
  model: { provider: string; model: string } | null;
  fingerprint: string;
};
export type SourceSelection = {
  source_id: string;
  code_snapshot_id: string;
  forked_from?: string;
  code_consent?: string;
  source_publication_id?: string;
};
export type PublicationPreview = SourcePreview & {
  scope: { path: string; sha256: string }[];
  design_profile: DesignProfile;
};
export type Implementation = {
  current_behavior: string;
  proposed_behavior: string;
  confirmed_policy: string[];
  preserve: string[];
  exceptions: string[];
  assumptions: string[];
  unresolved: string[];
  scope: {
    area: string;
    disposition: string;
    reason: string;
    evidence_ids: string[];
  }[];
  tasks: {
    id: string;
    requirement_ids: string[];
    evidence_ids: string[];
    acceptance_ids: string[];
    existing_targets: string[];
    proposed_targets: string[];
    reuse: string;
    implementation: string;
  }[];
  acceptance: { id: string; scenario: string }[];
};
