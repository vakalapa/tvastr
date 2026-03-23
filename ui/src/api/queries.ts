import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type {
  RunSummary,
  RunOut,
  AgentOut,
  IterationOut,
  SubObjectiveOut,
} from "./types";

export function useRuns() {
  return useQuery<RunSummary[]>({
    queryKey: ["runs"],
    queryFn: () => apiFetch<RunSummary[]>("/api/runs"),
  });
}

export function useRun(runId: string) {
  return useQuery<RunOut>({
    queryKey: ["run", runId],
    queryFn: () => apiFetch<RunOut>(`/api/runs/${runId}`),
    enabled: !!runId,
  });
}

export function useAgents(runId: string) {
  return useQuery<AgentOut[]>({
    queryKey: ["agents", runId],
    queryFn: () => apiFetch<AgentOut[]>(`/api/runs/${runId}/agents`),
    enabled: !!runId,
  });
}

export function useAgent(runId: string, agentId: string) {
  return useQuery<AgentOut>({
    queryKey: ["agent", runId, agentId],
    queryFn: () =>
      apiFetch<AgentOut>(`/api/runs/${runId}/agents/${agentId}`),
    enabled: !!runId && !!agentId,
  });
}

export function useIterations(runId: string, agentId: string) {
  return useQuery<IterationOut[]>({
    queryKey: ["iterations", runId, agentId],
    queryFn: () =>
      apiFetch<IterationOut[]>(
        `/api/runs/${runId}/agents/${agentId}/iterations`,
      ),
    enabled: !!runId && !!agentId,
  });
}

export function useObjectives(runId: string) {
  return useQuery<SubObjectiveOut[]>({
    queryKey: ["objectives", runId],
    queryFn: () =>
      apiFetch<SubObjectiveOut[]>(`/api/runs/${runId}/objectives`),
    enabled: !!runId,
  });
}
