import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWebSocket } from "../useWebSocket";
import type { WSMessage } from "../../api/types";

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  simulateOpen() {
    this.onopen?.();
  }

  simulateMessage(data: WSMessage) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  simulateClose() {
    this.onclose?.();
  }

  simulateError() {
    this.onerror?.();
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useWebSocket", () => {
  it("connects to the given URL", () => {
    renderHook(() => useWebSocket("ws://localhost:8000/ws/test"));
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toBe("ws://localhost:8000/ws/test");
  });

  it("sets connected=true on open", () => {
    const { result } = renderHook(() =>
      useWebSocket("ws://localhost:8000/ws/test"),
    );
    expect(result.current.connected).toBe(false);

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });
    expect(result.current.connected).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("parses incoming JSON messages", () => {
    const { result } = renderHook(() =>
      useWebSocket("ws://localhost:8000/ws/test"),
    );

    act(() => {
      MockWebSocket.instances[0].simulateOpen();
    });

    const msg: WSMessage = {
      event: "agent_output" as WSMessage["event"],
      run_id: "run-1",
      agent_id: "agent-0",
      data: "hello world",
      timestamp: "2024-01-01T00:00:00Z",
    };

    act(() => {
      MockWebSocket.instances[0].simulateMessage(msg);
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].data).toBe("hello world");
  });

  it("attempts reconnect on close with exponential backoff", () => {
    renderHook(() => useWebSocket("ws://localhost:8000/ws/test"));
    expect(MockWebSocket.instances).toHaveLength(1);

    act(() => {
      MockWebSocket.instances[0].simulateClose();
    });

    // First reconnect at 1000ms
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);

    // Close again, next reconnect at 2000ms
    act(() => {
      MockWebSocket.instances[1].simulateClose();
    });
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(MockWebSocket.instances).toHaveLength(2); // not yet
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it("does not connect when url is null", () => {
    renderHook(() => useWebSocket(null));
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("cleans up on unmount", () => {
    const { unmount } = renderHook(() =>
      useWebSocket("ws://localhost:8000/ws/test"),
    );
    const ws = MockWebSocket.instances[0];

    unmount();
    expect(ws.close).toHaveBeenCalled();
  });
});
