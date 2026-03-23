import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PatchViewer from '../PatchViewer';
import type { IterationOut } from '../../api/types';

// Mock the queries module
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
  hypothesis: 'Test hypothesis',
  files_changed: ['src/main.ts', 'src/utils.ts'],
  patch_sha: 'abc123def',
  validate_results: null,
  outcome: 'advanced',
  lesson: 'Learned something',
  created_at: '2024-01-01T00:00:00Z',
  ...overrides,
});

describe('PatchViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders file list from iteration data', () => {
    mockUseIterations.mockReturnValue({
      data: [makeIteration()],
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<PatchViewer runId="run-1" agentId="agent-1" />, { wrapper });

    expect(screen.getByText('2 file(s)')).toBeInTheDocument();
    // Expand to see files
    fireEvent.click(screen.getByText(/Iteration #1/));
    expect(screen.getByText('src/main.ts')).toBeInTheDocument();
    expect(screen.getByText('src/utils.ts')).toBeInTheDocument();
  });

  it('shows patch SHA when expanded', () => {
    mockUseIterations.mockReturnValue({
      data: [makeIteration()],
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<PatchViewer runId="run-1" agentId="agent-1" />, { wrapper });

    fireEvent.click(screen.getByText(/Iteration #1/));
    expect(screen.getByTestId('patch-sha')).toHaveTextContent('abc123def');
  });

  it('handles empty files_changed', () => {
    mockUseIterations.mockReturnValue({
      data: [makeIteration({ files_changed: [] })],
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<PatchViewer runId="run-1" agentId="agent-1" />, { wrapper });

    expect(screen.getByText('no files')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Iteration #1/));
    expect(screen.getByText(/No files changed/)).toBeInTheDocument();
  });

  it('shows empty state when no iterations found', () => {
    mockUseIterations.mockReturnValue({
      data: [],
      isLoading: false,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<PatchViewer runId="run-1" agentId="agent-1" />, { wrapper });

    expect(screen.getByText(/No iterations found/)).toBeInTheDocument();
  });

  it('shows loading state', () => {
    mockUseIterations.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useIterations>);

    render(<PatchViewer runId="run-1" agentId="agent-1" />, { wrapper });

    expect(screen.getByText(/Loading patches/)).toBeInTheDocument();
  });
});
