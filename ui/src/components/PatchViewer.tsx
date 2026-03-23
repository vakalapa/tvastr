import { useState } from 'react';
import { useIterations } from '../api/queries';
import type { IterationOut } from '../api/types';

export interface PatchViewerProps {
  runId: string;
  agentId: string;
  iterationId?: number;
}

function FileBadge({ path }: { path: string }) {
  const parts = path.split('/');
  const filename = parts.pop() ?? path;
  const dir = parts.join('/');
  return (
    <span className="inline-flex items-center gap-1 rounded bg-gray-700 px-2 py-0.5 text-xs font-mono text-gray-200">
      {dir && <span className="text-gray-400">{dir}/</span>}
      <span>{filename}</span>
    </span>
  );
}

function IterationSection({ iteration }: { iteration: IterationOut }) {
  const [expanded, setExpanded] = useState(false);
  const hasFiles = iteration.files_changed.length > 0;

  return (
    <div className="rounded border border-gray-700 bg-gray-800">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-gray-750 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-100">
            Iteration #{iteration.iteration_num}
          </span>
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              iteration.outcome === 'advanced'
                ? 'bg-green-900/50 text-green-300'
                : iteration.outcome === 'reverted'
                  ? 'bg-red-900/50 text-red-300'
                  : 'bg-yellow-900/50 text-yellow-300'
            }`}
          >
            {iteration.outcome}
          </span>
          <span className="text-xs text-gray-400">
            {hasFiles ? `${iteration.files_changed.length} file(s)` : 'no files'}
          </span>
        </div>
        <svg
          className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-gray-700 px-4 py-3 space-y-3">
          {iteration.hypothesis && (
            <div>
              <span className="text-xs font-medium text-gray-400">Hypothesis</span>
              <p className="mt-1 text-sm text-gray-200">{iteration.hypothesis}</p>
            </div>
          )}

          {hasFiles ? (
            <div>
              <span className="text-xs font-medium text-gray-400">Files Changed</span>
              <div className="mt-2 space-y-1">
                {iteration.files_changed.map((file) => (
                  <div
                    key={file}
                    className="flex items-center justify-between rounded bg-gray-900 px-3 py-2 font-mono text-sm"
                  >
                    <span className="text-gray-200">{file}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">No files changed in this iteration.</p>
          )}

          {iteration.patch_sha && (
            <div>
              <span className="text-xs font-medium text-gray-400">Patch SHA</span>
              <code className="ml-2 rounded bg-gray-900 px-2 py-0.5 text-xs text-blue-300 font-mono" data-testid="patch-sha">
                {iteration.patch_sha}
              </code>
            </div>
          )}

          {iteration.lesson && (
            <div>
              <span className="text-xs font-medium text-gray-400">Lesson</span>
              <p className="mt-1 text-sm text-gray-300">{iteration.lesson}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PatchViewer({ runId, agentId, iterationId }: PatchViewerProps) {
  const { data: iterations, isLoading, error } = useIterations(runId, agentId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-400 border-t-blue-400" />
        <span className="ml-3 text-sm text-gray-400">Loading patches...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-300">
        Failed to load iteration data: {(error as Error).message}
      </div>
    );
  }

  const filtered = iterationId
    ? (iterations ?? []).filter((it) => it.id === iterationId)
    : (iterations ?? []);

  if (filtered.length === 0) {
    return (
      <div className="rounded border border-gray-700 bg-gray-800 px-4 py-8 text-center text-sm text-gray-400">
        No iterations found for this agent.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-200">
          Patches &mdash; Agent {agentId}
        </h3>
        <div className="flex flex-wrap gap-1">
          {filtered
            .flatMap((it) => it.files_changed)
            .filter((v, i, a) => a.indexOf(v) === i)
            .slice(0, 8)
            .map((f) => (
              <FileBadge key={f} path={f} />
            ))}
        </div>
      </div>

      <div className="space-y-2">
        {filtered.map((it) => (
          <IterationSection key={it.id} iteration={it} />
        ))}
      </div>
    </div>
  );
}
