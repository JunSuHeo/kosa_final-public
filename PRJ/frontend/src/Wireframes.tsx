import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  LayoutTemplate,
  Monitor,
  MousePointer2,
  Plus,
  Settings2,
  Smartphone,
  Trash2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { Block, BlockType, Screen, Snapshot } from "./types";
type Update = (fn: (s: Snapshot) => void) => void;
const blockLabels: Record<BlockType, string> = {
  heading: "제목",
  text: "본문",
  input: "입력 필드",
  button: "버튼",
  card: "정보 카드",
  list: "목록",
  stat: "지표",
  navigation: "탐색 메뉴",
};
export function WirePage({
  screen,
  selectedBlock,
  onSelect,
  onNavigate,
  interactive = false,
}: {
  screen: Screen;
  selectedBlock?: string;
  onSelect?: (id: string) => void;
  onNavigate?: (id: string) => void;
  interactive?: boolean;
}) {
  const activate = (block: Block) => {
    if (interactive && block.target_screen_id)
      onNavigate?.(block.target_screen_id);
    else onSelect?.(block.id);
  };
  return (
    <div className={`wire-page ${screen.device}`}>
      <div className="wire-browser">
        {screen.device === "desktop" ? (
          <>
            <i />
            <i />
            <i />
            <span>preview / {screen.title}</span>
          </>
        ) : (
          <>
            <span>9:41</span>
            <div className="phone-notch" />
            <span>▰ ▪</span>
          </>
        )}
      </div>
      <div className="wire-page-body">
        {screen.blocks.map((block) => (
          <div
            tabIndex={
              onSelect || (interactive && block.target_screen_id)
                ? 0
                : undefined
            }
            role={
              onSelect || (interactive && block.target_screen_id)
                ? "button"
                : undefined
            }
            aria-label={
              onSelect
                ? `블록 선택 ${block.label}`
                : interactive && block.target_screen_id
                  ? block.label
                  : undefined
            }
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                activate(block);
              }
            }}
            key={block.id}
            className={`wire-block wire-${block.type} ${block.type === "stat" && block.content.length > 32 ? "long-stat" : ""} ${selectedBlock === block.id ? "block-selected" : ""} ${interactive && block.target_screen_id ? "can-navigate" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              activate(block);
            }}
          >
            {block.type === "navigation" ? (
              <>
                <strong>{block.label}</strong>
                <span>{block.content}</span>
              </>
            ) : block.type === "heading" ? (
              <>
                <h1>{block.label}</h1>
                {block.content && <p>{block.content}</p>}
              </>
            ) : block.type === "input" ? (
              <>
                <label>{block.label}</label>
                <div className="fake-input">
                  {block.content || "입력해 주세요"}
                </div>
              </>
            ) : block.type === "button" ? (
              <div className="wire-button-surface">
                {block.label}
                <ArrowUpRight size={15} />
              </div>
            ) : block.type === "list" ? (
              <>
                <h3>{block.label}</h3>
                {block.content
                  .split("\n")
                  .filter(Boolean)
                  .map((text, i) => (
                    <div className="wire-list-item" key={i}>
                      <span className="wire-checkbox" />
                      {text}
                      <ChevronRight size={13} />
                    </div>
                  ))}
              </>
            ) : block.type === "stat" ? (
              <>
                <span>{block.label}</span>
                <strong>{block.content}</strong>
                <div className="mini-bars">
                  {[34, 48, 39, 63, 55, 77, 68, 90].map((h, i) => (
                    <i key={i} style={{ height: h + "%" }} />
                  ))}
                </div>
              </>
            ) : (
              <>
                <h3>{block.label}</h3>
                <p>{block.content}</p>
              </>
            )}
          </div>
        ))}
      </div>
      {screen.device === "mobile" && <div className="phone-home" />}
    </div>
  );
}

export default function Wireframes({
  snapshot,
  editing,
  update,
  onSelectItem,
  onFlow,
  focusId,
  screenPreviews,
}: {
  snapshot: Snapshot;
  screenPreviews?: Record<string, string>;
  editing: boolean;
  update: Update;
  onSelectItem: (id: string) => void;
  onFlow: () => void;
  focusId?: string | null;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(true);
  const [blockId, setBlockId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(85);
  const [preview, setPreview] = useState(false);
  const [properties, setProperties] = useState(() => window.innerWidth > 900);
  useEffect(() => {
    if (selected && !snapshot.screens.some((s) => s.id === selected)) {
      setSelected(null);
      setBlockId(null);
    }
  }, [snapshot.screens, selected]);
  useEffect(() => {
    if (!focusId) return;
    const target = snapshot.screens.find((s) => s.id === focusId || s.blocks.some((b) => b.id === focusId));
    if (target) {
      setSelected(target.id);
      setBlockId(target.id === focusId ? null : focusId);
      setPreview(false);
      if (target.id !== focusId) setShowSource(false);
    }
  }, [focusId, snapshot.screens]);
  const screen = snapshot.screens.find((s) => s.id === selected);
  const sourcePreview = screen ? screenPreviews?.[screen.id] : undefined;
  const displayingSource = !!sourcePreview && showSource && !editing;
  const block = screen?.blocks.find((b) => b.id === blockId);
  const index = snapshot.screens.findIndex((s) => s.id === selected);
  const pick = (id: string) => {
    setSelected(id);
    setBlockId(null);
    setShowSource(!preview);
    setProperties(window.innerWidth > 900);
  };
  const editBlock = (patch: Partial<Block>) =>
    update((s) => {
      const b = s.screens
        .find((w) => w.id === selected)
        ?.blocks.find((b) => b.id === blockId);
      if (b) Object.assign(b, patch);
    });
  const addBlock = () => {
    if (!screen) return;
    const id = "block-" + crypto.randomUUID().slice(0, 8);
    update((s) =>
      s.screens
        .find((w) => w.id === screen.id)!
        .blocks.push({
          id,
          type: "text",
          label: "새 항목",
          content: "내용을 입력해 주세요.",
          target_screen_id: null,
        }),
    );
    setBlockId(id);
  };
  const shift = (direction: number) => {
    if (!screen || !block) return;
    update((s) => {
      const items = s.screens.find((w) => w.id === screen.id)!.blocks;
      const i = items.findIndex((x) => x.id === block.id),
        j = i + direction;
      if (j >= 0 && j < items.length)
        [items[i], items[j]] = [items[j], items[i]];
    });
  };
  return (
    <>
      <div className="view-toolbar">
        <div className="wire-view-title">
          {screen ? (
            <button
              className="text-button"
              onClick={() => {
                setSelected(null);
                setBlockId(null);
                setPreview(false);
              }}
            >
              <ArrowLeft size={15} />
              전체 화면
            </button>
          ) : (
            <span>
              <LayoutTemplate size={16} /> 화면 설계
            </span>
          )}
          {screen && (
            <>
              <span className="toolbar-divider" />
              <strong>{screen.title}</strong>
            </>
          )}
        </div>
        <div className="toolbar-actions">
          {sourcePreview && !editing && (
            <div className="segmented" aria-label="화면 보기 방식">
              <button className={displayingSource ? "active" : ""} aria-pressed={displayingSource} onClick={() => {
                setPreview(false);
                setShowSource(true);
              }}>소스 화면</button>
              <button className={!displayingSource ? "active" : ""} aria-pressed={!displayingSource} onClick={() => setShowSource(false)}>생성 설계안</button>
            </div>
          )}
          {screen && !displayingSource && (
            <>
              <button
                className={`secondary small ${preview ? "is-active" : ""}`}
                onClick={() => {
                  setPreview(!preview);
                  setBlockId(null);
                }}
              >
                <MousePointer2 size={13} />
                {preview ? "미리보기 종료" : "미리보기"}
              </button>
              {!preview && (
                <button
                  className="icon-button"
                  aria-label="화면 속성 패널"
                  aria-pressed={properties}
                  onClick={() => setProperties(!properties)}
                >
                  <Settings2 size={15} />
                </button>
              )}
              <button
                className="icon-button"
                aria-label="와이어프레임 축소"
                onClick={() => setZoom(Math.max(40, zoom - 10))}
              >
                <ZoomOut size={16} />
              </button>
              <span className="zoom-value">{zoom}%</span>
              <button
                className="icon-button"
                aria-label="와이어프레임 확대"
                onClick={() => setZoom(Math.min(120, zoom + 10))}
              >
                <ZoomIn size={16} />
              </button>
            </>
          )}
          <span className="toolbar-count">
            {screen
              ? `${index + 1} / ${snapshot.screens.length}`
              : `${snapshot.screens.length}개 화면`}
          </span>
        </div>
      </div>
      <div className="wire-workspace">
        <div className="wire-canvas dot-background">
          {!screen ? (
            <>
              <div className="wire-gallery-heading">
                <span className="eyebrow">CONNECTED SCREENS</span>
                <h2>제품의 흐름이 화면이 됩니다.</h2>
                <p>화면을 선택해 세부 구성을 확인하고 다듬어 보세요.</p>
              </div>
              <div className="wire-gallery">
                {snapshot.screens.map((w, i) => (
                  <button
                    className="wire-thumbnail"
                    key={w.id}
                    onClick={() => pick(w.id)}
                  >
                    <div className="thumbnail-caption">
                      <span>
                        <small>{String(i + 1).padStart(2, "0")}</small>
                        {w.title}
                      </span>
                      {w.device === "mobile" ? (
                        <Smartphone size={15} />
                      ) : (
                        <Monitor size={15} />
                      )}
                    </div>
                    <div className="thumbnail-viewport">
                      {screenPreviews?.[w.id] && !editing ? (
                        <iframe
                          className="thumbnail-source"
                          src={screenPreviews[w.id]}
                          title={`소스 화면 미리보기 ${w.title}`}
                          loading="lazy"
                          tabIndex={-1}
                          aria-hidden="true"
                          sandbox="allow-scripts allow-same-origin"
                          referrerPolicy="no-referrer"
                        />
                      ) : (
                        <div className="thumbnail-scale">
                          <WirePage screen={w} />
                        </div>
                      )}
                    </div>
                    <div className="thumbnail-footer">
                      <span>
                        {
                          snapshot.flow.nodes.find((n) => n.id === w.node_id)
                            ?.section
                        }
                      </span>
                      <ArrowUpRight size={15} />
                    </div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              {displayingSource ? (
                <section className="wire-source-preview" aria-label="로컬 소스 화면">
                  <div>{snapshot.source_context?.name} 소스 화면 · 테스트 데이터</div>
                  <iframe
                    key={sourcePreview}
                    src={sourcePreview}
                    title={`소스 화면 ${screen.title}`}
                    sandbox="allow-scripts allow-same-origin allow-downloads"
                    referrerPolicy="no-referrer"
                  />
                </section>
              ) : (
                <div
                  className="wire-single"
                  style={{
                    paddingBottom: Math.max(40, (zoom / 100 - 1) * 800 + 40),
                  }}
                >
                  <div
                    className="wire-sheet"
                    style={{
                      transform: `scale(${zoom / 100})`,
                      transformOrigin: "top center",
                    }}
                  >
                    <WirePage
                      screen={screen}
                      selectedBlock={blockId || undefined}
                      onSelect={
                        !preview
                          ? (id) => {
                              setBlockId(id);
                              setProperties(true);
                              onSelectItem(id);
                            }
                          : undefined
                      }
                      interactive={preview}
                      onNavigate={pick}
                    />
                  </div>
                </div>
              )}
              <div className="wire-pagination">
                <button
                  className="icon-button"
                  aria-label="이전 화면"
                  disabled={index <= 0}
                  onClick={() => pick(snapshot.screens[index - 1].id)}
                >
                  <ChevronLeft size={17} />
                </button>
                <span>{screen.title}</span>
                <button
                  className="icon-button"
                  aria-label="다음 화면"
                  disabled={index >= snapshot.screens.length - 1}
                  onClick={() => pick(snapshot.screens[index + 1].id)}
                >
                  <ChevronRight size={17} />
                </button>
              </div>
              {preview && !displayingSource && (
                <div className="preview-notice">
                  <MousePointer2 size={13} /> 연결된 버튼을 눌러 화면 이동을
                  확인하세요.
                </div>
              )}
            </>
          )}
        </div>
        {screen && !displayingSource && !preview && properties && (
          <aside className="wire-inspector">
            <div className="panel-heading">
              <strong>{block ? "요소 속성" : "화면 속성"}</strong>
              <button
                className="icon-button"
                aria-label="속성 패널 닫기"
                onClick={() => {
                  setBlockId(null);
                  setProperties(false);
                }}
              >
                <X size={15} />
              </button>
            </div>
            <div className="inspector-body">
              {block ? (
                <>
                  <span className="id-badge">{block.id}</span>
                  <h3>{blockLabels[block.type]}</h3>
                  <label className="property-label">
                    요소 유형
                    <select
                      disabled={!editing}
                      value={block.type}
                      onChange={(e) =>
                        editBlock({ type: e.target.value as BlockType })
                      }
                    >
                      {Object.entries(blockLabels).map(([type, label]) => (
                        <option key={type} value={type}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="property-label">
                    표시 텍스트
                    <input
                      aria-label="요소 표시 텍스트"
                      disabled={!editing}
                      value={block.label}
                      onChange={(e) => editBlock({ label: e.target.value })}
                    />
                  </label>
                  <label className="property-label">
                    내용
                    <textarea
                      aria-label="요소 내용"
                      disabled={!editing}
                      value={block.content}
                      onChange={(e) => editBlock({ content: e.target.value })}
                    />
                  </label>
                  <label className="property-label">
                    연결할 화면
                    <select
                      disabled={!editing}
                      value={block.target_screen_id || ""}
                      onChange={(e) =>
                        editBlock({ target_screen_id: e.target.value || null })
                      }
                    >
                      <option value="">화면 이동 없음</option>
                      {snapshot.screens.map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  {editing && (
                    <div className="block-actions">
                      <button
                        className="secondary small"
                        aria-label="요소 위로"
                        onClick={() => shift(-1)}
                      >
                        <ArrowUp size={15} />
                      </button>
                      <button
                        className="secondary small"
                        aria-label="요소 아래로"
                        onClick={() => shift(1)}
                      >
                        <ArrowDown size={15} />
                      </button>
                      <button
                        className="secondary small danger-text"
                        aria-label="요소 삭제"
                        onClick={() => {
                          update((s) => {
                            const w = s.screens.find(
                              (w) => w.id === screen.id,
                            )!;
                            w.blocks = w.blocks.filter(
                              (b) => b.id !== block.id,
                            );
                          });
                          setBlockId(null);
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <span className="eyebrow">SCREEN</span>
                  <h2>{screen.title}</h2>
                  <label className="property-label">
                    화면 제목
                    <input
                      aria-label="화면 제목 편집"
                      disabled={!editing}
                      value={screen.title}
                      onChange={(e) =>
                        update((s) => {
                          s.screens.find((w) => w.id === screen.id)!.title =
                            e.target.value;
                        })
                      }
                    />
                  </label>
                  <label className="property-label">
                    디바이스
                    <select
                      disabled={!editing}
                      value={screen.device}
                      onChange={(e) =>
                        update((s) => {
                          s.screens.find((w) => w.id === screen.id)!.device = e
                            .target.value as Screen["device"];
                        })
                      }
                    >
                      <option value="desktop">데스크톱 웹</option>
                      <option value="mobile">모바일</option>
                    </select>
                  </label>
                  <button className="link-card" onClick={onFlow}>
                    유저플로우에서 확인
                    <ArrowUpRight size={14} />
                  </button>
                  <div className="property-tip">
                    <MousePointer2 size={18} />
                    <p>
                      화면 안의 요소를 선택하면 텍스트와 연결을 확인할 수
                      있어요.
                    </p>
                  </div>
                </>
              )}
              {!editing && (
                <p className="editing-hint">
                  상단의 직접 편집을 누르면 수정할 수 있어요.
                </p>
              )}
            </div>
            {editing && (
              <div className="inspector-footer">
                <button
                  className="secondary"
                  onClick={addBlock}
                  disabled={screen.blocks.length >= 24}
                >
                  <Plus size={15} />
                  요소 추가
                </button>
              </div>
            )}
          </aside>
        )}
      </div>
    </>
  );
}
