import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch, ApiError } from "../client";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
});

describe("apiFetch", () => {
  it("returns parsed JSON on success", async () => {
    const data = { run_id: "run-1", state: "running" };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(data),
    });

    const result = await apiFetch<typeof data>("/api/runs/run-1");
    expect(result).toEqual(data);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/runs/run-1",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      }),
    );
  });

  it("throws ApiError on 404", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ detail: "Not found" }),
    });

    await expect(apiFetch("/api/runs/nope")).rejects.toThrow(ApiError);
    await expect(apiFetch("/api/runs/nope")).rejects.toThrow("API error 404");
  });

  it("throws ApiError on 500 with text body", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
      text: () => Promise.resolve("server error"),
    });

    try {
      await apiFetch("/api/runs");
      expect.unreachable("Should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(500);
      expect(apiErr.body).toBe("server error");
    }
  });

  it("passes custom options through", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });

    await apiFetch("/api/runs", {
      method: "POST",
      body: JSON.stringify({ repo_path: "/tmp/repo" }),
    });

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/runs",
      expect.objectContaining({
        method: "POST",
        body: '{"repo_path":"/tmp/repo"}',
      }),
    );
  });
});
