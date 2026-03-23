/** Run lifecycle states */
export type RunState = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';

/** Agent lifecycle states */
export type AgentState = 'pending' | 'running' | 'succeeded' | 'failed' | 'killed';

/** A single validation / test result */
export interface ValidationResultOut {
  name: string;
  status: string; // 'pass' | 'fail' | 'error' | 'skip'
  output: string;
  duration_secs: number;
  failed_tests: string[] | null;
}

/** One iteration performed by an agent */
export interface IterationOut {
  id: number;
  agent_id: string;
  sub_objective_id: number | null;
  iteration_num: number;
  hypothesis: string;
  files_changed: string[];
  patch_sha: string;
  validate_results: ValidationResultOut[] | null;
  outcome: string;
  lesson: string;
  created_at: string | null;
}

/** Lightweight agent summary */
export interface AgentOut {
  agent_id: string;
  run_id: string;
  state: AgentState;
  sub_objective_id: number | null;
  iterations_completed: number;
  created_at: string | null;
}

/** A forge run */
export interface RunOut {
  id: string;
  repo_url: string;
  objective: string;
  state: RunState;
  agents: AgentOut[];
  created_at: string | null;
  updated_at: string | null;
}

/** Payload for creating a run */
export interface CreateRunIn {
  repo_url: string;
  objective: string;
  max_agents?: number;
}
