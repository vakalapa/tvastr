import { useParams } from "react-router-dom";
import { useState } from "react";
import { useAgent, useIterations } from "../api/queries";
import { useWebSocket } from "../hooks/useWebSocket";
import { AgentState, WSEventType } from "../api/types";
import type { IterationOut, WSMessage } from "../api/types";

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

function outcomeBadge(outcome: string) {
  const colors: Record<string, string> = {
    advanced: "text-green-400",
    reverted: "text-red-400",
    no_changes: "text-yellow-400",
    partial: "text-orange-400",
  };
  return (
    <span className={`text-xs font-medium ${colors[outcome] ?? "text-gray-400"}`}>
      {outcome}
    </span>
  );
}

function IterationCard({ iteration }: { iteration: IterationOut }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-3 flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-gray-400">
            #{iteration.iteration_num}
          </span>
          {outcomeBadge(iteration.outcome)}
          <span className="text-sm text-gray-300 truncate max-w-md">
            {iteration.hypothesis.slice(0, 100)}
          </span>
        </div>
        <span className="text-gray-500 text-xs">
          {expanded ? "collapse" : "expand"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-gray-700 p-3 space-y-2">
          <div>
            <p className="text-xs text-gray-500 mb-1">Hypothesis</p>
            <p className="text-sm text-gray-300">{iteration.hypothesis}</p>
          </div>
          {iteration.files_changed.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Files Changed</p>
              <ul className="text-sm font-mono text-gray-400">
                {iteration.files_changed.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <p className="text-xs text-gray-500 mb-1">Lesson</p>
            <p className="text-sm text-gray-300">{iteration.lesson}</p>
          </div>
          {iteration.validate_results && iteration.validate_results.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Validation Results</p>
              {iteration.validate_results.map((vr) => (
                <div
                  key={vr.name}
                  className={`text-sm ${vr.status === "pass" ? "text-green-400" : "text-red-400"}`}
                >
                  {vr.name}: {vr.status} ({vr.duration_secs.toFixed(1)}s)
                </div>
              ))}
            </div>
          )}
          <div className="text-xs text-gray-600">
            SHA: {iteration.patch_sha || "n/a"} &middot;{" "}
            {new Date(iteration.created_at).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}

function AgentStream() {
  const { runId, agentId } = useParams<{ runId: string; agentId: string }>();

  const { data: agent, isLoading: agentLoading, error: agentError } = useAgent(
    runId ?? "",
    agentId ?? "",
  );
  const { data: iterations } = useIterations(runId ?? "", agentId ?? "");

  // WebSocket for live output
  const wsUrl =
    runId && agentId
      ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/runs/${runId}/agents/${agentId}`
      : null;
  const { messages, connected, error: wsError } = useWebSocket(wsUrl);

  // Filter agent output messages
  const outputMessages = messages.filter(
    (m: WSMessage) => m.event === WSEventType.AGENT_OUTPUT,
  );

  if (agentLoading) {
    return <div className="text-gray-400" data-testid="loading">Loading agent...</div>;
  }

  if (agentError) {
    return (
      <div className="text-red-400" data-testid="error">
        Failed to load agent: {agentError instanceof Error ? agentError.message : "Unknown error"}
      </div>
    );
  }

  if (!agent) {
    return <div className="text-gray-400">Agent not found.</div>;
  }

  return (
    <div>
      {/* Agent info header */}
      <div className="mb-6" data-testid="agent-header">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-2xl font-bold">{agent.agent_id}</h1>
          {agentStateBadge(agent.state)}
        </div>
        <p className="text-sm text-gray-400 mb-1">
          Branch: <span className="font-mono">{agent.branch_name}</span>
        </p>
        <p className="text-sm text-gray-300">{agent.sub_objective_desc}</p>
      </div>

      {/* Live output stream */}
      <section className="mb-6">
        <div className="flex items-center gap-2 mb-2">
          <h2 className="text-lg font-semibold">Live Output</h2>
          <span
            className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-red-400"}`}
            title={connected ? "Connected" : "Disconnected"}
          />
          {wsError && <span className="text-xs text-red-400">{wsError}</span>}
        </div>
        <div
          className="bg-gray-950 border border-gray-700 rounded-lg p-4 h-80 overflow-auto font-mono text-sm text-green-300"
          data-testid="live-output"
        >
          {outputMessages.length === 0 && (
            <p className="text-gray-600">Waiting for output...</p>
          )}
          {outputMessages.map((msg: WSMessage, i: number) => (
            <div key={i} className="whitespace-pre-wrap">
              {String(msg.data)}
            </div>
          ))}
        </div>
      </section>

      {/* Iteration history */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Iteration History</h2>
        {iterations && iterations.length > 0 ? (
          <div className="space-y-2" data-testid="iteration-list">
            {iterations.map((it: IterationOut) => (
              <IterationCard key={it.id} iteration={it} />
            ))}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No iterations yet.</p>
        )}
      </section>
    </div>
  );
}

export default AgentStream;
