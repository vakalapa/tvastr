import { useState } from 'react';
import { usePauseRun, useResumeRun, useCancelRun, useKillAgent } from '../api/mutations';
import type { RunState } from '../api/types';

export interface ControlsProps {
  runId: string;
  runState: RunState;
  agentIds?: string[];
}

function Spinner() {
  return (
    <div className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-white" />
  );
}

function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" data-testid="confirm-dialog">
      <div className="rounded-lg border border-gray-600 bg-gray-800 p-6 shadow-xl max-w-sm w-full mx-4">
        <p className="text-sm text-gray-200 mb-4">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded bg-gray-600 px-4 py-2 text-sm text-gray-200 hover:bg-gray-500 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-500 transition-colors"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}

function Toast({ message, variant }: { message: string; variant: 'success' | 'error' }) {
  const bg = variant === 'success' ? 'bg-green-800 border-green-600' : 'bg-red-800 border-red-600';
  return (
    <div className={`fixed bottom-4 right-4 z-50 rounded border ${bg} px-4 py-2 text-sm text-white shadow-lg`} data-testid="toast">
      {message}
    </div>
  );
}

const STATE_LABELS: Record<RunState, { label: string; color: string }> = {
  pending: { label: 'Pending', color: 'text-gray-400' },
  running: { label: 'Running', color: 'text-blue-400' },
  paused: { label: 'Paused', color: 'text-yellow-400' },
  completed: { label: 'Completed', color: 'text-green-400' },
  failed: { label: 'Failed', color: 'text-red-400' },
  cancelled: { label: 'Cancelled', color: 'text-gray-400' },
};

export default function Controls({ runId, runState, agentIds = [] }: ControlsProps) {
  const pauseRun = usePauseRun();
  const resumeRun = useResumeRun();
  const cancelRun = useCancelRun();
  const killAgent = useKillAgent();

  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [toast, setToast] = useState<{ message: string; variant: 'success' | 'error' } | null>(null);

  const showToast = (message: string, variant: 'success' | 'error') => {
    setToast({ message, variant });
    setTimeout(() => setToast(null), 3000);
  };

  const handlePause = () => {
    pauseRun.mutate(runId, {
      onSuccess: () => showToast('Run paused', 'success'),
      onError: (err) => showToast(`Pause failed: ${(err as Error).message}`, 'error'),
    });
  };

  const handleResume = () => {
    resumeRun.mutate(runId, {
      onSuccess: () => showToast('Run resumed', 'success'),
      onError: (err) => showToast(`Resume failed: ${(err as Error).message}`, 'error'),
    });
  };

  const handleCancel = () => {
    setShowCancelConfirm(true);
  };

  const confirmCancel = () => {
    setShowCancelConfirm(false);
    cancelRun.mutate(runId, {
      onSuccess: () => showToast('Run cancelled', 'success'),
      onError: (err) => showToast(`Cancel failed: ${(err as Error).message}`, 'error'),
    });
  };

  const handleKillAgent = () => {
    if (!selectedAgent) return;
    killAgent.mutate(
      { runId, agentId: selectedAgent },
      {
        onSuccess: () => showToast(`Agent ${selectedAgent} killed`, 'success'),
        onError: (err) => showToast(`Kill failed: ${(err as Error).message}`, 'error'),
      },
    );
  };

  const isActive = runState === 'running' || runState === 'paused';
  const stateInfo = STATE_LABELS[runState];
  const anyLoading = pauseRun.isPending || resumeRun.isPending || cancelRun.isPending || killAgent.isPending;

  return (
    <div className="space-y-4">
      {/* Status */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-gray-400">Status:</span>
        <span className={`text-sm font-medium ${stateInfo.color}`}>{stateInfo.label}</span>
      </div>

      {/* Action buttons */}
      {isActive && (
        <div className="flex flex-wrap gap-2">
          {runState === 'running' && (
            <button
              type="button"
              onClick={handlePause}
              disabled={anyLoading}
              className="flex items-center gap-2 rounded bg-yellow-600 px-4 py-2 text-sm font-medium text-white hover:bg-yellow-500 disabled:opacity-50 transition-colors"
            >
              {pauseRun.isPending && <Spinner />}
              Pause
            </button>
          )}
          {runState === 'paused' && (
            <button
              type="button"
              onClick={handleResume}
              disabled={anyLoading}
              className="flex items-center gap-2 rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-50 transition-colors"
            >
              {resumeRun.isPending && <Spinner />}
              Resume
            </button>
          )}
          <button
            type="button"
            onClick={handleCancel}
            disabled={anyLoading}
            className="flex items-center gap-2 rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50 transition-colors"
          >
            {cancelRun.isPending && <Spinner />}
            Cancel Run
          </button>
        </div>
      )}

      {!isActive && (
        <p className="text-sm text-gray-500 italic" data-testid="no-actions">
          No actions available for {runState} runs.
        </p>
      )}

      {/* Kill agent */}
      {isActive && agentIds.length > 0 && (
        <div className="rounded border border-gray-700 bg-gray-800 p-3 space-y-2">
          <span className="text-xs font-medium text-gray-400 uppercase">Kill Agent</span>
          <div className="flex gap-2">
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="flex-1 rounded border border-gray-600 bg-gray-900 px-3 py-1.5 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
            >
              <option value="">Select agent...</option>
              {agentIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleKillAgent}
              disabled={!selectedAgent || anyLoading}
              className="flex items-center gap-2 rounded bg-red-700 px-3 py-1.5 text-sm text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
            >
              {killAgent.isPending && <Spinner />}
              Kill
            </button>
          </div>
        </div>
      )}

      {/* Confirmation dialog */}
      {showCancelConfirm && (
        <ConfirmDialog
          message="Are you sure you want to cancel this run? This action cannot be undone."
          onConfirm={confirmCancel}
          onCancel={() => setShowCancelConfirm(false)}
        />
      )}

      {/* Toast */}
      {toast && <Toast message={toast.message} variant={toast.variant} />}
    </div>
  );
}
