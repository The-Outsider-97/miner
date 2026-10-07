export type StatusState = "ready" | "unavailable" | "available" | "empty" | string;

export type ArtifactState = {
  profile: string | null;
  version: string | null;
  hash: string | null;
  size_bytes: number | null;
  validated: boolean | null;
  built_at: string | null;
  strategy: Record<string, unknown> | null;
  enabled_components: string[];
  disabled_components: string[];
};

export type RuntimeMeasurement = {
  agent?: string;
  operation?: string;
  elapsed_ms?: number;
};

export type BenchmarkRun = {
  run_id: string | null;
  run_kind: string | null;
  strategy: string | null;
  artifact_hash: string | null;
  artifact_version: string | null;
  batch_id: string | null;
  source_batch_id: string | null;
  total_score: number | null;
  comparison_score: number | null;
  fast_score: number | null;
  normal_score: number | null;
  wins: number | null;
  losses: number | null;
  ties: number | null;
  champion_selected: boolean | null;
  total_cost_usd: number | null;
  median_runtime_ms: number | null;
  p95_runtime_ms: number | null;
  timeout_rate: number | null;
  error_rate: number | null;
  citation_failure_rate: number | null;
  structured_output_failure_rate: number | null;
  created_at: string | null;
};

export type PerformanceState = {
  total_cost_usd: number | null;
  token_usage: number;
  tool_calls: number;
  provider_models: string[];
  median_runtime_ms: number | null;
  p95_runtime_ms: number | null;
  timeout_rate: number | null;
  error_rate: number | null;
  citation_failure_rate: number | null;
  structured_output_failure_rate: number | null;
};

export type MiningRegistrationState = {
  status: "registered" | "not_registered" | "unknown" | string;
  netuid: number | null;
  uid: number | null;
  hotkey_ss58: string | null;
  network: string | null;
  source: string;
};

export type MiningAuthState = {
  status: "authenticated" | "not_authenticated" | "error" | "unknown" | string;
  uid: number | null;
  hotkey_ss58: string | null;
  message: string | null;
};

export type MiningProviderState = {
  status: "ready" | "not_ready" | "unknown" | string;
  required: string[];
  configured: string[];
  missing: string[];
  requirements_complete: boolean;
};

export type MiningArtifactLifecycle = {
  status: "submitted" | "unknown" | string;
  acceptance: "accepted" | "unverified" | "rejected" | "unknown" | string;
  artifact_id: string | null;
  content_hash: string | null;
  submitted_at: string | null;
  uid: number | null;
  filename: string | null;
  size_bytes: number | null;
  candidate_status: "current_candidate" | "moved_to_batch" | "not_current" | "unknown" | string;
};

export type MiningSchedulerState = {
  status: "scheduled" | "disabled" | "unknown" | string;
  next_scheduled_batch_at: string | null;
  cron: string | null;
  evaluation_timeout_seconds: number | null;
  validator_health: {
    healthy: number | null;
    unhealthy: number | null;
    unknown: number | null;
  };
};

export type MiningBatchState = {
  batch_id: string;
  status: string;
  evaluation_stage: string | null;
  created_at: string | null;
  cutoff_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  artifact_count: number | null;
  task_count: number | null;
  qualifying_task_count: number | null;
  main_task_count: number | null;
  champion_artifact_id: string | null;
  stage_progress: Record<string, unknown> | null;
};

export type MiningValidatorExecutionState = {
  status: "running" | "completed" | "batch_running_unconfirmed" | "pending" | "unknown" | string;
  validator_count: number | null;
  resolved_count: number | null;
  total_count: number | null;
  percent_complete: number | null;
  started_at: string | null;
  stage: string | null;
};

export type MiningEvaluationState = {
  qualifying_status: string;
  main_status: string;
  main_admitted: boolean | null;
  final_status: string;
  qualifying_score: number | null;
  total_score: number | null;
  comparison_score: number | null;
  median_cost_usd: number | null;
  total_cost_usd: number | null;
  median_runtime_ms: number | null;
  novelty_classification: string | null;
  reference_selection_outcome: string | null;
  similarity_outcome: string | null;
  similarity_passes: boolean | null;
  similarity_responding_validator_count: number | null;  
};

export type MiningAllocationState = {
  status: string;
  reward_eligible: boolean | null;
  weight: number | null;
  source_batch_id: string | null;
  source: string;
};

export type MiningOnchainState = {
  status: "confirmed" | "emitting" | "unavailable" | "unknown" | string;
  netuid: number | null;
  weight_submitted: boolean | null;
  incentive: number | null;
  emission_tao: number | null;
  rank: number | null;
  trust: number | null;
  consensus: number | null;
  stake: number | null;
  last_update: number | string | null;
  source: string;
  message: string | null;
};

export type MiningSummary = {
  title: string;
  detail: string;
  next_step: string;
  batch_id: string | null;
  artifact_id: string | null;
};

export type MiningState = {
  status: "mining" | "initializing" | "inactive" | "unknown" | string;
  active: boolean;
  batch_id: string | null;
  batch_status: string | null;
  artifact_id: string | null;
  source: string;
  checked_at: string | null;
  phase: string;
  summary: MiningSummary;
  registration: MiningRegistrationState;
  harnyx_auth: MiningAuthState;
  providers: MiningProviderState;
  artifact: MiningArtifactLifecycle | null;
  scheduler: MiningSchedulerState;
  batch: MiningBatchState | null;
  validator_execution: MiningValidatorExecutionState;
  evaluation: MiningEvaluationState;
  allocation: MiningAllocationState;
  onchain: MiningOnchainState;
  errors: string[];
};

export type DashboardSnapshot = {
  schema: string;
  generated_at: string;
  backend: {
    status: StatusState;
    benchmark_store: StatusState;
    data_source: string;
    message: string | null;
  };
  mining: MiningState;
  artifact: ArtifactState | null;
  slai: {
    status: StatusState;
    commit: string | null;
    expected_commit: string | null;
    revision_state: "matching" | "mismatch" | "unresolved" | "unavailable" | string;
    worktree_state: "clean" | "modified" | "unavailable" | string;
    pinned: boolean;
    selected_agents: string[];
    runtime_measurements: RuntimeMeasurement[];
    runtime_evidence: "recorded" | "not_recorded" | string;
    runtime_candidates: string[];
  };
  harnyx: {
    status: StatusState;
    commit: string | null;
    expected_commit: string | null;
    revision_state: "matching" | "mismatch" | "unresolved" | "unavailable" | string;
    worktree_state: "clean" | "modified" | "unavailable" | string;
    pinned: boolean;
    sdk_version: string;
  };
  benchmark: {
    latest: BenchmarkRun | null;
    recent: BenchmarkRun[];
  };
  performance: PerformanceState | null;
  versions: {
    miner_commit: string | null;
    slai_commit: string | null;
    harnyx_commit: string | null;
    dataset_version: string | null;
    scoring_version: string | null;
    suite_slug: string | null;
    batch_id: string | null;
    source_batch_id: string | null;
  };
};

export type SectionDefinition = {
  id: string;
  label: string;
};

export type TaoCurrency =
  | "USD"
  | "EUR"
  | "GBP";

export type TaoMarketState = {
  status:
    | "ready"
    | "stale"
    | "unavailable";
  provider: string;
  asset: "TAO";
  prices: Record<TaoCurrency, string> | null;
  updated_at: string | null;
  fetched_at: string | null;
  message: string | null;
};

export type MinerEarningsState = {
  status:
    | "available"
    | "zero"
    | "unavailable";
  netuid: number;
  earned_tao: string | null;
  source: string;
  as_of: string | null;
  message: string | null;
};

export type TaoSnapshot = {
  schema: "slai-miner-tao-v1";
  generated_at: string;
  market: TaoMarketState;
  earnings: MinerEarningsState;
};

export type PreviousSubmission = {
  artifact_hash: string;
  profile: string;
  status: string;
  platform_artifact_id: string | null;
  platform_content_hash: string | null;
  uid: number | null;
  size_bytes: number | null;
  submitted_at: string;
};

export type ArtifactCandidate = {
  profile: string | null;
  version: string | null;
  sha256: string;
  size_bytes: number | null;
  built_at: string | null;
  manifest_validated: boolean;
  artifact_exists: boolean;
  previous_upload: PreviousSubmission | null;
};

export type PreflightCheck = {
  name: string;
  passed: boolean;
  detail: string;
};

export type ArtifactPreflight = {
  eligible: boolean;
  profile: string | null;
  version: string | null;
  sha256: string;
  size_bytes: number | null;
  harnyx_max_bytes: number;
  built_at: string | null;
  checks: PreflightCheck[];
  duplicate_upload: boolean;
  previous_upload: PreviousSubmission | null;
};

export type SubmissionStatus =
  | "idle"
  | "validating"
  | "ready"
  | "submitting"
  | "uploaded_unconfirmed"
  | "accepted"
  | "rejected"
  | "failed";

export type SubmissionResult = {
  status: SubmissionStatus;
  acceptance:
    | "unverified"
    | "accepted"
    | "rejected";
  artifact_id: string | null;
  content_hash: string;
  submitted_at: string | null;
  uid: number | null;
  size_bytes: number | null;
  message: string;
};