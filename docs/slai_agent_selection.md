# SLAI agent selection for Harnyx SN67

The Harnyx validator score, not agent count, decides whether a capability remains. Full SLAI runs only in Miner's development environment; validator artifacts contain distilled strategy plus the public Harnyx SDK.

| SLAI capability | Classification | Miner use |
|---|---|---|
| ReasoningAgent | conditionally useful | Development experiments; B2/B4 decomposition only if score gain justifies latency/cost. |
| KnowledgeAgent | conditionally useful | Offline retrieval/ranking experiments; live artifact evidence still comes from Harnyx receipt-backed tools. |
| PlanningAgent | offline/benchmark first | Use only with real structured Task contracts; Miner does not fabricate them from arbitrary text. |
| QualityAgent | offline/benchmark first | Data/workflow quality, not a substitute for Harnyx answer scoring. |
| BrowserAgent | unnecessary in artifact | Harnyx `search_web`/`fetch_page` own sandbox network access and receipts. |
| ReaderAgent | unnecessary in artifact | Local document state cannot produce Harnyx citation receipts. |
| HandlerAgent | conditionally useful in development | Failure-policy experiments only after measurable benefit. |
| ObservabilityAgent | offline/benchmark | Official Harnyx reports + BenchmarkStore already own experiment evidence. |
| AdaptiveAgent | offline/benchmark | Potential future strategy optimization; no initial hot-path justification. |
| LearningAgent | offline/benchmark | Potential future policy learning, not an assumed online reward loop. |
| LanguageAgent / LANTRA | offline/benchmark | Candidate for routing/decomposition/ranking; not assumed competitive for final synthesis. |
| SafetyAgent | conditionally useful | Only if reward-relevant reliability benefit is demonstrated. |
| CollaborativeAgent / SharedMemory | infrastructure | Shared runtime for AgentFactory-created development agents; never copied into sandbox artifact. |
| EvaluationAgent | offline only | Harnyx local-eval/local-benchmark remain scoring authority. |

## Artifact progression

- **B0** fixed-provider direct Harnyx baseline with separate fast/normal prompts.
- **B1** B0 + runtime provider/model availability routing via `tooling_info`.
- **B2** B1 + bounded normal-query decomposition.
- **B3** routing + Harnyx search + deterministic evidence ranking + receipt-backed citations + synthesis.
- **B4** B3 + decomposition + budget/time-gated verification.
- **B5** intentionally withheld until repeated local-eval and holdout evidence identifies the best selective architecture.

`artifact_builder.py --disable <component>` generates controlled ablations without editing source. A component remains removed unless its reward-relevant gain justifies its cost and latency.
