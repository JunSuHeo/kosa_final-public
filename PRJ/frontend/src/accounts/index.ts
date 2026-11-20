import browser from "./browser";
import server from "./server";
export let accountService = browser;
export function configureAccountService(mode: string) {
  accountService = mode === "mock" ? browser : server;
}
export * from "./types";
