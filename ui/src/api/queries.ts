import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { RunOut, IterationOut } from './types';

/** Fetch a single run by id */
export function useRun(runId: string) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => api.get<RunOut>(`/runs/${runId}`),
    enabled: !!runId,
  });
}

/** Fetch all runs */
export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: () => api.get<RunOut[]>('/runs'),
  });
}

/** Fetch iterations for a run, optionally filtered by agent */
export function useIterations(runId: string, agentId?: string) {
  return useQuery({
    queryKey: ['iterations', runId, agentId ?? 'all'],
    queryFn: () => {
      const path = agentId
        ? `/runs/${runId}/agents/${agentId}/iterations`
        : `/runs/${runId}/iterations`;
      return api.get<IterationOut[]>(path);
    },
    enabled: !!runId,
  });
}
