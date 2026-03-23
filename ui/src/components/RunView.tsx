import { useParams, useNavigate } from "react-router-dom";
import { useRun, useAgents, useObjectives } from "../api/queries";
import { RunState, AgentState, SubObjectiveStatus } from "../api/types";
import type { AgentOut, SubObjectiveOut, MergeResultOut } from "../api/types";

function runStateBadge(state: RunState) {
  const colors: Record<RunState, string> = {
    [RunState.PENDING]: "bg-yellow-600",
    [RunState.RUNNING]: "bg-blue-600",
    [RunState.MERGING]: "bg-purple-600",
    [RunState.DONE]: "bg-green-600",
    [RunState.FAILED]: "bg-red-600",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[state] ?? "bg-gray-600"}`}
    >
      {state}
    </span>
  );
}

function agentStateBadge(state: AgentState) {
  const colors: Record<AgentState, string> = {
    [AgentState.IDLE]: "bg-gray-600",
    [AgentState.DISCOVERING]: "bg-cyan-600",
    [AgentState.PLANNING]: "bg-yellow-600",
    [AgentState.PATCHING]: "bg-blue-600",
    [AgentState.VALIDATING]: "bg-purple-600",
    [AgentState.DONE]: "bg-green-600",
    [AgentState.FAILED]: "bg-red-600",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[state] ?? "bg-gray-600"}`}
    >
      {state}
    </span>
  );
}

function objectiveStatusBadge(status: SubObjectiveStatus) {
  const colors: Record<SubObjectiveStatus, string> = {
    [SubObjectiveStatus.PENDING]: "bg-gray-600",
    [SubObjectiveStatus.IN_PROGRESS]: "bg-blue-600",
    [SubObjectiveStatus.DONE]: "bg-green-600",
    [SubObjectiveStatus.BLOCKED]: "bg-red-600",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${colors[status] ?? "bg-gray-600"}`}
    >
      {status}
    </span>
  );
}

function RunView() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const { data: run, isLoading: runLoading, error: runError } = useRun(runId ?? "");
  const { data: agents, isLoading: agentsLoading } = useAgents(runId ?? "");
  const { data: objectives } = useObjectives(runId ?? "");

  if (runLoading || agentsLoading) {
    return <div className="text-gray-400" data-testid="loading">Loading run details...</div>;
  }

  if (runError) {
    return (
      <div className="text-red-400" data-testid="error">
        Failed to load run: {runError instanceof Error ? runError.message : "Unknown error"}
      </div>
    );
  }

  if (!run) {
    return <div className="text-gray-400">Run not found.</div>;
  }

  // Placeholder: merge results would come from the run or a separate query
  const mergeResults: MergeResultOut[] = [];

  return (
    <div>
      {/* Header */}
      <div className="mb-6" data-testid="run-header">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold">{run.run_id}</h1>
          {runStateBadge(run.state)}
        </div>
        <p className="text-gray-400 text-sm mb-1">
          {run.repo_path} &middot; {run.model} &middot; {run.strategy}
        </p>
        <p className="text-gray-300">{run.objective}</p>
      </div>

      {/* Sub-objectives */}
      {objectives && objectives.length > 0 && (
        <section className="mb-6" data-testid="objectives-section">
          <h2 className="text-lg font-semibold mb-3">Sub-Objectives</h2>
          <div className="space-y-2">
            {objectives.map((obj: SubObjectiveOut) => (
              <div
                key={obj.id}
                className="bg-gray-800 border border-gray-700 rounded p-3 flex items-center justify-between"
              >
                <div>
                  <p className="text-sm">{obj.description}</p>
                  {obj.assigned_agent && (
                    <p className="text-xs text-gray-500 mt-1">
                      Assigned: {obj.assigned_agent}
                    </p>
                  )}
                </div>
                {objectiveStatusBadge(obj.status)}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Agents grid */}
      {agents && agents.length > 0 && (
        <section className="mb-6" data-testid="agents-section">
          <h2 className="text-lg font-semibold mb-3">Agents</h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent: AgentOut) => (
              <button
                key={agent.agent_id}
                onClick={() =>
                  navigate(`/runs/${runId}/agents/${agent.agent_id}`)
                }
                className="text-left bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-purple-500 transition-colors"
                data-testid="agent-card"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-sm">{agent.agent_id}</span>
                  {agentStateBadge(agent.state)}
                </div>
                <p className="text-xs text-gray-400 truncate mb-1">
                  {agent.sub_objective_desc}
                </p>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>{agent.iteration_count} iterations</span>
                  <span className="font-mono">{agent.branch_name}</span>
                </div>
                {agent.error && (
                  <p className="text-xs text-red-400 mt-1 truncate">
                    {agent.error}
                  </p>
                )}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Merge results */}
      {mergeResults.length > 0 && (
        <section className="mb-6" data-testid="merge-section">
          <h2 className="text-lg font-semibold mb-3">Merge Results</h2>
          <div className="space-y-2">
            {mergeResults.map((mr: MergeResultOut) => (
              <div
                key={mr.branch}
                className="bg-gray-800 border border-gray-700 rounded p-3 flex items-center justify-between"
              >
                <span className="font-mono text-sm">{mr.branch}</span>
                <span
                  className={`text-xs font-medium ${mr.success ? "text-green-400" : "text-red-400"}`}
                >
                  {mr.success ? "Merged" : "Failed"}
                  {mr.validation_passed === false && " (validation failed)"}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Placeholder: PatchViewer component will be created by Agent 4 */}
      {/* Placeholder: Controls component will be created by Agent 4 */}
      {/* Placeholder: TestResults component will be created by Agent 4 */}
      {/* Placeholder: Journal component will be created by Agent 4 */}
    </div>
  );
}

export default RunView;
