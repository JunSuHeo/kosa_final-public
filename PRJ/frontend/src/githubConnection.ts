export type GitHubConnection = {
  enabled: boolean;
  connected: boolean;
  login: string | null;
  install_url: string | null;
};

export type GitHubRepository = {
  name: string;
  branch: string;
  private: boolean;
};

const draftKey = "studio-github-registration";

export function leaveForGitHub(url: string, form: HTMLFormElement) {
  const target = new URL(url);
  if (target.origin !== "https://github.com" || target.pathname !== "/login/oauth/authorize") {
    throw new Error("GitHub 승인 주소를 확인할 수 없습니다.");
  }
  const state = target.searchParams.get("state");
  const fields = Object.fromEntries(new FormData(form));
  sessionStorage.setItem(draftKey, JSON.stringify({ state, fields }));
  location.assign(target.href);
}

function readGitHubReturn() {
  if (location.pathname !== "/github/callback") return null;
  const params = new URLSearchParams(location.search);
  const raw = sessionStorage.getItem(draftKey);
  sessionStorage.removeItem(draftKey);
  history.replaceState({}, "", "/?view=settings");
  const code = params.get("code");
  const state = params.get("state");
  let draft: { state: string; fields: Record<string, string> } | null = null;
  try {
    if (raw) draft = JSON.parse(raw);
  } catch {
    // An unreadable draft cannot be matched to a GitHub return.
  }
  if (!state || !draft || draft.state !== state) {
    return { approval: null, fields: {} };
  }
  return { approval: code ? { state, code } : null, fields: draft.fields ?? {} };

}

export let githubReturn = readGitHubReturn();

export function clearGitHubReturn() {
  githubReturn = null;
}
