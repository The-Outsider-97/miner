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

export type DashboardSnapshot = {
  schema: string;
  generated_at: string;
  backend: {
    status: StatusState;
    benchmark_store: StatusState;
    data_source: string;
    message: string | null;
  };
  artifact: ArtifactState | null;
  slai: {
    status: StatusState;
    commit: string | null;
    expected_commit: string | null;
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
  | "GBP"
  | "BTC";

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