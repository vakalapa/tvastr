import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TestResults from '../TestResults';
import type { ValidationResultOut } from '../../api/types';

const makeResult = (overrides: Partial<ValidationResultOut> = {}): ValidationResultOut => ({
  name: 'test_example',
  status: 'pass',
  output: 'Test passed successfully',
  duration_secs: 1.23,
  failed_tests: null,
  ...overrides,
});

describe('TestResults', () => {
  it('renders summary counts correctly', () => {
    const results: ValidationResultOut[] = [
      makeResult({ name: 'test_a', status: 'pass' }),
      makeResult({ name: 'test_b', status: 'pass' }),
      makeResult({ name: 'test_c', status: 'fail' }),
      makeResult({ name: 'test_d', status: 'error' }),
    ];

    render(<TestResults results={results} />);

    expect(screen.getByTestId('summary-bar')).toHaveTextContent('4 tests');
    expect(screen.getByTestId('summary-bar')).toHaveTextContent('2 passed');
    expect(screen.getByTestId('summary-bar')).toHaveTextContent('1 failed');
    expect(screen.getByTestId('summary-bar')).toHaveTextContent('1 errors');
  });

  it('filters by status', () => {
    const results: ValidationResultOut[] = [
      makeResult({ name: 'test_pass_1', status: 'pass' }),
      makeResult({ name: 'test_fail_1', status: 'fail' }),
      makeResult({ name: 'test_pass_2', status: 'pass' }),
    ];

    render(<TestResults results={results} />);

    // Initially all shown
    expect(screen.getByText('test_pass_1')).toBeInTheDocument();
    expect(screen.getByText('test_fail_1')).toBeInTheDocument();
    expect(screen.getByText('test_pass_2')).toBeInTheDocument();

    // Click "Failed" filter
    fireEvent.click(screen.getByText('Failed (1)'));

    expect(screen.queryByText('test_pass_1')).not.toBeInTheDocument();
    expect(screen.getByText('test_fail_1')).toBeInTheDocument();
    expect(screen.queryByText('test_pass_2')).not.toBeInTheDocument();
  });

  it('expands test details', () => {
    const results: ValidationResultOut[] = [
      makeResult({
        name: 'test_expandable',
        status: 'fail',
        output: 'AssertionError: expected true to be false',
        failed_tests: ['test_expandable::case_1'],
      }),
    ];

    render(<TestResults results={results} />);

    // Output not visible before expand
    expect(screen.queryByText(/AssertionError/)).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(screen.getByText('test_expandable'));

    expect(screen.getByText(/AssertionError: expected true to be false/)).toBeInTheDocument();
    expect(screen.getByText('test_expandable::case_1')).toBeInTheDocument();
  });

  it('handles empty results', () => {
    render(<TestResults results={[]} />);

    expect(screen.getByText(/No test results available/)).toBeInTheDocument();
  });

  it('shows duration for each test', () => {
    const results: ValidationResultOut[] = [
      makeResult({ name: 'test_timed', duration_secs: 2.567 }),
    ];

    render(<TestResults results={results} />);

    expect(screen.getByText('2.57s')).toBeInTheDocument();
  });
});
