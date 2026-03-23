/** Mirrors tvastr server Pydantic models / DB schema. */

// --- Enums ---

export enum RunState {
  PENDING = "pending",
  RUNNING = "running",
  MERGING = "merging",
  DONE = "done",
  FAILED = "failed",
}

export enum AgentState {
  IDLE = "idle",
  DISCOVERING = "discovering",
  PLANNING = "planning",
  PATCHING = "patching",
  VALIDATING = "validating",
  DONE = "done",
  FAILED = "failed",
}

export enum SubObjectiveStatus {
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  DONE = "done",
  BLOCKED = "blocked",
}

export enum WSEventType {
  AGENT_OUTPUT = "agent_output",
  AGENT_STATE = "agent_state",
  ITERATION_COMPLETE = "iteration_complete",
  RUN_STATE = "run_state",
  ERROR = "error",
}

// --- Request types ---

export interface RunCreateRequest {
  repo_path: string;
  objective: string;
  max_iterations_per_agent?: number;
  max_concurrent_agents?: number;
  model?: string;
  strategy?: string;
  parallel?: boolean;
}

// --- Response types ---

export interface RunSummary {
  run_id: string;
  repo_path: string;
  objective: string;
  state: RunState;
  agent_count: number;
  created_at: string;
}

export interface RunOut {
  run_id: string;
  repo_path: string;
  objective: string;
  state: RunState;
  strategy: string;
  parallel: boolean;
  max_iterations_per_agent: number;
  max_concurrent_agents: number;
  model: string;
  agent_count: number;
  created_at: string;
  finished_at: string | null;
}

export interface AgentOut {
  agent_id: string;
  run_id: string;
  sub_objective_id: number;
  sub_objective_desc: string;
  branch_name: string;
  state: AgentState;
  iteration_count: number;
  result: boolean | null;
  error: string | null;
}

export interface IterationOut {
  id: number;
  agent_id: string;
  sub_objective_id: number | null;
  iteration_num: number;
  hypothesis: string;
  files_changed: string[];
  patch_sha: string;
  validate_results: ValidationResultOut[] | null;
  outcome: string; // "advanced" | "reverted" | "partial" | "no_changes"
  lesson: string;
  created_at: string;
}

export interface SubObjectiveOut {
  id: number;
  description: string;
  status: SubObjectiveStatus;
  assigned_agent: string | null;
  priority: number;
  depends_on: number[];
  created_at: string;
  completed_at: string | null;
}

export interface ValidationResultOut {
  status: string; // "pass" | "fail" | "error" | "skip"
  name: string;
  output: string;
  duration_secs: number;
  failed_tests: string[] | null;
}

export interface MergeResultOut {
  branch: string;
  success: boolean;
  conflict_files: string[];
  validation_passed: boolean | null;
  error: string | null;
}

export interface WSMessage {
  event: WSEventType;
  run_id?: string;
  agent_id?: string;
  data: unknown;
  timestamp: string;
}
