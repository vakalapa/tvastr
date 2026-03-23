import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dashboard from "../Dashboard";
import * as queries from "../../api/queries";
import { RunState } from "../../api/types";
import type { RunSummary } from "../../api/types";

// Mock useRuns
vi.mock("../../api/queries", () => ({
  useRuns: vi.fn(),
}));

// Mock navigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const mockRuns: RunSummary[] = [
  {
    run_id: "run-abc",
    repo_path: "/home/user/myrepo",
    objective: "Fix all the bugs",
    state: RunState.RUNNING,
    agent_count: 3,
    created_at: "2024-07-01T10:00:00Z",
  },
  {
    run_id: "run-def",
    repo_path: "/home/user/other",
    objective: "Add feature X",
    state: RunState.DONE,
    agent_count: 1,
    created_at: "2024-07-02T12:00:00Z",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Dashboard", () => {
  it("renders loading state", () => {
    vi.mocked(queries.useRuns).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof queries.useRuns>);

    renderWithProviders(<Dashboard />);
    expect(screen.getByTestId("loading")).toHaveTextContent("Loading runs...");
  });

  it("renders error state", () => {
    vi.mocked(queries.useRuns).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Network fail"),
    } as ReturnType<typeof queries.useRuns>);

    renderWithProviders(<Dashboard />);
    expect(screen.getByTestId("error")).toHaveTextContent("Network fail");
  });

  it("renders run list", () => {
    vi.mocked(queries.useRuns).mockReturnValue({
      data: mockRuns,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRuns>);

    renderWithProviders(<Dashboard />);
    expect(screen.getByTestId("run-list")).toBeInTheDocument();
    const cards = screen.getAllByTestId("run-card");
    expect(cards).toHaveLength(2);
    expect(screen.getByText("run-abc")).toBeInTheDocument();
    expect(screen.getByText("run-def")).toBeInTheDocument();
  });

  it("navigates to run detail on click", () => {
    vi.mocked(queries.useRuns).mockReturnValue({
      data: mockRuns,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRuns>);

    renderWithProviders(<Dashboard />);
    const cards = screen.getAllByTestId("run-card");
    fireEvent.click(cards[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/runs/run-abc");
  });

  it("shows New Run button", () => {
    vi.mocked(queries.useRuns).mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRuns>);

    renderWithProviders(<Dashboard />);
    expect(screen.getByText("New Run")).toBeInTheDocument();
  });
});
