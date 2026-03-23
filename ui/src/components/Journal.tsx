import { Fragment, useState, useMemo } from 'react';
import { useIterations } from '../api/queries';
import type { IterationOut, ValidationResultOut } from '../api/types';

export interface JournalProps {
  runId: string;
}

const OUTCOME_STYLE: Record<string, string> = {
  advanced: 'bg-green-900/50 text-green-300',
  reverted: 'bg-red-900/50 text-red-300',
  no_changes: 'bg-yellow-900/50 text-yellow-300',
};

const PAGE_SIZE = 20;

type SortKey = 'id' | 'agent_id' | 'iteration_num' | 'outcome' | 'hypothesis' | 'lesson' | 'created_at';
type SortDir = 'asc' | 'desc';

function compare(a: IterationOut, b: IterationOut, key: SortKey): number {
  const av = a[key];
  const bv = b[key];
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === 'number' && typeof bv === 'number') return av - bv;
  return String(av).localeCompare(String(bv));
}

function MiniTestSummary({ results }: { results: ValidationResultOut[] }) {
  const passed = results.filter((r) => r.status === 'pass').length;
  const failed = results.filter((r) => r.status === 'fail').length;
  return (
    <span className="text-xs text-gray-400">
      <span className="text-green-400">{passed}P</span>{' / '}
      <span className="text-red-400">{failed}F</span>{' / '}
      {results.length} total
    </span>
  );
}

function ExpandedRow({ iteration }: { iteration: IterationOut }) {
  return (
    <tr>
      <td colSpan={7} className="px-4 py-3 bg-gray-850 border-t border-gray-700">
        <div className="space-y-3">
          <div>
            <span className="text-xs font-medium text-gray-400">Hypothesis</span>
            <p className="mt-1 text-sm text-gray-200">{iteration.hypothesis || 'N/A'}</p>
          </div>
          <div>
            <span className="text-xs font-medium text-gray-400">Lesson</span>
            <p className="mt-1 text-sm text-gray-200">{iteration.lesson || 'N/A'}</p>
          </div>
          {iteration.files_changed.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-400">Files Changed</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {iteration.files_changed.map((f) => (
                  <span key={f} className="rounded bg-gray-700 px-2 py-0.5 text-xs font-mono text-gray-200">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}
          {iteration.validate_results && iteration.validate_results.length > 0 && (
            <div>
              <span className="text-xs font-medium text-gray-400">Validation Results</span>
              <div className="mt-1">
                <MiniTestSummary results={iteration.validate_results} />
              </div>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'id', label: '#' },
  { key: 'agent_id', label: 'Agent' },
  { key: 'iteration_num', label: 'Iteration' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'hypothesis', label: 'Hypothesis' },
  { key: 'lesson', label: 'Lesson' },
  { key: 'created_at', label: 'Created' },
];

export default function Journal({ runId }: JournalProps) {
  const { data: iterations, isLoading, error } = useIterations(runId);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('id');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [page, setPage] = useState(0);

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const processed = useMemo(() => {
    if (!iterations) return [];
    const term = search.toLowerCase();
    const filtered = term
      ? iterations.filter(
          (it) =>
            it.hypothesis.toLowerCase().includes(term) ||
            it.lesson.toLowerCase().includes(term) ||
            it.agent_id.toLowerCase().includes(term),
        )
      : iterations;
    const sorted = [...filtered].sort((a, b) => {
      const cmp = compare(a, b, sortKey);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return sorted;
  }, [iterations, search, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(processed.length / PAGE_SIZE));
  const paged = processed.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-gray-400 border-t-blue-400" />
        <span className="ml-3 text-sm text-gray-400">Loading journal...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-red-800 bg-red-900/30 px-4 py-3 text-sm text-red-300">
        Failed to load journal: {(error as Error).message}
      </div>
    );
  }

  if (!iterations || iterations.length === 0) {
    return (
      <div className="rounded border border-gray-700 bg-gray-800 px-4 py-8 text-center text-sm text-gray-400">
        No iterations recorded yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Search bar */}
      <input
        type="text"
        placeholder="Search hypothesis, lesson, or agent..."
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(0);
        }}
        className="w-full rounded border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none"
      />

      {/* Table */}
      <div className="overflow-x-auto rounded border border-gray-700">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-xs text-gray-400 uppercase">
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-2 cursor-pointer select-none hover:text-gray-200 transition-colors"
                  onClick={() => handleSort(col.key)}
                >
                  {col.label}
                  {sortKey === col.key && (
                    <span className="ml-1">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {paged.map((it) => (
              <Fragment key={it.id}>
                <tr
                  data-testid={`journal-row-${it.id}`}
                  onClick={() => setExpandedId(expandedId === it.id ? null : it.id)}
                  className="cursor-pointer bg-gray-900 hover:bg-gray-800 transition-colors"
                >
                  <td className="px-4 py-2 text-gray-300">{it.id}</td>
                  <td className="px-4 py-2 font-mono text-xs text-gray-200">{it.agent_id}</td>
                  <td className="px-4 py-2 text-gray-300">{it.iteration_num}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        OUTCOME_STYLE[it.outcome] ?? 'bg-gray-700 text-gray-400'
                      }`}
                    >
                      {it.outcome}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-300 max-w-xs truncate">{it.hypothesis}</td>
                  <td className="px-4 py-2 text-gray-300 max-w-xs truncate">{it.lesson}</td>
                  <td className="px-4 py-2 text-gray-400 text-xs">
                    {it.created_at ? new Date(it.created_at).toLocaleString() : '—'}
                  </td>
                </tr>
                {expandedId === it.id && <ExpandedRow iteration={it} />}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-400">
          <span>
            Page {page + 1} of {totalPages} ({processed.length} rows)
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              className="rounded bg-gray-700 px-3 py-1 text-xs disabled:opacity-40 hover:bg-gray-600"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
              className="rounded bg-gray-700 px-3 py-1 text-xs disabled:opacity-40 hover:bg-gray-600"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
