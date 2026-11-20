import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, Check, LoaderCircle, Settings2 } from "lucide-react";
import { api } from "./api";
import { SourcePicker, Evidence } from "./Sources";
import { Brand } from "./BusinessHome";
import { WirePage } from "./Wireframes";
import type { DesignProfile, PublicationPreview, Source } from "./types";

export default function SourceSettings({
  accountMenu,
  navigation,
  onHome,
  onAssignments,
  onError,
}: {
  accountMenu: ReactNode;
  navigation: ReactNode;
  onHome: () => void;
  onAssignments?: () => void;
  onError: (e: unknown) => void;
}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState(
    new URLSearchParams(location.search).get("source") || "",
  );
  const [profile, setProfile] = useState<DesignProfile | null>(null);
  const [preview, setPreview] = useState<PublicationPreview | null>(null);
  const [confirmed, setConfirmed] = useState<PublicationPreview | null>(null);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const selected = sources.find((s) => s.id === sourceId);
  const refresh = useCallback(
    async () =>
      setSources(
        (await api<Source[]>("/api/sources")).filter(
          (s) => s.can_manage !== false,
        ),
      ),
    [],
  );
  useEffect(() => {
    void refresh().catch(onError);
  }, [refresh, onError]);
  const analyzing = sources.some((s) =>
    ["queued", "running"].includes(s.status || ""),
  );
  useEffect(() => {
    if (!analyzing) return;
    const timer = setInterval(() => void refresh().catch(onError), 1400);
    return () => clearInterval(timer);
  }, [analyzing, refresh, onError]);
  const snapshotId = selected?.current_snapshot_id;
  const ready = selected?.status === "ready";
  useEffect(() => {
    let active = true;
    setPreview(null);
    setProfile(null);
    setConfirmed(null);
    setNotice("");
    if (sourceId && snapshotId && ready)
      api<PublicationPreview>(
        `/api/sources/${sourceId}/snapshots/${snapshotId}/publication-preview`,
        {},
      )
        .then((result) => {
          if (active) {
            setPreview(result);
            setProfile(result.design_profile);
          }
        })
        .catch(onError);
    return () => {
      active = false;
    };
  }, [sourceId, snapshotId, ready, onError]);
  const change = <K extends keyof DesignProfile>(
    key: K,
    value: DesignProfile[K],
  ) => {
    setProfile((current) => current && { ...current, [key]: value });
    setConfirmed(null);
    setNotice("");
  };
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
    <div className="source-settings">
      <header className="business-header">
        <div className="header-brand">
          {navigation}
          <Brand />
        </div>
        <div className="business-header-actions">
          {onAssignments && (
            <button className="secondary" onClick={onAssignments}>
              업무 배정
            </button>
          )}
          <button className="secondary" onClick={onHome}>
            <ArrowLeft size={16} /> 업무 선택으로 돌아가기
          </button>
          {accountMenu}
        </div>
      </header>
      <main className="settings-main">
        <div className="page-heading">
          <span className="eyebrow">업무 연결 준비</span>
          <h1>
            <Settings2 size={25} /> 업무 연결 설정
          </h1>
          <p>
            기존 시스템의 연결·코드 사용 범위·화면 디자인을 준비한 뒤 업무를
            게시합니다.
          </p>
        </div>
        <SourcePicker
          sources={sources}
          selected={selected}
          onSelect={(id) => {
            setSourceId(id);
            window.history.replaceState({}, "", `/?view=settings&source=${id}`);
          }}
          refresh={refresh}
          onError={onError}
        />
        {selected && !ready && (
          <div className="home-empty">
            <LoaderCircle size={22} className={analyzing ? "spin" : ""} />
            <p>업무 분석이 준비되면 디자인과 코드 범위를 확인할 수 있습니다.</p>
          </div>
        )}
        {preview && profile && (
          <>
            <section className="settings-section">
              <h2>화면 디자인</h2>
              <p>
                {profile.evidence.length
                  ? "분석된 소스의 스타일에서 가져온 값입니다. 공통 화면에 맞게 보완할 수 있습니다."
                  : "확인 가능한 스타일이 없어 기본 디자인을 사용합니다. 필요한 값을 직접 지정할 수 있습니다."}
              </p>
              <div className="design-settings-grid">
                <div className="design-fields">
                  {(
                    [
                      ["primary", "주요 버튼"],
                      ["background", "화면 배경"],
                      ["surface", "구획 배경"],
                      ["text", "본문 글자"],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key}>
                      {label}
                      <input
                        type="color"
                        aria-label={label}
                        value={profile[key]}
                        onChange={(e) => change(key, e.target.value)}
                      />
                    </label>
                  ))}
                  <label>
                    글꼴
                    <select
                      value={profile.font}
                      onChange={(e) =>
                        change("font", e.target.value as DesignProfile["font"])
                      }
                    >
                      <option value="system">시스템 기본</option>
                      <option value="sans">고딕</option>
                      <option value="serif">명조</option>
                      <option value="mono">고정폭</option>
                    </select>
                  </label>
                  <label>
                    공통 배치
                    <select
                      value={profile.shell}
                      onChange={(e) =>
                        change(
                          "shell",
                          e.target.value as DesignProfile["shell"],
                        )
                      }
                    >
                      <option value="header">상단 메뉴</option>
                      <option value="sidebar">측면 메뉴</option>
                      <option value="plain">본문 중심</option>
                    </select>
                  </label>
                  <label>
                    항목 간격
                    <input
                      type="number"
                      min={8}
                      max={32}
                      value={profile.spacing}
                      onChange={(e) =>
                        change("spacing", Number(e.target.value))
                      }
                    />
                  </label>
                  <label>
                    모서리 둥글기
                    <input
                      type="number"
                      min={0}
                      max={24}
                      value={profile.radius}
                      onChange={(e) => change("radius", Number(e.target.value))}
                    />
                  </label>
                </div>
                <div className="design-sample">
                  <WirePage
                    designProfile={profile}
                    screen={{
                      id: "sample",
                      node_id: "sample",
                      title: "업무 목록 예시",
                      device: "desktop",
                      layout: "list",
                      blocks: [
                        {
                          id: "sample-nav",
                          type: "navigation",
                          label: selected?.name || "업무",
                          content: "업무 목록 · 상세 확인",
                          target_screen_id: null,
                          region: "navigation",
                        },
                        {
                          id: "sample-title",
                          type: "heading",
                          label: "업무 목록",
                          content: "기존 디자인을 참고한 시안 예시입니다.",
                          target_screen_id: null,
                          region: "header",
                        },
                        {
                          id: "sample-search",
                          type: "input",
                          label: "검색 조건",
                          content: "조회할 내용을 입력하세요",
                          target_screen_id: null,
                          region: "filters",
                        },
                        {
                          id: "sample-table",
                          type: "table",
                          label: "처리 내역",
                          content: "",
                          columns: ["업무", "담당자", "상태"],
                          rows: [["업무 예시", "담당자", "진행 중"]],
                          target_screen_id: null,
                        },
                        {
                          id: "sample-btn",
                          type: "button",
                          label: "조회",
                          content: "",
                          target_screen_id: null,
                          region: "actions",
                        },
                      ],
                    }}
                  />
                </div>
              </div>
              {!!profile.evidence.length && (
                <details>
                  <summary>스타일 참고 파일</summary>
                  <ul>
                    {profile.evidence.map((path) => (
                      <li key={path}>
                        <code>{path}</code>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </section>
            <section className="settings-section">
              <h2>코드 사용 범위 확인</h2>
              <p>
                이 업무의 대화·기획·검토는 아래 분석 파일 중 요청과 관련된
                발췌를 사용합니다. 게시 후 시작하는 기획은 이 코드 기준과 디자인
                설정을 고정합니다.
              </p>
              <p>
                {preview.model
                  ? `${preview.model.provider} / ${preview.model.model}에 관련 코드 발췌가 전송되며 기획 기록에 보관됩니다. 공급자의 처리는 연결 정책을 따릅니다.`
                  : "로컬 AI 데모에서는 외부 모델로 코드를 전송하지 않습니다."}
              </p>
              <details>
                <summary>
                  사용 가능한 분석 파일 {preview.scope.length}개
                </summary>
                <ul className="scope-files">
                  {preview.scope.map((item) => (
                    <li key={item.path}>
                      <code>{item.path}</code>
                    </li>
                  ))}
                </ul>
              </details>
              <details>
                <summary>현재 발췌 예시</summary>
                <Evidence evidence={preview.context.evidence} />
              </details>
              <div className="publication-actions">
                <button
                  className="secondary"
                  disabled={working}
                  onClick={() =>
                    void run(async () => {
                      setConfirmed(
                        await api<PublicationPreview>(
                          `/api/sources/${sourceId}/snapshots/${snapshotId}/publication-preview`,
                          { design_profile: profile },
                        ),
                      );
                    })
                  }
                >
                  이 코드 범위와 디자인으로 준비
                </button>
                {confirmed && (
                  <button
                    className="primary"
                    disabled={working}
                    onClick={() =>
                      void run(async () => {
                        await api(`/api/sources/${sourceId}/publish`, {
                          snapshot_id: snapshotId,
                          fingerprint: confirmed.fingerprint,
                          design_profile: confirmed.design_profile,
                        });
                        await refresh();
                        setNotice(
                          "업무를 게시했어요. 업무 선택 화면에서 기획을 시작할 수 있습니다.",
                        );
                        setConfirmed(null);
                      })
                    }
                  >
                    <Check size={16} /> 확인하고 업무 게시
                  </button>
                )}
              </div>
              {notice && (
                <p className="valid-check" role="status">
                  {notice}
                </p>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
