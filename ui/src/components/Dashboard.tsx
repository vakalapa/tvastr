import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRuns } from "../api/queries";
import { apiFetch } from "../api/client";
import type { RunCreateRequest, RunSummary, RunOut } from "../api/types";
import { RunState } from "../api/types";
import { useQueryClient } from "@tanstack/react-query";

function stateBadge(state: RunState) {
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

function NewRunForm({ onClose }: { onClose: () => void }) {
  const [repoPath, setRepoPath] = useState("");
  const [objective, setObjective] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: RunCreateRequest = { repo_path: repoPath, objective };
      const run = await apiFetch<RunOut>("/api/runs", {
        method: "POST",
        body: JSON.stringify(body),
      });
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create run");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mb-6 bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-lg font-semibold mb-3">New Run</h3>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Repository Path
          </label>
          <input
            type="text"
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-purple-500"
            placeholder="/path/to/repo"
            required
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Objective</label>
          <textarea
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-purple-500"
            rows={3}
            placeholder="Describe what the agents should accomplish..."
            required
          />
        </div>
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-sm font-medium disabled:opacity-50"
          >
            {submitting ? "Creating..." : "Create Run"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function Dashboard() {
  const { data: runs, isLoading, error } = useRuns();
  const [showForm, setShowForm] = useState(false);
  const navigate = useNavigate();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded text-sm font-medium"
        >
          New Run
        </button>
      </div>

      {showForm && <NewRunForm onClose={() => setShowForm(false)} />}

      {isLoading && (
        <div className="text-gray-400" data-testid="loading">
          Loading runs...
        </div>
      )}

      {error && (
        <div className="text-red-400" data-testid="error">
          Failed to load runs: {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {runs && runs.length === 0 && (
        <div className="text-gray-500">
          No runs yet. Create one to get started.
        </div>
      )}

      {runs && runs.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" data-testid="run-list">
          {runs.map((run: RunSummary) => (
            <button
              key={run.run_id}
              onClick={() => navigate(`/runs/${run.run_id}`)}
              className="text-left bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-purple-500 transition-colors"
              data-testid="run-card"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-mono text-gray-400">
                  {run.run_id}
                </span>
                {stateBadge(run.state)}
              </div>
              <p className="text-sm text-gray-300 truncate mb-2">
                {run.repo_path}
              </p>
              <p className="text-sm text-gray-400 truncate mb-2">
                {run.objective}
              </p>
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>{run.agent_count} agent(s)</span>
                <span>{new Date(run.created_at).toLocaleString()}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default Dashboard;
