# SLAI × Harnyx SN67 Miner

Dedicated engineering environment for determining whether **SLAI v2.3** can produce a measurable validator-scoring advantage on **Harnyx / Bittensor Subnet 67**.

The repository builds standalone Harnyx artifacts, invokes the current official Harnyx local-eval/local-benchmark tooling, persists benchmark evidence, and supports component ablation. It deliberately contains **no wallet registration, subnet registration, artifact submission, or TAO-spending command**.

## Architecture

```text
Miner (authoritative repository)
├── external/slai    -> pinned SLAI-v.2.3 Git submodule
├── external/harnyx  -> pinned harnyx/harnyx Git submodule
├── adapters/slai.py -> full development-runtime boundary
├── adapters/harnyx.py -> Query/ContextSnapshot/Response boundary
├── artifact_builder.py
├── benchmark_store.py
├── slai_miner.py
└── artifacts/harnyx/*.py -> standalone validator artifacts
```

The full SLAI runtime is a development dependency only. Submitted Harnyx artifacts never assume SLAI source, AgentFactory, SharedMemory, local models, or Miner files are present in the validator sandbox. Normal SLAI agents remain unaware of Harnyx.

Current pinned revisions are recorded by the Git links plus `configs/harnyx.yaml`. Harnyx scoring and champion-selection logic are **not copied** into Miner; official Harnyx tooling remains authoritative.

## Current Harnyx contract

See [`docs/harnyx_contract.md`](docs/harnyx_contract.md) for the inspected source paths. At the pinned revision:

- `harnyx-miner-sdk` is `0.1.23` and the toolchain requires Python `>=3.11,<3.12`;
- miners submit one UTF-8 Python source artifact;
- the current recommended entrypoint is `async def query(query: Query, context: ContextSnapshot) -> Response`;
- `Query.fast=True` is correctness-only and citations provide no scoring benefit;
- normal research responses are evidence/citation sensitive;
- structured output must use the query's JSON Schema contract and return `Response.output` rather than encoded JSON in `text`;
- citations must use receipt/result IDs returned by Harnyx tools;
- current `MAX_AGENT_BYTES` is read from pinned Harnyx source (1,000,000 bytes at the inspected commit);
- official local evaluation runs target/champion artifacts in Docker validator-style sandboxes;
- black-box endpoint mining is still documented by Harnyx as not released and initially zero-emission.

## Clone / submodules

```powershell
# POWERSHELL
git clone --recurse-submodules https://github.com/The-Outsider-97/miner.git
Set-Location .\miner
git submodule sync --recursive
git submodule update --init --recursive
git submodule status
```

The `branch =` values in `.gitmodules` are update hints only. The Git-link commits are the actual reproducibility pins.

## Environment isolation

Do not merge the SLAI and Harnyx environments.

### Lightweight Miner environment

Used for config, artifact generation, report normalization and credential-free tests:

```powershell
# POWERSHELL - Miner root
uv sync --group dev
uv run python .\slai_miner.py status
```

### SLAI development runtime

`adapters/slai.py` imports pinned `external/slai` source but expects the active interpreter to have SLAI's real dependencies. Reusing an already-working SLAI interpreter avoids contaminating it with Bittensor/Harnyx packages:

```powershell
# POWERSHELL - Miner root
G:\GAIA\AI\SLAI\venv\Scripts\python.exe .\slai_miner.py slai-smoke --agent reasoning
```

`SlaiRuntime` owns one SLAI `SharedMemory` and one `AgentFactory`, creates requested agents via `factory.create(...)`, measures initialization/invocation latency, and closes both lifecycles explicitly. SLAI exceptions are not silently swallowed.

### Harnyx official tooling

Use WSL2/Linux for the Harnyx/Bittensor/Docker side:

```bash
# WSL2 / LINUX - <miner>/external/harnyx
uv sync --frozen --all-packages --dev
uv run --frozen --package harnyx-miner harnyx-miner-local-eval --help
uv run --frozen --package harnyx-miner harnyx-miner-local-benchmark --help
```

Docker Desktop should use its WSL2 backend. Miner does not assume native Windows Bittensor operation is production-supported.

## Configuration / secrets

`configs/harnyx.yaml` stores only non-secret Miner policy. `utils/config_loader.py` is a thin binding over SLAI's existing `src.utils.configuration` infrastructure; Miner does not implement a second YAML/cache system.

Never commit provider API keys, Bittensor wallet material, seed phrases, private keys, or hotkey URIs. `.gitignore` excludes `.env`, key formats, wallet/credential paths, SQLite state, benchmark result bundles and local debug logs. Harnyx local `.env`/provider handling and Harnyx platform-stored provider credentials remain separate from Miner configuration.

## SLAI capability policy

See [`docs/slai_agent_selection.md`](docs/slai_agent_selection.md). Initial runtime emphasis is selective: Reasoning and Knowledge are candidates; Planning/Quality/Handler/Observability/Safety require benchmark justification; Adaptive/Learning/LANTRA start as offline experiments; Browser/Reader are not copied into artifacts because Harnyx tools own validator-side retrieval and citation receipts; EvaluationAgent never replaces Harnyx scoring.

## Artifact progression

| Profile | Strategy |
|---|---|
| **B0** | fixed-provider direct Harnyx baseline with separate fast/normal discipline |
| **B1** | B0 + provider/model availability routing via `tooling_info` |
| **B2** | B1 + bounded normal-query decomposition |
| **B3** | routing + Harnyx search + evidence ranking + receipt-backed citations + synthesis |
| **B4** | B3 + decomposition + budget/time-gated verification |
| **B5** | intentionally withheld until repeated benchmark evidence identifies the best selective architecture |

Fast requests bypass decomposition, retrieval and verification in the generated selective artifacts.

Build one candidate:

```powershell
uv run python .\artifact_builder.py b3
```

Generate all B0-B4 profiles:

```powershell
uv run python .\artifact_builder.py all
```

Generate an ablation:

```powershell
uv run python .\artifact_builder.py b4 --disable verification --disable decomposition
```

With the pinned Harnyx uv workspace installed, run Harnyx's own loader/entrypoint/hash validation as part of the build:

```bash
# WSL2 / LINUX - Miner root
uv run python artifact_builder.py b3 --official-validate
```

The builder performs deterministic profile rendering, Python syntax/entrypoint checks, documented upload-subset preflight, current upstream size-limit lookup, secret-literal scanning, SHA-256 recording, optional official Harnyx `load_submittable_agent_bytes` validation, and a manifest containing Miner/SLAI/Harnyx revisions. Platform upload policy remains the ultimate authority.

## Official local evaluation

After Docker and Harnyx's documented provider/scoring credentials are configured:

```bash
# WSL2 / LINUX - Miner root
uv run python slai_miner.py eval \
  --artifact artifacts/harnyx/baseline_agent.py \
  --strategy b0 \
  --mode vs-champion
```

Pin the same completed batch while comparing candidates:

```bash
uv run python slai_miner.py eval \
  --artifact artifacts/harnyx/b3_agent.py \
  --strategy b3 \
  --batch-id <completed-batch-uuid> \
  --mode vs-champion
```

Miner delegates execution, scoring, retries, target-vs-champion comparison and local champion-selection simulation to `harnyx-miner-local-eval`. The official JSON report is retained locally and normalized into `BenchmarkStore`.

## Official benchmark suites

```bash
# WSL2 / LINUX - external/harnyx
uv run --frozen --package harnyx-miner harnyx-miner-local-benchmark --list-suites

# WSL2 / LINUX - Miner root
uv run python slai_miner.py benchmark \
  --artifact artifacts/harnyx/b2_agent.py \
  --strategy b2 \
  --suite <current-suite-slug> \
  --source-batch-id <uuid>
```

Do not publish benchmark reports that Harnyx marks as non-public/plaintext-sensitive.

## BenchmarkStore

`benchmark_store.py` is experiment analytics, not AI memory. It stores run/task IDs, artifact hash/version, strategy, batch/source-batch IDs, fast/normal mode, official scores, cost, tool/token usage, median/p95 runtime, timeout/error/citation/schema failure rates, head-to-head outcomes, local champion-selection result, ablation metadata and Miner/SLAI/Harnyx commits.

Raw Harnyx reports and the SQLite database live under `benchmarks/harnyx/results/` and are ignored because they may contain task text, retrieved evidence and provider output.

```powershell
uv run python .\slai_miner.py runs --limit 10
```

## Tests / CI

Credential-free tests:

```powershell
uv run pytest -q -m "not integration and not harnyx"
uv run ruff check artifact_builder.py benchmark_store.py slai_miner.py adapters utils tests
```

Optional real SLAI integration check:

```powershell
$env:RUN_SLAI_INTEGRATION="1"
G:\GAIA\AI\SLAI\venv\Scripts\python.exe -m pytest -q -m integration
```

Optional official Harnyx loader check:

```bash
RUN_HARNYX_OFFICIAL=1 uv run pytest -q -m harnyx
```

GitHub Actions checks recursive submodules, lint/compile, credential-free tests, secret-file guardrails and deterministic artifact generation without requiring paid provider credentials.

## Deployment gate

No registration or TAO expenditure should be added until all of the following are evidenced:

1. current official artifact validation passes;
2. official Docker-backed local-eval completes;
3. B0 and selective candidates are persisted and compared on a pinned batch;
4. the selective pipeline produces a reward-relevant improvement over B0;
5. the result survives an untouched holdout batch;
6. p95 latency, errors/timeouts and budget use are acceptable;
7. no secret leakage exists;
8. current SN67 registration burn and likely unit economics are manually reviewed.

Any later action capable of spending TAO requires explicit human confirmation.

## Frontend gate

Frontend implementation is intentionally deferred. This repository now has backend code for generation/orchestration/persistence, but this development session has not produced a credentialed Docker-backed official local-eval result. Therefore no UI with invented benchmark data is created. Existing brand assets remain in `frontend/assets/`; after the backend gate passes, the UI must be implemented from the **actual BIMAP source** and real BenchmarkStore data.

## Current limitations

- B0-B4 remain engineering hypotheses until official local-eval/holdout evidence exists.
- Provider/model availability changes; B1-B4 discover permitted routes with `tooling_info`, while B0 is intentionally fixed for baseline stability.
- Structured-output fallback preserves protocol shape where possible but cannot make an unavailable provider semantically correct.
- Full SLAI smoke tests require a real SLAI dependency environment; Miner does not duplicate or silently install it.
- Harnyx platform upload policy remains authoritative even after local preflight and official loader validation.
