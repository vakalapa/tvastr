import { useState } from 'react';
import type { ValidationResultOut } from '../api/types';

export interface TestResultsProps {
  results: ValidationResultOut[];
}

type StatusFilter = 'all' | 'pass' | 'fail' | 'error';

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  pass: { label: 'Passed', bg: 'bg-green-900/50', text: 'text-green-300' },
  fail: { label: 'Failed', bg: 'bg-red-900/50', text: 'text-red-300' },
  error: { label: 'Error', bg: 'bg-yellow-900/50', text: 'text-yellow-300' },
  skip: { label: 'Skipped', bg: 'bg-gray-700', text: 'text-gray-400' },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, bg: 'bg-gray-700', text: 'text-gray-400' };
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  );
}

function TestRow({ result }: { result: ValidationResultOut }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded border border-gray-700 bg-gray-800">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-gray-750 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <StatusBadge status={result.status} />
          <span className="truncate text-sm text-gray-100">{result.name}</span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-gray-400">
            {result.duration_secs.toFixed(2)}s
          </span>
          <svg
            className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-700 px-4 py-3 space-y-2">
          {result.output && (
            <pre className="max-h-64 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-300 font-mono whitespace-pre-wrap">
              {result.output}
            </pre>
          )}
          {result.failed_tests && result.failed_tests.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-400">Failed tests:</span>
              <ul className="mt-1 list-disc list-inside text-xs text-red-300">
                {result.failed_tests.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function TestResults({ results }: TestResultsProps) {
  const [filter, setFilter] = useState<StatusFilter>('all');

  const counts = {
    pass: results.filter((r) => r.status === 'pass').length,
    fail: results.filter((r) => r.status === 'fail').length,
    error: results.filter((r) => r.status === 'error').length,
  };

  const filtered =
    filter === 'all' ? results : results.filter((r) => r.status === filter);

  if (results.length === 0) {
    return (
      <div className="rounded border border-gray-700 bg-gray-800 px-4 py-8 text-center text-sm text-gray-400">
        No test results available.
      </div>
    );
  }

  const filterButtons: { key: StatusFilter; label: string }[] = [
    { key: 'all', label: `All (${results.length})` },
    { key: 'pass', label: `Passed (${counts.pass})` },
    { key: 'fail', label: `Failed (${counts.fail})` },
    { key: 'error', label: `Errors (${counts.error})` },
  ];

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex items-center gap-4 rounded bg-gray-800 px-4 py-2.5" data-testid="summary-bar">
        <span className="text-sm text-gray-200 font-medium">
          {results.length} test{results.length !== 1 ? 's' : ''}
        </span>
        <span className="text-sm text-green-400">{counts.pass} passed</span>
        <span className="text-sm text-red-400">{counts.fail} failed</span>
        <span className="text-sm text-yellow-400">{counts.error} errors</span>
      </div>

      {/* Filter buttons */}
      <div className="flex gap-2" role="group" aria-label="Filter tests">
        {filterButtons.map((btn) => (
          <button
            key={btn.key}
            type="button"
            onClick={() => setFilter(btn.key)}
            className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === btn.key
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {/* Test list */}
      <div className="space-y-2">
        {filtered.map((r) => (
          <TestRow key={r.name} result={r} />
        ))}
      </div>
    </div>
  );
}
