import { test as base, expect, type APIRequestContext } from "@playwright/test";

export const headers = { Authorization: "" };
export async function loginHeaders(request: APIRequestContext, identifier: string) {
  const result = await request.post("/api/auth/login", {
    data: { identifier, password: "a123456789!" },
  });
  expect(result.status()).toBe(200);
  return { Authorization: `Bearer ${(await result.json()).access_token}` };
}

export const test = base.extend<{ databaseAccounts: void }>({
  databaseAccounts: [async ({ request }, use) => {
    const auth = process.env.E2E_AUTH_URL;
    if (!auth) throw new Error("Run scripts/e2e.sh with isolated DB/Auth fixtures.");
    const reset = await request.post(auth + "/reset", {
      headers: { Authorization: "Bearer e2e-service-role" },
    });
    expect(reset.status()).toBe(200);
    Object.assign(headers, await loginHeaders(request, "admin"));
    await use();
  }, { auto: true }],
});
export { expect };
