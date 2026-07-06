import { describe, expect, it, vi } from "vitest";
import {
  deviceToken,
  getErrorMessage,
  ifcDownloadUrl,
  isCancelError,
  pdfReportUrl,
  shareUrl,
} from "./client";

// Environment-independent localStorage stub (the jsdom global lacks methods
// under this vitest version) — same pattern as useStore.test.ts.
const backing = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => backing.get(k) ?? null,
  setItem: (k: string, v: string) => void backing.set(k, v),
  removeItem: (k: string) => void backing.delete(k),
});

describe("deviceToken", () => {
  it("mints a uuid once and returns the same token afterwards", () => {
    backing.clear();
    const first = deviceToken();
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(deviceToken()).toBe(first);
    expect(backing.get("archvision_device_v1")).toBe(first);
  });
});

describe("shareUrl", () => {
  it("builds a hash-routed link on the current origin", () => {
    expect(shareUrl("abc")).toBe(`${location.origin}${location.pathname}#/p/abc`);
  });
});

describe("pdfReportUrl", () => {
  it("passes supported languages through", () => {
    expect(pdfReportUrl("abc", "ru")).toBe("/api/v1/report/abc?lang=ru");
    expect(pdfReportUrl("abc", "kk")).toBe("/api/v1/report/abc?lang=kk");
  });

  it("normalizes BCP-47 regional tags", () => {
    expect(pdfReportUrl("abc", "en-US")).toBe("/api/v1/report/abc?lang=en");
    expect(pdfReportUrl("abc", "ru-RU")).toBe("/api/v1/report/abc?lang=ru");
  });

  it("falls back to en for missing or unsupported languages", () => {
    expect(pdfReportUrl("abc")).toBe("/api/v1/report/abc?lang=en");
    expect(pdfReportUrl("abc", "de")).toBe("/api/v1/report/abc?lang=en");
  });
});

describe("ifcDownloadUrl", () => {
  it("builds the download path", () => {
    expect(ifcDownloadUrl("xyz")).toBe("/api/v1/download/xyz");
  });
});

describe("isCancelError", () => {
  it("recognizes DOMException AbortError (abortable sleep)", () => {
    expect(isCancelError(new DOMException("Aborted", "AbortError"))).toBe(true);
  });

  it("rejects ordinary errors", () => {
    expect(isCancelError(new Error("boom"))).toBe(false);
    expect(isCancelError(null)).toBe(false);
    expect(isCancelError(undefined)).toBe(false);
  });
});

describe("getErrorMessage", () => {
  it("extracts Error messages", () => {
    expect(getErrorMessage(new Error("boom"))).toBe("boom");
  });

  it("returns the fallback for unknown values", () => {
    expect(getErrorMessage(null, "fallback")).toBe("fallback");
    expect(getErrorMessage({}, "fallback")).toBe("fallback");
  });
});
