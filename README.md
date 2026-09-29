# SLAI × Harnyx SN67 Miner

Dedicated engineering environment for determining whether **SLAI v2.3** can produce a measurable validator-scoring advantage on **Harnyx / Bittensor Subnet 67**.

Miner builds standalone Harnyx artifacts, invokes official Harnyx local evaluation/benchmark tooling, persists benchmark evidence, and now includes a read-only observability frontend. It deliberately contains **no wallet registration, subnet registration, artifact submission, or TAO-spending command**.

## Architecture

```text
Miner (authoritative repository)
├── external/slai               -> pinned SLAI-v2.3 Git submodule
├── external/harnyx             -> pinned harnyx/harnyx Git submodule
├── adapters/slai.py            -> full development-runtime boundary
├── adapters/harnyx.py          -> Query/ContextSnapshot/Response boundary
├── artifact_builder.py
├── benchmark_store.py
├── dashboard_api.py            -> read-only frontend snapshot bridge
├── slai_miner.py
├── artifacts/harnyx/*.py       -> standalone validator artifacts
└── frontend/                   -> single-page SN67 observability dashboard
```

The full SLAI runtime is a development dependency only. Submitted Harnyx artifacts never assume SLAI source, AgentFactory, SharedMemory, local models, Miner files, or frontend code are present in the validator sandbox. Harnyx scoring and champion-selection logic are not copied into Miner; official Harnyx tooling remains authoritative.

## Clone and dependencies

```powershell
git clone --recurse-submodules https://github.com/The-Outsider-97/miner.git
Set-Location .\miner
git submodule sync --recursive
git submodule update --init --recursive
uv sync --group dev
```

The Git-link commits are the reproducibility pins. `configs/harnyx.yaml` records the expected SLAI/Harnyx revisions and non-secret Miner policy.

## Environment boundaries

Keep the Miner, SLAI, and Harnyx environments isolated.

For normal Miner work:

```powershell
uv run python .\slai_miner.py status
```

For real SLAI runtime checks, use the existing SLAI interpreter rather than installing Harnyx/Bittensor packages into it. Harnyx Docker/local-eval work should be run from WSL2/Linux using the pinned `external/harnyx` workspace.

Never commit provider keys, wallet material, seed phrases, private keys, or hotkey URIs. `.gitignore` excludes local credential paths, SQLite benchmark state, Harnyx result bundles, logs, and frontend build output.

## Artifact progression

| Profile | Strategy |
|---|---|
| **B0** | fixed-provider direct Harnyx baseline |
| **B1** | B0 + provider/model availability routing |
| **B2** | B1 + bounded normal-query decomposition |
| **B3** | routing + Harnyx retrieval + evidence ranking + citations + synthesis |
| **B4** | B3 + decomposition + budget/time-gated verification |
| **B5** | withheld until benchmark evidence identifies the strongest selective architecture |

Examples:

```powershell
uv run python .\artifact_builder.py b3
uv run python .\artifact_builder.py all
uv run python .\artifact_builder.py b4 --disable verification --disable decomposition
```

With the pinned Harnyx environment installed, `--official-validate` invokes Harnyx's own loader/entrypoint/hash validation.

## Official Harnyx evaluation

```bash
# WSL2 / LINUX - Miner root
uv run python slai_miner.py eval \
  --artifact artifacts/harnyx/baseline_agent.py \
  --strategy b0 \
  --mode vs-champion
```

For candidate comparison, reuse the same completed batch:

```bash
uv run python slai_miner.py eval \
  --artifact artifacts/harnyx/b3_agent.py \
  --strategy b3 \
  --batch-id <completed-batch-uuid> \
  --mode vs-champion
```

Miner delegates execution, scoring, retries, target/champion comparison, and local champion-selection simulation to the official Harnyx tooling. Reports are normalized into `BenchmarkStore`.

## BenchmarkStore

`benchmark_store.py` is experiment analytics, not AI memory. It persists run/task identity, artifact hash/version, strategy, batch identity, official score fields, cost, tool/token usage, median/p95 runtime, timeout/error/citation/schema failure rates, head-to-head outcomes, ablation metadata, and Miner/SLAI/Harnyx revisions.

```powershell
uv run python .\slai_miner.py runs --limit 10
```

Raw Harnyx reports and SQLite data stay local because they can contain task text, retrieved evidence, and provider output.

## Frontend dashboard

`frontend/` contains the implemented **single-page SLAI Miner SN67 observability dashboard**. Its visual system is based on the actual BIMAP frontend: fixed blurred shell header, black/off-white/yellow palette, Segoe UI/Cascadia Mono typography, thin separators, numbered side navigation, compact dark footer, BIMAP-style route loader, and the same 980 px / 680 px responsive breakpoints.

The browser does **not** duplicate Harnyx report parsing or BenchmarkStore normalization. `frontend/app/api/dashboard/route.ts` invokes the root `dashboard_api.py` bridge. That bridge reads existing normalized Miner state, artifact manifests, persisted benchmark evidence, and dependency status and returns one frontend-safe JSON snapshot.

The UI displays only data that exists. If no benchmark run is available it shows an explicit `No benchmark results available yet.` state. SLAI agents are only displayed as selected/used when that evidence was actually persisted.

Dashboard sections:

- Overview — artifact, score, champion comparison, backend state;
- Artifact — profile/version/hash/size/validation and enabled/ablated strategy components;
- SLAI — pinned SLAI/Harnyx state plus persisted selected-agent/runtime measurements;
- Benchmark — total/comparison/fast/normal scores, W/L/T and recent runs;
- Performance — cost, tokens, tool calls, median/p95 latency, timeout/error/citation/schema failure rates;
- System — Miner/SLAI/Harnyx revisions and benchmark suite/data/scoring versions when available.

### Run the frontend

Prepare the Miner Python environment from the repository root, then:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

The dashboard API uses `uv run --project .. --no-sync python` by default. Set `MINER_PYTHON` to an explicit interpreter path if another Python environment should execute `dashboard_api.py`.

Validation commands:

```powershell
npm run typecheck
npm run lint
npm run build
```

The frontend is observability-only: no authentication, wallet-management, subnet-registration, TAO-transfer, or artifact-submission controls are included.

## Tests and CI

Backend credential-free checks:

```powershell
uv run pytest -q -m "not integration and not harnyx"
uv run ruff check artifact_builder.py benchmark_store.py dashboard_api.py slai_miner.py adapters utils tests
```

GitHub Actions contains separate backend and frontend workflows. The frontend workflow compiles the Python dashboard bridge, installs the frontend dependencies, then runs TypeScript checking, ESLint, and the production Next.js build without paid API credentials.

## Deployment gate

No registration or TAO expenditure should be added until official artifact validation and Docker-backed local-eval have succeeded, B0/selective candidates have been compared on pinned and holdout batches, reward-relevant improvement survives cost/latency/error analysis, secrets are clean, and current SN67 economics have been manually reviewed.

Any future action capable of spending TAO requires explicit human confirmation.

## Current limitations

- B0-B4 remain engineering hypotheses until official local-eval/holdout evidence exists.
- The dashboard can only display benchmark fields that have actually been persisted; missing evidence is intentionally shown as unavailable.
- SLAI runtime measurements require the real SLAI environment and must be persisted before they appear as used-agent evidence.
- Harnyx platform upload policy remains authoritative even after local preflight and official loader validation.
