import { useEffect, useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import type { Node as CanvasNode, NodeProps, Edge } from "@xyflow/react";
import {
  ArrowUpRight,
  Check,
  FileText,
  GitBranch,
  Sparkles,
  Tag,
  Users,
  X,
} from "lucide-react";
import type { Feature, FlowNode, Requirement, Snapshot, Tab } from "./types";

type Update = (fn: (snapshot: Snapshot) => void) => void;
type Selection = (id: string) => void;
type PlanNode = CanvasNode<
  { label: string; kind: string; subtitle: string; priority?: string },
  "plan"
>;
function CanvasCard({ data, selected }: NodeProps<PlanNode>) {
  return (
    <div className={`canvas-node ${data.kind} ${selected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-meta">
        <span>
          {data.kind === "prd"
            ? "PRODUCT"
            : data.kind === "requirement"
              ? "요구사항"
              : data.kind === "feature"
                ? "기능"
                : (
                    {
                      screen: "화면",
                      decision: "분기",
                      start: "시작",
                      end: "종료",
                      action: "행동",
                    } as Record<string, string>
                  )[data.kind]}
        </span>
        {data.priority && <span className="priority">{data.priority}</span>}
      </div>
      <strong>{data.label}</strong>
      {data.subtitle && <small>{data.subtitle}</small>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { plan: CanvasCard };
export function Canvas({
  snapshot,
  mode,
  selected,
  onSelect,
  editing,
  update,
}: {
  snapshot: Snapshot;
  mode: "features" | "flow";
  selected: string | null;
  onSelect: Selection;
  editing: boolean;
  update: Update;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<PlanNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const computed = useMemo(() => {
    const n: PlanNode[] = [],
      e: {
        id: string;
        source: string;
        target: string;
        label?: string;
        type: string;
        markerEnd: { type: MarkerType };
        style: { stroke: string };
      }[] = [];
    const add = (
      id: string,
      label: string,
      kind: string,
      x: number,
      y: number,
      subtitle = "",
      priority?: string,
    ) =>
      n.push({
        id,
        type: "plan",
        position: { x, y },
        data: { label, kind, subtitle, priority },
        selected: id === selected,
      });
    const edge = (id: string, source: string, target: string, label = "") =>
      e.push({
        id,
        source,
        target,
        label,
        type: "smoothstep",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#94a3b8" },
      });
    if (mode === "features") {
      add(
        "prd-root",
        snapshot.prd.title,
        "prd",
        0,
        Math.max(0, snapshot.features.length * 65 - 80),
        `${snapshot.requirements.length}개 요구사항 · ${snapshot.features.length}개 기능`,
      );
      let row = 0;
      snapshot.requirements.forEach((r) => {
        const children = snapshot.features.filter(
          (f) => f.requirement_id === r.id,
        );
        const y = row * 145;
        add(
          r.id,
          r.title,
          "requirement",
          330,
          y,
          `${r.id} · ${children.length}개 기능`,
          r.priority,
        );
        edge(`root-${r.id}`, "prd-root", r.id);
        children.forEach((f, i) => {
          add(f.id, f.title, "feature", 680, y + i * 145, f.actor);
          edge(`f-${f.id}`, r.id, f.id);
        });
        row += Math.max(1, children.length) + 0.3;
      });
    } else {
      snapshot.flow.nodes.forEach((x) =>
        add(x.id, x.title, x.type, x.x, x.y, x.section),
      );
      snapshot.flow.edges.forEach((x) =>
        edge(x.id, x.source, x.target, x.label),
      );
    }
    return { n, e };
  }, [snapshot, mode, selected]);
  useEffect(() => {
    setNodes(computed.n);
    setEdges(computed.e);
  }, [computed, setNodes, setEdges]);
  return (
    <div className="graph-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={(_, n) => onSelect(n.id)}
        onPaneClick={() => onSelect("")}
        onNodeDragStop={(_, n) => {
          if (editing && mode === "flow")
            update((s) => {
              const target = s.flow.nodes.find((x) => x.id === n.id);
              if (target) {
                target.x = Math.round(n.position.x);
                target.y = Math.round(n.position.y);
              }
            });
        }}
        nodesDraggable={editing && mode === "flow"}
        nodesConnectable={false}
        edgesReconnectable={false}
        deleteKeyCode={null}
        fitView
        fitViewOptions={{ padding: 0.25, maxZoom: 1 }}
        minZoom={0.15}
        maxZoom={1.8}
        colorMode="light"
        attributionPosition="bottom-left"
      >
        <Background
          color="#c7d3e4"
          gap={22}
          size={1}
          variant={BackgroundVariant.Dots}
        />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) =>
            n.data.kind === "decision"
              ? "#f2d78e"
              : ["screen", "start", "end"].includes(String(n.data.kind))
                ? "#b7cdef"
                : "#dbe4ef"
          }
          maskColor="rgba(226, 232, 240, 0.6)"
        />
      </ReactFlow>
      <div className="canvas-legend">
        {mode === "features" ? (
          <>
            <span className="legend-dot purple" />
            요구사항
            <span className="legend-dot" />
            기능
          </>
        ) : (
          <>
            <span className="legend-dot purple" />
            화면
            <span className="legend-dot amber" />
            분기
            <span className="legend-dot" />
            행동
          </>
        )}
        <span className="legend-hint">드래그로 이동 · 스크롤로 확대</span>
      </div>
    </div>
  );
}

export function PrdDocument({
  snapshot,
  selected,
  editing,
  update,
  onSelect,
}: {
  snapshot: Snapshot;
  selected?: string | null;
  editing: boolean;
  update: Update;
  onSelect: Selection;
}) {
  const groups = [...new Set(snapshot.prd.sections.map((s) => s.group))];
  const completion = snapshot.prd.sections.length
    ? Math.round(
        (snapshot.prd.sections.filter((s) => s.content.trim()).length /
          snapshot.prd.sections.length) *
          100,
      )
    : 0;
  return (
    <>
      <div className="document-toolbar">
        <div className="completion">
          <span>기획 내용 작성률</span>
          <div>
            <i style={{ width: `${completion}%` }} />
          </div>
          <strong>{completion}%</strong>
        </div>
        <span className="subtle">{snapshot.prd.sections.length}개 항목</span>
      </div>
      <div className="document-scroll">
        <div className="document-page">
          <div className="document-cover">
            <span className="eyebrow">
              <FileText size={13} /> 업무 기획서
            </span>
            <h1>{snapshot.prd.title}</h1>
            <p>현재 업무와 바꾸려는 내용을 정리합니다.</p>
          </div>
          {groups.map((group, index) => (
            <section className="prd-group" key={group}>
              <div className="section-heading">
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h2>{group}</h2>
              </div>
              {snapshot.prd.sections
                .filter((s) => s.group === group)
                .map((section) => (
                  <div
                    id={section.id}
                    key={section.id}
                    className={`prd-field ${selected === section.id ? "review-focused" : ""}`}
                  >
                    <div className="field-title">
                      <h3>{section.title}</h3>
                      <button
                        className="icon-button"
                        title="이 항목을 AI와 수정"
                        aria-label={`${section.title} 선택`}
                        onClick={() => onSelect(section.id)}
                      >
                        <Sparkles size={14} />
                      </button>
                    </div>
                    {editing ? (
                      <textarea
                        className="document-input"
                        aria-label={`${section.title} 편집`}
                        value={section.content}
                        onChange={(e) =>
                          update((s) => {
                            s.prd.sections.find(
                              (x) => x.id === section.id,
                            )!.content = e.target.value;
                          })
                        }
                      />
                    ) : (
                      <p>
                        {section.content || (
                          <span className="subtle">
                            아직 작성되지 않았어요.
                          </span>
                        )}
                      </p>
                    )}
                  </div>
                ))}
            </section>
          ))}
          <section className="prd-group">
            <div className="section-heading">
              <span>05</span>
              <h2>업무 담당자와 사용 환경</h2>
            </div>
            <div className="attribute-row">
              <span>
                <Users size={15} />
                업무 담당자
              </span>
              <div>
                {snapshot.prd.roles.map((r) => (
                  <span className="chip" key={r}>
                    {r}
                  </span>
                ))}
              </div>
            </div>
            <div className="attribute-row">
              <span>
                <Tag size={15} />
                사용 환경
              </span>
              <div>
                {snapshot.prd.platforms.map((p) => (
                  <span className="chip" key={p}>
                    {p}
                  </span>
                ))}
              </div>
            </div>
          </section>
          {snapshot.prd.assumptions.length > 0 && (
            <section className="assumptions">
              <h3>함께 확인할 업무 기준</h3>
              {snapshot.prd.assumptions.map((a, i) => (
                <p key={i}>
                  <span>{i + 1}</span>
                  {a}
                </p>
              ))}
            </section>
          )}
          <div className="document-end">
            <Check size={14} /> 기능 상세·업무 흐름·화면 시안과 연결됩니다.
          </div>
        </div>
      </div>
    </>
  );
}

export function FeaturesView({
  snapshot,
  selected,
  onSelect,
}: {
  snapshot: Snapshot;
  selected: string | null;
  onSelect: Selection;
  editing: boolean;
  update: Update;
}) {
  return (
    <>
      <div className="view-toolbar">
        <strong>업무별 기능과 처리 순서</strong>
        <span className="toolbar-count">
          요구사항 {snapshot.requirements.length} · 기능{" "}
          {snapshot.features.length}
        </span>
      </div>
      <div className="feature-scroll">
        {snapshot.requirements.map((requirement) => (
          <section
            className="requirement-group"
            id={requirement.id}
            key={requirement.id}
          >
            <button
              className={`requirement-heading ${selected === requirement.id ? "selected" : ""}`}
              onClick={() => onSelect(requirement.id)}
            >
              <strong>{requirement.title}</strong>
              <span className="priority">
                {{ P0: "필수", P1: "중요", P2: "추후" }[requirement.priority]}
              </span>
              <ArrowUpRight size={15} />
            </button>
            <p className="req-description">{requirement.description}</p>
            {snapshot.features
              .filter((feature) => feature.requirement_id === requirement.id)
              .map((feature) => (
                <article
                  id={feature.id}
                  className={`feature-article ${selected === feature.id ? "review-focused" : ""}`}
                  key={feature.id}
                >
                  <button
                    className="text-button"
                    onClick={() => onSelect(feature.id)}
                  >
                    <h3>{feature.title}</h3>
                    <ArrowUpRight size={15} />
                  </button>
                  <p>{feature.description}</p>
                  <div className="feature-actor">
                    업무 담당자 · {feature.actor}
                  </div>
                  {!!feature.preconditions.length && (
                    <p className="feature-rules">
                      시작 조건 · {feature.preconditions.join(" / ")}
                    </p>
                  )}
                  <div className="feature-columns">
                    <div>
                      <h4>처리 순서</h4>
                      <ol>
                        {feature.steps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                    </div>
                    <div>
                      <h4>예외와 완료 조건</h4>
                      <ul>
                        {[...feature.exceptions, ...feature.acceptance].map(
                          (item, i) => (
                            <li key={i}>{item}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  </div>
                </article>
              ))}
          </section>
        ))}
      </div>
    </>
  );
}

export function Inspector({
  snapshot,
  selected,
  tab,
  editing,
  update,
  onClose,
  onAsk,
  onTab,
}: {
  snapshot: Snapshot;
  selected: string;
  tab: Tab;
  editing: boolean;
  update: Update;
  onClose: () => void;
  onAsk: () => void;
  onTab: (tab: Tab) => void;
}) {
  const req = snapshot.requirements.find((x) => x.id === selected),
    feature = snapshot.features.find((x) => x.id === selected),
    node = snapshot.flow.nodes.find((x) => x.id === selected);
  const item = req || feature || node;
  if (!item) return null;
  const kind = req ? "요구사항" : feature ? "기능명세" : "흐름 노드";
  const alter = (key: string, value: unknown) =>
    update((s) => {
      const target = (
        req ? s.requirements : feature ? s.features : s.flow.nodes
      ).find((x) => x.id === selected);
      if (target) Object.assign(target, { [key]: value });
    });
  const list = (
    key: "steps" | "preconditions" | "exceptions" | "acceptance",
    label: string,
  ) => {
    const values =
      (feature as Feature | undefined)?.[key] ||
      (req as Requirement | undefined)?.[key as "acceptance"];
    return (
      values && (
        <div className="inspector-field">
          <h4>{label}</h4>
          {editing ? (
            <textarea
              aria-label={`${label} 편집`}
              value={values.join("\n")}
              onChange={(e) => alter(key, e.target.value.split("\n"))}
            />
          ) : (
            <ul>
              {values.map((v, i) => (
                <li key={i}>{v}</li>
              ))}
            </ul>
          )}
        </div>
      )
    );
  };
  return (
    <aside className="inspector">
      <div className="panel-heading">
        <span className="eyebrow">{kind}</span>
        <button
          className="icon-button"
          aria-label="상세 닫기"
          onClick={onClose}
        >
          <X size={17} />
        </button>
      </div>
      <div className="inspector-body">
        {editing ? (
          <input
            className="inspector-title-input"
            aria-label="항목 제목 편집"
            value={item.title}
            onChange={(e) => alter("title", e.target.value)}
          />
        ) : (
          <h2>{item.title}</h2>
        )}
        {"description" in item && (
          <div className="inspector-field">
            <h4>설명</h4>
            {editing ? (
              <textarea
                aria-label="설명 편집"
                value={item.description}
                onChange={(e) => alter("description", e.target.value)}
              />
            ) : (
              <p>{item.description}</p>
            )}
          </div>
        )}
        {feature && (
          <div className="attribute-row">
            <span>사용자</span>
            <span className="chip">{feature.actor}</span>
          </div>
        )}
        {list("preconditions", "업무 시작 조건")}
        {list("steps", "처리 순서")}
        {list("exceptions", "예외 처리")}
        {list("acceptance", "완료 조건")}
        {node && (
          <>
            <div className="attribute-row">
              <span>유형</span>
              <span className="chip">
                {
                  {
                    start: "시작",
                    screen: "화면",
                    action: "업무 처리",
                    decision: "조건 확인",
                    end: "종료",
                  }[node.type]
                }
              </span>
            </div>
            <div className="inspector-field">
              <h4>연결된 기능</h4>
              {node.feature_ids.map((id) => (
                <p key={id}>
                  {snapshot.features.find((f) => f.id === id)?.title || id}
                </p>
              ))}
            </div>
            {snapshot.screens
              .filter((w) => w.node_id === node.id)
              .map((w) => (
                <button
                  className="link-card"
                  key={w.id}
                  onClick={() => onTab("wireframes")}
                >
                  <FileText size={15} />
                  {w.title} 화면 시안
                  <ArrowUpRight size={14} />
                </button>
              ))}
          </>
        )}
        {tab === "features" &&
          feature &&
          snapshot.flow.nodes.filter((n) => n.feature_ids.includes(feature.id))
            .length > 0 && (
            <button className="link-card" onClick={() => onTab("flow")}>
              <GitBranch size={15} />
              연결된 업무 흐름
              <ArrowUpRight size={14} />
            </button>
          )}
      </div>
      <div className="inspector-footer">
        <button className="secondary" onClick={onAsk}>
          <Sparkles size={15} /> 이 항목을 AI와 수정
        </button>
      </div>
    </aside>
  );
}
