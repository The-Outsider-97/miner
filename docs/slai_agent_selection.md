# SLAI agent selection for Harnyx SN67

The pinned SLAI commit is `44e3edf73fe6b12ccf036b0727d4d4ab4b8e7604`.
Its `AgentFactory.DEFAULT_AGENT_SPECS` registers 21 agents. Miner considers every
registered agent, but Harnyx validator score, latency, and cost decide whether a
capability remains. Full SLAI runs only in Miner's development environment;
validator artifacts contain distilled strategy plus the public Harnyx SDK.

Classifications:

- **A — runtime-critical:** required in the Miner development hot path.
- **B — conditional runtime:** invoked only for a justified task/experiment class.
- **C — benchmark/offline:** analysis, learning, tuning, or ablation outside the submitted artifact.
- **D — infrastructure:** indirect runtime infrastructure rather than answer-generation policy.
- **E — not justified:** no current reward-relevant role that offsets overlap, latency, dependency, or cost.

No SLAI agent is currently category A. `ReasoningAgent` and `KnowledgeAgent` are
the only category-B candidates with explicit Miner adapter operations. This is
intentional: their value must be demonstrated before their strategies are
distilled into a submitted artifact.

| Agent | Class | Current Miner role | Execution boundary | Inclusion / exclusion basis |
|---|---|---|---|---|
| AdaptiveAgent | C | Strategy/adaptation experiments only | Offline | Torch/RL overhead; no measured SN67 hot-path gain yet. |
| AlignmentAgent | E | None | — | Constitutional/value-alignment subsystem does not currently map to an SN67 scoring advantage and adds torch-backed overhead. |
| BrowserAgent | E | None | — | Harnyx `search_web`/`fetch_page` own sandbox network access and receipt-backed evidence. |
| EvaluationAgent | C | Optional experiment analysis only | Offline | Harnyx local-eval/local-benchmark remain scoring authority; SLAI evaluation must not reinterpret validator score. |
| ExecutionAgent | E | None | — | Robotics/action execution semantics do not match the text research-miner contract. |
| HandlerAgent | C | Failure-policy experiments | Offline | Possible development utility, but no measured benefit justifies runtime invocation. |
| KnowledgeAgent | B | `SlaiRuntime.retrieve()` for retrieval/ranking experiments | Development runtime | Can test local knowledge/ranking value; live artifact citations must still originate from Harnyx receipts. |
| LanguageAgent / LANTRA | C | Routing/decomposition/ranking experiments | Offline | Must be benchmarked before any final-synthesis role; stronger hosted providers remain available through Harnyx. |
| LearningAgent | C | Policy-learning experiments | Offline | Training/meta-learning belongs outside validator execution. |
| NetworkAgent | E | None | — | Harnyx's trusted tool proxy owns provider/network transport inside the sandbox. |
| ObservabilityAgent | C | Optional experiment analysis | Offline | Official Harnyx reports plus BenchmarkStore already own Miner experiment evidence. |
| PerceptionAgent | E | None | — | Current Harnyx query contract is text/structured-output oriented; multimodal torch stack adds unjustified cost. |
| PlanningAgent | C | Structured-task decomposition experiments | Offline | Only useful when a real planning task contract exists; generic use risks duplicating ReasoningAgent. |
| PrivacyAgent | C | Optional local data/privacy audit | Offline | Useful for local evidence-handling audits, not a default answer-generation step. |
| QNNAgent | E | None | — | No demonstrated relevance to SN67 reward or query execution. |
| QualityAgent | C | Dataset/workflow quality experiments | Offline | Does not replace Harnyx answer scoring or deterministic schema/citation validation. |
| ReaderAgent | E | None | — | Local reader state cannot create authoritative Harnyx citation receipts. |
| ReasoningAgent | B | `SlaiRuntime.reason()` for reasoning/decomposition experiments | Development runtime | Candidate only when measured score gain justifies initialization/invocation latency. |
| SafetyAgent | C | Reliability/safety ablations | Offline | Retain only if benchmark evidence shows reward-relevant reliability benefit. |
| SimulationAgent | E | None | — | Scenario/numerical simulation is not part of the general SN67 research-answer hot path. |
| VerificationAgent | C | Formal-task experiments | Offline | Potential value for explicit formal properties, but no justification for generic runtime use. |

## Infrastructure

`CollaborativeAgent` is not a registered default `AgentFactory` agent at the
pinned commit. The collaborative subsystem provides `SharedMemory`, which Miner
uses as category-D infrastructure when SLAI agents are instantiated. `SlaiRuntime`
constructs agents through `AgentFactory`, reuses the process-scoped
`SharedMemory`, measures initialization/invocation latency, shuts down the
factory, and clears experiment values without closing SLAI's singleton memory
fabric.

AgentFactory's own cache/observability/lifecycle infrastructure is also reused;
Miner does not reimplement it.

## Artifact boundary

None of the SLAI classes above are imported by the submitted artifact. The
artifact contains only standalone policy that is valid under the pinned Harnyx
SDK/sandbox contract.

- **B0** fixed-provider direct Harnyx baseline with separate fast/normal prompts.
- **B1** B0 + runtime provider/model availability routing via `tooling_info`.
- **B2** B1 + bounded normal-query decomposition.
- **B3** routing + Harnyx search + deterministic evidence ranking + receipt-backed citations + synthesis.
- **B4** B3 + decomposition + request-local budget/time-gated verification.
- **B5** intentionally withheld until repeated local-eval and holdout evidence identifies the best selective architecture.

`artifact_builder.py --disable <component>` generates controlled ablations
without editing source. A component remains out of the candidate unless its
reward-relevant gain justifies its cost and latency.
