# Harnyx SN67 contract snapshot

This document records the upstream contract inspected for the Miner integration. It is a traceability aid, not a replacement for Harnyx source code.

- **Pinned Harnyx commit:** `a8fd4998d0aadda1e5099faeaacba9948a8de6b5`
- **Miner SDK:** `0.1.23` (`packages/miner-sdk/pyproject.toml`)
- **Python:** `>=3.11,<3.12` for the miner SDK/sandbox toolchain.
- **Artifact:** one UTF-8 Python source file, maximum **1,000,000 bytes**. The authority is `packages/commons/src/harnyx_commons/sandbox/agent_staging.py::MAX_AGENT_BYTES`; Miner reads this constant from the pinned source instead of treating this document as runtime authority.
- **Entrypoint:** `async def query(query: Query, context: ContextSnapshot) -> Response`, registered with `@entrypoint("query")`. The context-aware form is the current recommended contract (`packages/miner-sdk/README.md`, `harnyx_miner_sdk.decorators`).
- **Query:** strict `text`, `fast`, and optional `output_schema` contract in `packages/miner-sdk/src/harnyx_miner_sdk/query.py`.
- **Structured output:** JSON Schema Draft 2020-12, local references only, 80,000 compact JSON characters (`packages/miner-sdk/src/harnyx_miner_sdk/structured_output.py`).
- **Response:** exactly one of `text` or `output`; optional `note`; at most 200 citation refs and 400 materialized evidence segments (`query.py`).
- **Evidence:** citation refs must use Harnyx tool `receipt_id` + `result_id`. Prose pointers are exact one-based `[[n]]` markers.
- **Fast scoring:** correctness-only component precision/recall F1; citations are accepted but omitted from the fast judge and provide no scoring benefit.
- **Normal scoring:** current miner-task scoring uses citation-aware pairwise comparison against the reference answer; the current total is the comparison score.
- **Hosted tools:** `search_web`, `fetch_page`, `llm_chat`, `embed_text`, `tooling_info`. Current public provider/model availability must be read from `tooling_info` at runtime rather than assumed permanent.
- **Sandbox:** Linux Docker, seccomp/resource isolation, 1 GiB container limit, independent query workers, no new miner-created processes/threads. Tool calls are proxied through the trusted host.
- **Tool concurrency:** at most 20 in-flight tool calls per evaluation session; queued calls still consume the invocation deadline.
- **Batch shape:** current source batches start with 10 qualifying tasks and add 20 shared main tasks for admitted participants; final selection uses all 30.
- **Champion rules:** for data version >=8 the platform ranking cascade permits replacement through +10 percentage-point score margin, >=10% cost improvement without score/runtime regression, or >=10% and >=1,000 ms runtime improvement without score/cost regression. Historical data versions replay their historical rules. Authority: `packages/commons/src/harnyx_commons/miner_task_champion.py` and `miner_task_ranking.py`.
- **Novelty/rewards:** the current participant/champion allocation is versioned and implemented in Harnyx commons. Miner never reimplements it; official local-eval supplies the simulated selection result.
- **Upload policy:** the current upload AST subset rejects direct `eval`, `exec`, `compile`, dynamic reflection/import machinery, pattern matching, `global`/`nonlocal`, and other documented unsupported constructs. Authority: current Harnyx miner/upload policy source and `miner/README.md`.
- **Black-box endpoint mining:** current `miner/README.md` marks it **not yet released** and states initial black-box emission remains zero. This repository therefore targets the rewarded Python-artifact path.

If `external/harnyx` is updated, rerun the contract tests and update this snapshot only after reviewing the corresponding upstream source changes.
