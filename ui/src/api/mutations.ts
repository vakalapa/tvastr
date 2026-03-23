import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { RunOut, CreateRunIn } from './types';

/** Create a new forge run */
export function useCreateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateRunIn) => api.post<RunOut>('/runs', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

/** Pause a running run */
export function usePauseRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.post<void>(`/runs/${runId}/pause`),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: ['runs', runId] });
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

/** Resume a paused run */
export function useResumeRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.post<void>(`/runs/${runId}/resume`),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: ['runs', runId] });
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

/** Cancel a run */
export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.post<void>(`/runs/${runId}/cancel`),
    onSuccess: (_data, runId) => {
      qc.invalidateQueries({ queryKey: ['runs', runId] });
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

/** Kill a specific agent */
export function useKillAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, agentId }: { runId: string; agentId: string }) =>
      api.post<void>(`/runs/${runId}/agents/${agentId}/kill`),
    onSuccess: (_data, { runId }) => {
      qc.invalidateQueries({ queryKey: ['runs', runId] });
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}
