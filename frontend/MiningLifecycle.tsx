"use client";

import type { MiningState } from "./types";

type Props = {
  mining: MiningState;
  onRefresh: () => void;
};

type StepState = "complete" | "current" | "pending" | "unknown" | "error" | "skipped";

type Step = {
  label: string;
  detail: string;
  state: StepState;
};

const title = (value: string | null | undefined) =>
  !value
    ? "Unknown"
    : value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());

const shortId = (value: string | null | undefined, size = 12) =>
  !value ? "Not available" : value.length > size ? `${value.slice(0, size)}…` : value;

const number = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined
    ? "Not available"
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);

const money = (value: number | null | undefined) =>
  value === null || value === undefined
    ? "Not available"
    : `$${value.toFixed(value < 0.01 ? 6 : 4)}`;

const duration = (value: number | null | undefined) =>
  value === null || value === undefined
    ? "Not available"
    : value >= 1000
      ? `${(value / 1000).toFixed(2)} s`
      : `${value.toFixed(0)} ms`;

const timestamp = (value: string | null | undefined) => {
  if (!value) return "Not available";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const utc = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(parsed);
  const local = new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
  return `${utc} UTC${local === utc ? "" : ` · ${local} local`}`;
};

const dotState = (state: StepState) => {
  if (state === "complete" || state === "current") return "ready";
  if (state === "error") return "unavailable";
  if (state === "skipped") return "available";
  return "empty";
};

function lifecycleSteps(mining: MiningState): Step[] {
  const candidate = mining.artifact?.candidate_status;
  const batch = mining.batch;
  const validators = mining.validator_execution.status;
  const qualifying = mining.evaluation.qualifying_status;
  const main = mining.evaluation.main_status;
  const allocation = mining.allocation.status;

  return [
    {
      label: "SN67 Registered",
      detail:
        mining.registration.status === "registered"
          ? `UID ${mining.registration.uid ?? "unknown"} · Netuid ${mining.registration.netuid ?? "unknown"}`
          : "Registration is not independently available.",
      state: mining.registration.status === "registered" ? "complete" : "unknown",
    },
    {
      label: "Harnyx Authenticated",
      detail:
        mining.harnyx_auth.status === "authenticated"
          ? "Harnyx recognizes the configured signing hotkey."
          : mining.harnyx_auth.message ?? "Authentication state unavailable.",
      state: mining.harnyx_auth.status === "authenticated" ? "complete" : "unknown",
    },
    {
      label: "Provider Ready",
      detail:
        mining.providers.status === "ready"
          ? `${mining.providers.required.join(", ")} configured`
          : mining.providers.status === "not_ready"
            ? `Missing: ${mining.providers.missing.join(", ")}`
            : "Required-provider readiness is not fully known.",
      state:
        mining.providers.status === "ready"
          ? "complete"
          : mining.providers.status === "not_ready"
            ? "error"
            : "unknown",
    },
    {
      label: "Artifact Submitted",
      detail:
        mining.artifact?.acceptance === "accepted"
          ? `${mining.artifact.filename ?? "Production artifact"} · ${shortId(mining.artifact.artifact_id)}`
          : "No accepted production upload is confirmed.",
      state: mining.artifact?.acceptance === "accepted" ? "complete" : "pending",
    },
    {
      label: "Current Candidate",
      detail:
        candidate === "current_candidate"
          ? "Current Harnyx candidate; awaiting finalized batch selection."
          : candidate === "moved_to_batch"
            ? "Moved from the candidate view into batch membership."
            : "Current-candidate status is not confirmed.",
      state:
        candidate === "current_candidate"
          ? "current"
          : candidate === "moved_to_batch" || batch
            ? "complete"
            : candidate === "not_current"
              ? "unknown"
              : "pending",
    },
    {
      label: "Batch Selected",
      detail: batch
        ? `${shortId(batch.batch_id)} · ${title(batch.status)} · ${title(batch.evaluation_stage)}`
        : "No finalized batch membership is confirmed.",
      state: batch
        ? batch.status === "failed"
          ? "error"
          : batch.status === "initializing"
            ? "current"
            : "complete"
        : "pending",
    },
    {
      label: "Validator Execution",
      detail:
        validators === "running"
          ? "Artifact-level validator execution is confirmed."
          : validators === "batch_running_unconfirmed"
            ? "The batch is executing, but artifact-level task execution is not yet confirmed."
            : title(validators),
      state:
        validators === "running"
          ? "current"
          : validators === "completed"
            ? "complete"
            : validators === "batch_running_unconfirmed" || validators === "complete_or_unavailable"
              ? "unknown"
              : "pending",
    },
    {
      label: "Qualifying",
      detail: title(qualifying),
      state:
        qualifying === "running"
          ? "current"
          : qualifying === "complete"
            ? "complete"
            : qualifying === "pending"
              ? "pending"
              : batch
                ? "unknown"
                : "pending",
    },
    {
      label: "Main Evaluation",
      detail:
        main === "not_admitted"
          ? "Qualifying complete — not admitted to main."
          : title(main),
      state:
        main === "running" || main === "admitted"
          ? "current"
          : main === "complete"
            ? "complete"
            : main === "not_admitted"
              ? "skipped"
              : main === "unknown" && batch
                ? "unknown"
                : "pending",
    },
    {
      label: "Final Score",
      detail:
        mining.evaluation.total_score !== null
          ? `Total score ${number(mining.evaluation.total_score)}`
          : title(mining.evaluation.final_status),
      state:
        mining.evaluation.final_status === "scored"
          ? "complete"
          : mining.evaluation.final_status === "complete_score_unavailable"
            ? "unknown"
            : "pending",
    },
    {
      label: "Weight / Allocation",
      detail:
        allocation === "calculated"
          ? `Weight ${number(mining.allocation.weight, 6)}`
          : allocation === "no_participant_allocation"
            ? "No participant allocation."
            : allocation === "eligible_pending_weight"
              ? "Reward eligible; weight not yet exposed."
              : "No authoritative allocation is available yet.",
      state:
        allocation === "calculated"
          ? "complete"
          : allocation === "no_participant_allocation"
            ? "skipped"
            : allocation === "eligible_pending_weight"
              ? "current"
              : "pending",
    },
    {
      label: "Bittensor On-chain Emission",
      detail:
        mining.onchain.status === "emitting"
          ? `${number(mining.onchain.emission_tao, 8)} TAO`
          : mining.onchain.message ?? "On-chain state is not independently confirmed.",
      state:
        mining.onchain.status === "emitting"
          ? "current"
          : mining.onchain.weight_submitted === true
            ? "complete"
            : mining.onchain.status === "unavailable"
              ? "unknown"
              : "pending",
    },
  ];
}

export function MiningLifecycle({ mining, onRefresh }: Props) {
  const steps = lifecycleSteps(mining);
  const artifact = mining.artifact;
  const batch = mining.batch;
  const evaluation = mining.evaluation;
  const configuredProviders = new Set(mining.providers.configured);

  return (
    <>
      <div className="integration-grid">
        <div className="integration-card">
          <div className="integration-card__head">
            <div>
              <p className="side-panel__label">Current production state</p>
              <h3>{mining.summary.title}</h3>
            </div>
            <button className="secondary-button" type="button" onClick={onRefresh}>
              Refresh
            </button>
          </div>
          <p>{mining.summary.detail}</p>
          <dl className="detail-list detail-list--compact">
            <div className="detail-row">
              <dt>UID</dt>
              <dd>{mining.registration.uid ?? "Unknown"}</dd>
            </div>
            <div className="detail-row">
              <dt>Artifact</dt>
              <dd>{artifact?.filename ?? shortId(artifact?.artifact_id)}</dd>
            </div>
            <div className="detail-row">
              <dt>Next step</dt>
              <dd>{mining.summary.next_step ?? "No confirmed next transition"}</dd>
            </div>
            <div className="detail-row">
              <dt>Next batch</dt>
              <dd>{timestamp(mining.scheduler.next_scheduled_batch_at)}</dd>
            </div>
            <div className="detail-row">
              <dt>Last updated</dt>
              <dd>{timestamp(mining.checked_at)}</dd>
            </div>
          </dl>
        </div>

        <div className="integration-card">
          <div className="integration-card__head">
            <h3>Lifecycle</h3>
            <span className="status-label">
              <span className="status-dot" data-state={mining.active ? "ready" : "available"} aria-hidden="true" />
              {title(mining.phase)}
            </span>
          </div>
          <div className="side-status">
            {steps.map((step) => (
              <div className="side-status__row" key={step.label}>
                <span className="status-dot" data-state={dotState(step.state)} aria-hidden="true" />
                <span>{step.label}</span>
                <strong title={step.detail}>{title(step.state)}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="integration-grid subsection">
        <div className="integration-card">
          <div className="integration-card__head">
            <h3>Production artifact</h3>
            <span className="status-label">
              <span className="status-dot" data-state={artifact?.acceptance === "accepted" ? "ready" : "empty"} aria-hidden="true" />
              {title(artifact?.acceptance)}
            </span>
          </div>
          <dl className="detail-list detail-list--compact">
            <div className="detail-row"><dt>Artifact ID</dt><dd><code className="hash-value">{artifact?.artifact_id ?? "Not available"}</code></dd></div>
            <div className="detail-row"><dt>Hash</dt><dd><code className="hash-value">{artifact?.content_hash ?? "Not available"}</code></dd></div>
            <div className="detail-row"><dt>Submitted</dt><dd>{timestamp(artifact?.submitted_at)}</dd></div>
            <div className="detail-row"><dt>Candidate</dt><dd>{title(artifact?.candidate_status)}</dd></div>
          </dl>
          <div className="component-list">
            {mining.providers.required.length ? mining.providers.required.map((provider) => (
              <span className="component-chip" data-state={configuredProviders.has(provider) ? "ready" : "unavailable"} key={provider}>
                {provider} · {configuredProviders.has(provider) ? "configured" : "not configured"}
              </span>
            )) : <span className="muted-copy">Required-provider set is not available.</span>}
          </div>
        </div>

        <div className="integration-card">
          <div className="integration-card__head">
            <h3>Batch / validators</h3>
            <span className="status-label">
              <span className="status-dot" data-state={batch?.status === "running" ? "ready" : "empty"} aria-hidden="true" />
              {batch ? title(batch.status) : "Not selected"}
            </span>
          </div>
          <dl className="detail-list detail-list--compact">
            <div className="detail-row"><dt>Batch</dt><dd><code className="hash-value">{batch?.batch_id ?? "Not available"}</code></dd></div>
            <div className="detail-row"><dt>Stage</dt><dd>{title(batch?.evaluation_stage)}</dd></div>
            <div className="detail-row"><dt>Cutoff</dt><dd>{timestamp(batch?.cutoff_at)}</dd></div>
            <div className="detail-row"><dt>Tasks</dt><dd>{batch ? `${batch.qualifying_task_count ?? 0} qualifying · ${batch.main_task_count ?? 0} main` : "Not available"}</dd></div>
            <div className="detail-row"><dt>Validators</dt><dd>{mining.validator_execution.validator_count ?? "Not available"}{mining.validator_execution.percent_complete !== null ? ` · ${mining.validator_execution.percent_complete.toFixed(1)}% batch progress` : ""}</dd></div>
          </dl>
        </div>
      </div>

      <div className="metric-grid subsection">
        <div className="metric"><p>Qualifying score</p><strong>{number(evaluation.qualifying_score)}</strong></div>
        <div className="metric"><p>Total score</p><strong>{number(evaluation.total_score)}</strong></div>
        <div className="metric"><p>Execution cost</p><strong>{evaluation.total_cost_usd !== null ? money(evaluation.total_cost_usd) : money(evaluation.median_cost_usd)}</strong></div>
        <div className="metric"><p>Median runtime</p><strong>{duration(evaluation.median_runtime_ms)}</strong></div>
        <div className="metric"><p>Reward eligibility</p><strong>{mining.allocation.reward_eligible === true ? "Eligible" : mining.allocation.reward_eligible === false ? "No participant allocation" : "Unknown"}</strong></div>
        <div className="metric"><p>On-chain emission</p><strong>{mining.onchain.emission_tao !== null ? `${number(mining.onchain.emission_tao, 8)} TAO` : "Not confirmed"}</strong></div>
      </div>

      {mining.errors.length ? (
        <div className="inline-notice subsection">
          <span className="status-dot" data-state="unavailable" aria-hidden="true" />
          <p>{mining.errors.join(" ")}</p>
        </div>
      ) : null}
    </>
  );
}
