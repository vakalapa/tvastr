import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RunView from "../RunView";
import * as queries from "../../api/queries";
import { RunState, AgentState, SubObjectiveStatus } from "../../api/types";
import type { RunOut, AgentOut, SubObjectiveOut } from "../../api/types";

vi.mock("../../api/queries", () => ({
  useRun: vi.fn(),
  useAgents: vi.fn(),
  useObjectives: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderWithProviders(runId = "run-abc") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/runs/${runId}`]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const mockRun: RunOut = {
  run_id: "run-abc",
  repo_path: "/home/user/myrepo",
  objective: "Fix all the bugs in the codebase",
  state: RunState.RUNNING,
  strategy: "isolated",
  parallel: false,
  max_iterations_per_agent: 50,
  max_concurrent_agents: 3,
  model: "claude-sonnet-4-20250514",
  agent_count: 2,
  created_at: "2024-07-01T10:00:00Z",
  finished_at: null,
};

const mockAgents: AgentOut[] = [
  {
    agent_id: "agent-0",
    run_id: "run-abc",
    sub_objective_id: 1,
    sub_objective_desc: "Fix authentication bugs",
    branch_name: "tvastr/agent-0",
    state: AgentState.PATCHING,
    iteration_count: 3,
    result: null,
    error: null,
  },
  {
    agent_id: "agent-1",
    run_id: "run-abc",
    sub_objective_id: 2,
    sub_objective_desc: "Fix database bugs",
    branch_name: "tvastr/agent-1",
    state: AgentState.VALIDATING,
    iteration_count: 5,
    result: null,
    error: null,
  },
];

const mockObjectives: SubObjectiveOut[] = [
  {
    id: 1,
    description: "Fix authentication bugs",
    status: SubObjectiveStatus.IN_PROGRESS,
    assigned_agent: "agent-0",
    priority: 1,
    depends_on: [],
    created_at: "2024-07-01T10:00:00Z",
    completed_at: null,
  },
  {
    id: 2,
    description: "Fix database bugs",
    status: SubObjectiveStatus.IN_PROGRESS,
    assigned_agent: "agent-1",
    priority: 0,
    depends_on: [1],
    created_at: "2024-07-01T10:00:00Z",
    completed_at: null,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RunView", () => {
  it("renders loading state", () => {
    vi.mocked(queries.useRun).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof queries.useRun>);
    vi.mocked(queries.useAgents).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof queries.useAgents>);
    vi.mocked(queries.useObjectives).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useObjectives>);

    renderWithProviders();
    expect(screen.getByTestId("loading")).toHaveTextContent("Loading run details...");
  });

  it("renders run header with state badge", () => {
    vi.mocked(queries.useRun).mockReturnValue({
      data: mockRun,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRun>);
    vi.mocked(queries.useAgents).mockReturnValue({
      data: mockAgents,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useAgents>);
    vi.mocked(queries.useObjectives).mockReturnValue({
      data: mockObjectives,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useObjectives>);

    renderWithProviders();
    expect(screen.getByTestId("run-header")).toBeInTheDocument();
    expect(screen.getByText("run-abc")).toBeInTheDocument();
    expect(screen.getByText("running")).toBeInTheDocument();
    expect(screen.getByText("Fix all the bugs in the codebase")).toBeInTheDocument();
  });

  it("renders agents grid", () => {
    vi.mocked(queries.useRun).mockReturnValue({
      data: mockRun,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRun>);
    vi.mocked(queries.useAgents).mockReturnValue({
      data: mockAgents,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useAgents>);
    vi.mocked(queries.useObjectives).mockReturnValue({
      data: mockObjectives,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useObjectives>);

    renderWithProviders();
    expect(screen.getByTestId("agents-section")).toBeInTheDocument();
    const agentCards = screen.getAllByTestId("agent-card");
    expect(agentCards).toHaveLength(2);
    expect(screen.getByText("agent-0")).toBeInTheDocument();
    expect(screen.getByText("agent-1")).toBeInTheDocument();
  });

  it("renders sub-objectives", () => {
    vi.mocked(queries.useRun).mockReturnValue({
      data: mockRun,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRun>);
    vi.mocked(queries.useAgents).mockReturnValue({
      data: mockAgents,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useAgents>);
    vi.mocked(queries.useObjectives).mockReturnValue({
      data: mockObjectives,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useObjectives>);

    renderWithProviders();
    expect(screen.getByTestId("objectives-section")).toBeInTheDocument();
    // Text appears in both objectives section and agent cards
    expect(screen.getAllByText("Fix authentication bugs").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Fix database bugs").length).toBeGreaterThanOrEqual(1);
  });

  it("navigates to agent detail on click", () => {
    vi.mocked(queries.useRun).mockReturnValue({
      data: mockRun,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useRun>);
    vi.mocked(queries.useAgents).mockReturnValue({
      data: mockAgents,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useAgents>);
    vi.mocked(queries.useObjectives).mockReturnValue({
      data: mockObjectives,
      isLoading: false,
      error: null,
    } as ReturnType<typeof queries.useObjectives>);

    renderWithProviders();
    const agentCards = screen.getAllByTestId("agent-card");
    fireEvent.click(agentCards[0]);
    expect(mockNavigate).toHaveBeenCalledWith("/runs/run-abc/agents/agent-0");
  });
});
