import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Controls from '../Controls';

// Mock mutations
const mockPauseMutate = vi.fn();
const mockResumeMutate = vi.fn();
const mockCancelMutate = vi.fn();
const mockKillMutate = vi.fn();

vi.mock('../../api/mutations', () => ({
  usePauseRun: () => ({ mutate: mockPauseMutate, isPending: false }),
  useResumeRun: () => ({ mutate: mockResumeMutate, isPending: false }),
  useCancelRun: () => ({ mutate: mockCancelMutate, isPending: false }),
  useKillAgent: () => ({ mutate: mockKillMutate, isPending: false }),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('Controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows Pause and Cancel buttons for running state', () => {
    render(<Controls runId="run-1" runState="running" />, { wrapper });

    expect(screen.getByText('Pause')).toBeInTheDocument();
    expect(screen.getByText('Cancel Run')).toBeInTheDocument();
    expect(screen.queryByText('Resume')).not.toBeInTheDocument();
  });

  it('shows Resume and Cancel buttons for paused state', () => {
    render(<Controls runId="run-1" runState="paused" />, { wrapper });

    expect(screen.getByText('Resume')).toBeInTheDocument();
    expect(screen.getByText('Cancel Run')).toBeInTheDocument();
    expect(screen.queryByText('Pause')).not.toBeInTheDocument();
  });

  it('shows no action buttons for completed state', () => {
    render(<Controls runId="run-1" runState="completed" />, { wrapper });

    expect(screen.queryByText('Pause')).not.toBeInTheDocument();
    expect(screen.queryByText('Resume')).not.toBeInTheDocument();
    expect(screen.queryByText('Cancel Run')).not.toBeInTheDocument();
    expect(screen.getByTestId('no-actions')).toHaveTextContent(/No actions available/);
  });

  it('shows no action buttons for failed state', () => {
    render(<Controls runId="run-1" runState="failed" />, { wrapper });

    expect(screen.getByTestId('no-actions')).toHaveTextContent(/No actions available/);
  });

  it('Cancel shows confirmation dialog', () => {
    render(<Controls runId="run-1" runState="running" />, { wrapper });

    // Click Cancel Run
    fireEvent.click(screen.getByText('Cancel Run'));

    // Confirm dialog appears
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText(/Are you sure/)).toBeInTheDocument();

    // Click Confirm
    fireEvent.click(screen.getByText('Confirm'));

    expect(mockCancelMutate).toHaveBeenCalledWith('run-1', expect.any(Object));
  });

  it('cancel confirmation can be dismissed', () => {
    render(<Controls runId="run-1" runState="running" />, { wrapper });

    fireEvent.click(screen.getByText('Cancel Run'));
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();

    // Click Cancel in the dialog (not "Cancel Run")
    fireEvent.click(screen.getByText('Cancel'));

    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument();
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });
});
