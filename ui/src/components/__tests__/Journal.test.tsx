import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Journal from '../Journal';
import type { IterationOut } from '../../api/types';

vi.mock('../../api/queries', () => ({
  useIterations: vi.fn(),
}));

import { useIterations } from '../../api/queries';

const mockUseIterations = vi.mocked(useIterations);

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const makeIteration = (overrides: Partial<IterationOut> = {}): IterationOut => ({
  id: 1,
  agent_id: 'agent-1',
  sub_objective_id: null,
  iteration_num: 1,
  hypothesis: 'Hypothesis A',
  files_changed: ['src/main.ts'],
  patch_sha: 'sha123',
  validate_results: null,
  outcome: 'advanced',
  lesson: 'Lesson A',
  created_at: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('Journal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders iteration rows', () => {
    const iterations: IterationOut[] = [
      makeIteration({ id: 1, agent_id: 'agent-1', outcome: 'advanced' }),
      makeIteration({ id: 2, agent_id: 'agent-2', iteration_num: 2, outcome: 'reverted', hypothesis: 'Hypothesis B', lesson: 'Lesson B' }),
    ];

    mockUseIterations.mockReturnValue({
      data: iterations,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<Journal runId="run-1" />, { wrapper });

    expect(screen.getByText('agent-1')).toBeInTheDocument();
    expect(screen.getByText('agent-2')).toBeInTheDocument();
    expect(screen.getByText('advanced')).toBeInTheDocument();
    expect(screen.getByText('reverted')).toBeInTheDocument();
  });

  it('search filters results', () => {
    const iterations: IterationOut[] = [
      makeIteration({ id: 1, hypothesis: 'Refactor database layer' }),
      makeIteration({ id: 2, hypothesis: 'Optimize UI rendering', lesson: 'Use memoization' }),
    ];

    mockUseIterations.mockReturnValue({
      data: iterations,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<Journal runId="run-1" />, { wrapper });

    // Both rows present
    expect(screen.getByText('Refactor database layer')).toBeInTheDocument();
    expect(screen.getByText('Optimize UI rendering')).toBeInTheDocument();

    // Search for "database"
    fireEvent.change(screen.getByPlaceholderText(/Search/), {
      target: { value: 'database' },
    });

    expect(screen.getByText('Refactor database layer')).toBeInTheDocument();
    expect(screen.queryByText('Optimize UI rendering')).not.toBeInTheDocument();
  });

  it('expands row details', () => {
    const iterations: IterationOut[] = [
      makeIteration({
        id: 1,
        hypothesis: 'Full hypothesis text here',
        lesson: 'Full lesson text here',
        files_changed: ['src/a.ts', 'src/b.ts'],
      }),
    ];

    mockUseIterations.mockReturnValue({
      data: iterations,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<Journal runId="run-1" />, { wrapper });

    // Click row to expand
    fireEvent.click(screen.getByTestId('journal-row-1'));

    // Expanded details visible (column header + expanded label = 2 each)
    expect(screen.getAllByText('Hypothesis')).toHaveLength(2);
    expect(screen.getAllByText('Lesson')).toHaveLength(2);
    expect(screen.getByText('src/a.ts')).toBeInTheDocument();
    expect(screen.getByText('src/b.ts')).toBeInTheDocument();
  });

  it('shows empty state when no iterations', () => {
    mockUseIterations.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<Journal runId="run-1" />, { wrapper });

    expect(screen.getByText(/No iterations recorded/)).toBeInTheDocument();
  });
});
