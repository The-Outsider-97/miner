# SLAI × Harnyx SN67 Miner

Dedicated engineering environment for determining whether **SLAI v2.3** can
produce a measurable validator-scoring advantage on **Harnyx / Bittensor
Subnet 67**.

Miner builds standalone Harnyx artifacts, invokes official Harnyx local
evaluation/benchmark tooling, persists benchmark evidence, and exposes a
read-only observability frontend. It deliberately contains **no wallet
registration, subnet registration, artifact submission, or TAO-spending
command**.

## Architecture

```text
Miner (authoritative repository)
├── external/slai               -> pinned SLAI-v2.3 Git submodule
├── external/harnyx             -> pinned harnyx/harnyx Git submodule
├── adapters/slai.py            -> full development-runtime boundary
├── adapters/harnyx.py          -> Query/ContextSnapshot/Response boundary
├── utils/repository_state.py   -> shared revision/path state
├── artifact_builder.py
├── benchmark_store.py
├── dashboard_api.py            -> read-only frontend snapshot bridge
├── slai_miner.py               -> development CLI/orchestration
├── artifacts/harnyx/*.py       -> standalone validator artifacts
└── frontend/                   -> single-page SN67 observability dashboard
```

Dependency direction is intentionally one-way:

```text
utils/config/state
      ↓
   adapters
      ↓
domain services (artifact / benchmark)
      ↓
orchestration (slai_miner)
      ↓
CLI / frontend bridge
```

`dashboard_api.py` does not import the CLI. Shared repository revision/path
logic lives in `utils/repository_state.py`, and frontend reads use
`BenchmarkStore`'s public read-only API rather than its SQLite connection.

The full SLAI runtime is a development dependency only. Submitted Harnyx
artifacts never assume SLAI source, AgentFactory, SharedMemory, local models,
Miner files, BenchmarkStore, or frontend code are present in the validator
sandbox. Harnyx scoring and champion-selection logic are not copied into Miner;
official Harnyx tooling remains authoritative.

## Clone and dependencies

```powershell
git clone --recurse-submodules https://github.com/The-Outsider-97/miner.git
Set-Location .\miner
git submodule sync --recursive
git submodule update --init --recursive
uv sync --group dev
```

The Git-link commits are the upstream reproducibility pins.
`configs/harnyx.yaml` records the expected SLAI/Harnyx revisions and non-secret
Miner policy.

Check effective revision and worktree state:

```powershell
uv run python .\slai_miner.py status
```

A dependency is reported `ready` only when its checked-out commit matches the
configured pin and its tracked worktree is clean.

## Environment boundaries

Keep the Miner, SLAI, and Harnyx environments isolated.

For normal Miner work:

```powershell
uv run python .\slai_miner.py status
```

For real SLAI runtime checks, use the existing SLAI interpreter rather than
installing Harnyx/Bittensor packages into it. Harnyx Docker/local-eval work
should be run from WSL2/Linux using the pinned `external/harnyx` workspace.

Never commit provider keys, wallet material, seed phrases, private keys, or
hotkey URIs. `.gitignore` excludes local credential paths, SQLite benchmark
state, Harnyx result bundles, logs, and frontend build output.

## SLAI development runtime

`adapters/slai.py` constructs agents through SLAI `AgentFactory` and reuses
SLAI's process-scoped `SharedMemory`. Current explicit runtime experiment
operations are:

- `ReasoningAgent` through `SlaiRuntime.reason()`;
- `KnowledgeAgent` through `SlaiRuntime.retrieve()`.

Other registered SLAI agents are classified in
`docs/slai_agent_selection.md`; none are invoked merely to increase agent
count. Agent initialization and invocation latency is measured by the adapter.

Because SLAI `SharedMemory` is a process singleton, `SlaiRuntime.close()` shuts
down its AgentFactory and clears experiment values without closing the singleton
memory object. This permits sequential Miner experiments in one process without
reusing a permanently closed SharedMemory instance.

## Artifact progression

| Profile | Strategy |
|---|---|
| **B0** | fixed-provider direct Harnyx baseline |
| **B1** | B0 + provider/model availability routing |
| **B2** | B1 + bounded normal-query decomposition |
| **B3** | routing + Harnyx retrieval + evidence ranking + citations + synthesis |
| **B4** | B3 + decomposition + request-local budget/time-gated verification |
| **B5** | withheld until benchmark evidence identifies the strongest selective architecture |

Examples:

```powershell
uv run python .\artifact_builder.py b3
uv run python .\artifact_builder.py all
uv run python .\artifact_builder.py b4 --disable verification --disable decomposition
```

With the pinned Harnyx environment installed, `--official-validate` invokes
Harnyx's own loader/entrypoint/hash validation. Miner reads
`MAX_AGENT_BYTES` from the pinned Harnyx source instead of using the
documentation value as runtime authority.

## Official Harnyx evaluation

```bash
# WSL2 / LINUX - Miner root
uv run python slai_miner.py eval \
  --artifact artifacts/harnyx/baseline_agent.py \
  --strategy b0
```

`--mode` is optional; when omitted Miner uses
`harnyx.local_eval.default_mode` from `configs/harnyx.yaml`.

For candidate comparison, reuse the same completed batch:

```bash
uv run python slai_miner.py eval \
  --artifact artifacts/harnyx/b3_agent.py \
  --strategy b3 \
  --batch-id <completed-batch-uuid>
```

Miner delegates execution, scoring, retries, target/champion comparison, and
local champion-selection simulation to official Harnyx tooling. The Harnyx
command names and benchmark query-time limit are read from Miner configuration.
Machine-readable report paths are verified to exist inside the requested Miner
result directory before ingestion.

## BenchmarkStore

`benchmark_store.py` is experiment analytics, not AI memory. It persists
run/task identity, artifact hash/version, strategy, batch identity, official
score fields, cost, tool/token usage, median/p95 runtime,
timeout/error/citation/schema failure rates, head-to-head outcomes, ablation
metadata, and Miner/SLAI/Harnyx revisions.

```powershell
uv run python .\slai_miner.py runs --limit 10
```

Writes use a normal WAL-enabled SQLite connection. Dashboard reads use
`BenchmarkStore(..., read_only=True)` and a bounded `recent_run_details()` path,
so the frontend does not create or mutate the experiment database. Recent
dashboard data is loaded with one run query plus one task query rather than one
task query per run.

Raw Harnyx reports and SQLite data stay local because they can contain task
text, retrieved evidence, and provider output.

## Frontend dashboard

`frontend/` contains the implemented **single-page SLAI Miner SN67
observability dashboard**. Its visual system is based on the actual BIMAP
frontend: fixed blurred shell header, black/off-white/yellow palette, Segoe
UI/Cascadia Mono typography, thin separators, numbered side navigation, compact
dark footer, BIMAP-style route loader, and the same 980 px / 680 px responsive
breakpoints.

The browser does **not** parse Harnyx reports or read SQLite directly.
`frontend/app/api/dashboard/route.ts` invokes the root `dashboard_api.py`
bridge once per dashboard request. The route validates the returned dashboard
schema before forwarding it and returns sanitized 503 responses on bridge
failure. The bridge reads normalized BenchmarkStore state, artifact manifests,
and dependency status.

The UI displays only data that exists. If no benchmark run is available it
shows `No benchmark results available yet.` SLAI agents are displayed as used
only when selected-agent/runtime measurements were actually persisted.

Dashboard sections:

- Overview — artifact, score, champion comparison, backend state;
- Artifact — profile/version/hash/size/validation and enabled/ablated strategy components;
- SLAI — pinned SLAI/Harnyx state plus persisted selected-agent/runtime measurements;
- Benchmark — total/comparison/fast/normal scores, W/L/T and recent runs;
- Performance — cost, tokens, tool calls, provider/model usage, median/p95 latency, timeout/error/citation/schema failure rates;
- System — Miner/SLAI/Harnyx revisions and benchmark suite/data/scoring versions when available.

### Run the frontend

Prepare the Miner Python environment from the repository root, then:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

The dashboard API uses `uv run --project .. --no-sync python` by default.
`MINER_ROOT` may point to an explicit Miner checkout, and `MINER_PYTHON` may
point to an explicit Python interpreter.

Validation:

```powershell
npm run typecheck
npm run lint
npm run build
```

The frontend is observability-only: no authentication, wallet-management,
subnet-registration, TAO-transfer, or artifact-submission controls are
included.

## Tests and CI

Backend credential-free checks:

```powershell
uv run ruff check artifact_builder.py benchmark_store.py dashboard_api.py slai_miner.py adapters utils tests
uv run python -m compileall -q artifact_builder.py benchmark_store.py dashboard_api.py slai_miner.py adapters utils artifacts/harnyx tests
uv run pytest -q -m "not integration and not harnyx"
uv run python .\dashboard_api.py --json
```

The test suite includes independent import/circular-boundary smoke tests,
BenchmarkStore read-only/corruption coverage, dashboard empty/populated/error
states, Harnyx adapter contract checks, artifact determinism/ablation checks,
and opt-in real SLAI/Harnyx integration tests.

GitHub Actions contains separate backend and frontend workflows. The frontend
workflow compiles the Python bridge, installs frontend dependencies, then runs
TypeScript checking, ESLint, and the production Next.js build without paid API
credentials.

## Deployment gate

No registration or TAO expenditure should be added until official artifact
validation and Docker-backed local-eval have succeeded, B0/selective candidates
have been compared on pinned and holdout batches, reward-relevant improvement
survives cost/latency/error analysis, secrets are clean, and current SN67
economics have been manually reviewed.

Any future action capable of spending TAO requires explicit human confirmation.

## Current limitations

- B0-B4 remain engineering hypotheses until official local-eval/holdout evidence exists.
- The dashboard can only display benchmark fields that have actually been persisted; missing evidence is intentionally unavailable.
- SLAI runtime measurements require the real SLAI environment and must be associated with an experiment before they appear as used-agent evidence.
- Harnyx platform upload policy remains authoritative even after Miner preflight and official loader validation.
- Miner and frontend dependency lockfiles are not currently committed; upstream source revisions are pinned, but third-party package resolution still follows the declared version constraints.
