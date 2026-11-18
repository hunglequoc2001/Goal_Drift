# Provenance and comparability decision (Exp02)

Full per-run table: `data/manifests/provenance_by_run.csv`; exit-status attrition: `results/tables/attrition_exit_status.csv`;
config diff across runs: `data/manifests/smoke_config_diff.tsv`.

## What is identical across all 13 analysed runs (verified from `replay_config` in every trajectory)
SWE-agent 1.1.0, function-calling parser, the same system/instance/next-step templates, the same tool
bundles (`registry`, `edit_anthropic`, `submit`), temperature 1.0, the same Docker images per task
(Modal deployment), and the same task statements (SWE-bench Pro v1 public set). swe-rex is 1.2.2, except
the 100-call "paper" runs, which use 1.2.0.

## What differs, and how it is handled
| Factor | Values | Handling |
|---|---|---|
| Call limit / cost limit | 250 / none (leaderboard runs, README: "all run with the same config"); 100 / $2–4; 50 / $1 | **Cohorts are defined by config and never pooled.** Primary = 250-call runs; secondary paper-50; tertiary paper-100 (Gemini-paper has $2 vs $4, flagged) |
| Context window | 128k (GPT-5, GLM), 200k (Claude), 1M/900k (Gemini) | inherent to the model; confounded with model and reported |
| Reasoning effort | GPT-5 `high`; others default | confounded with model and reported |
| Within-run deviations | Sonnet-4.5: **109/730 trajectories with an 85-call limit**; Gemini: 116/730 with a 900k context | sensitivity cohort `primary5_cfgclean` drops these 224 tasks for every model |
| Folder labels | `claude-opus-4-1-paper` holds **Claude Sonnet 4** and `claude-sonnet-4-paper` holds **Claude Opus 4.1** (`replay_config.agent.model.name`). The official eval for "claude-sonnet-4-paper" agrees 98.3% with S3 "claude-opus-4-1-paper" outcomes | model identity from `replay_config`; the swap is reported here |
| Hidden reasoning | thought text empty in 98% of GPT-5, 97% of gpt-oss and GPT-5-high action messages, 0–28% for others | defines why R0 (authors' loader) fails asymmetrically; role-aware R2 is unaffected |
| Rejected commands | SWE-agent drops malformed commands (not executed, `execution_time` 0) from history but keeps them in `trajectory[]`; mostly GPT-5 (40% of its trajectories, 1–12 each) | R2 counts executed tool calls only (the model's effective action sequence); documented representation choice |

## Outcomes
Rule: `(FAIL_TO_PASS ∪ PASS_TO_PASS) ⊆ PASSED` (official `swe_bench_pro_eval.py:555-558`) on the archived
`_output.json`, with v1 test lists. Missing eval file = unresolved, as in the official script.
Agreement with the official `eval_results.json` (`results/tables/outcome_validation.csv`):
GPT-5 716/729, Sonnet-4.5 719/730, Sonnet-4 554/562, gpt-oss 717/728, GPT-4o 612/619. The 32 primary
disagreements are all "official False, recomputed True" and concentrate on **14 tasks shared across models**
(NodeBB, element-web). The newer `default` test lists explain them worse (agreement drops to 640–654),
so the cause is instance-level evaluation in the official run, not model behaviour. **Decision: these 14 tasks
are excluded from every cohort** (`data/manifests/disputed_instances.csv`), so all models are labelled by
one rule. Haiku-4.5, GLM-4.5 and Gemini have no official file. Their labels use the same validated rule.

## Matched cohorts (pre-registered before any Exp02 BCM was computed)
| Cohort | Models | Matched tasks | Notes |
|---|---|---|---|
| **primary5** | GPT-5, Sonnet-4.5, Haiku-4.5, GLM-4.5 (open-weight), Gemini-2.5-Pro | **715** | main analysis |
| primary6 | + Sonnet-4 | 551 | Sonnet-4 run has only 563 trajectories |
| primary5_cfgclean | primary5 | 496 | drops config-deviant tasks |
| paper50 | GPT-5-high, gpt-oss-120b (open), Kimi-K2 (open) | 713 | proprietary vs open-weight under one config |
| paper100 | Sonnet-4, Opus-4.1, Gemini-2.5-Pro ($2), GPT-4o | 623 | Opus outcome labels agree only 83% with the official file of the same name (a different run?), flagged |

Attrition: all trajectories present are kept. Failures, errors, cost exits and empty submissions are
outcomes, not exclusions. No trajectory was corrupted (all 9,139 parsed). Exit-status distributions per run
are in `attrition_exit_status.csv`. E.g. GPT-5: 438 clean submits, 78 command-timeout, 63 context exits,
14.7% empty submissions.

## Is any cross-model claim still confounded?
Yes. Even in primary5, "model" bundles weights, provider API, context window, reasoning settings and
tokenizer, and each model has **one attempt per task**. Cross-model contrasts are descriptive comparisons of
systems under a common scaffold. They are not causal effects of model identity, and they say nothing
about within-model repeatability. GLM-4.5 vs the rest is the only open-vs-proprietary contrast in the
primary cohort (n = 1 open model). paper50 adds a 1-vs-2 contrast under a different budget.
