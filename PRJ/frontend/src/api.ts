let accessToken = sessionStorage.getItem("studio-token") || "";
export function setToken(token: string, persist = true) {
  accessToken = token;
  token && persist
    ? sessionStorage.setItem("studio-token", token)
    : sessionStorage.removeItem("studio-token");
}
let accessGuard: ((path: string, method: string) => Promise<void>) | null =
  null;
export function setAccessGuard(guard: typeof accessGuard) {
  accessGuard = guard;
}
export async function api<T>(
  path: string,
  body?: unknown,
  method?: string,
  signal?: AbortSignal,
): Promise<T> {
  await accessGuard?.(path, method || (body === undefined ? "GET" : "POST"));
  const res = await fetch(path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    signal,
  });
  if (!res.ok) {
    let detail = "요청을 처리하지 못했습니다.";
    try {
      const data = await res.json();
      detail =
        typeof data.detail === "string"
          ? data.detail
          : "입력한 내용을 확인해 주세요.";
    } catch {
      /* HTTP response without a JSON error */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json();
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function download(path: string) {
  await accessGuard?.(path, "GET");
  const res = await fetch(path, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok)
    throw new Error("내보내기에 실패했습니다. 확정된 버전을 선택해 주세요.");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download =
    res.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] ||
    "planning.md";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
