# Parser validation (Exp02)

Code: `src/bcm02/parse.py` (tests: `tests/test_parse.py`, 4 passing); validation script
`scripts/parser_validation.py`; outputs `results/tables/parser_*.csv`, `results/validation/*`.

## Representations of the same `.traj` record
| | Step = | Source of the definition |
|---|---|---|
| R0 | `content` of history messages with `message_type=="action"`, non-empty | literal BCM-author SWE-smith loader |
| R1 | every history message with text (system prompt, task, observations, assistant turns) | literal BCM-author Nebius loader |
| **R2** | each executed model tool call (SWE-agent's own `action` rendering), with its observation | role-aware (primary) |
| R3 | R2 steps labelled by a tool-semantic categoriser | alternative feature set |

## Programmatic invariants (all 9,139 trajectories; `parser_invariants.csv`)
- R2 steps = tool-call action messages in **100%** of trajectories for every run. 0 multi-call messages.
  Harness exit messages (no tool call, e.g. "Exit due to cost limit") are excluded: 47–680 per run.
- R2 vs non-empty `trajectory[].action`: equal in 96–100% of trajectories for every run except GPT-5
  (60%) and GPT-5-high (67%). Inspection shows the extra trajectory entries are commands SWE-agent
  rejected before execution (malformed quoting; `execution_time` 0.0, empty observation). They are
  dropped from the model's history and re-queried. R2 follows the executed history. Max per-trajectory
  difference: 12.
- Zero-step trajectories: **R0: GPT-5 427/730 (58%), GPT-5-high 97/730, gpt-oss 47/728, GPT-4o 6/643, all
  others 0.** The cause is the share of action messages with empty thought text: 98.2% (GPT-5), 96.8%
  (GPT-5-high), 96.7% (gpt-oss) vs 1.7–28% for others. R2: ≤14 per run (Gemini 14: trajectories that
  ended before any tool call). R1: 0.
- Median steps per trajectory, e.g. GPT-5: R0 0, R1 54, R2 52; Sonnet-4.5: R0 55, R1 134, R2 77.

## Role leakage (`parser_role_leakage.csv`)
Fraction of R2 steps containing the system prompt, `<uploaded_files>`, `<pr_description>`, starting with
`OBSERVATION`, or empty: **0.0000** for every run (max 0.0001 for Gemini-paper, where the model echoed a tag).
Problem-statement text (first 200 chars) inside a sampled step (20k steps): 0. By contrast, about 50% of R1
"steps" are non-agent messages by construction.

## Category distributions (`parser_category_distribution.csv`, `parser_regex_vs_semantic_crosstab.csv`)
The BCM paper's regex categoriser labels **42–66%** of real tool actions as "other". It catches only 29%
of semantic `view` steps (e.g. `str_replace_editor view /app/x.go`), 32% of `edit` steps and 19% of `test`
steps. Semantic categories show large model differences: Gemini 50% edit / 3% test; GPT-5 30% run / 3%
test; Claude 12% test. The regex features therefore carry little of this structure.

## Sample audit and human review
- `results/validation/audit_40.csv`: 40 seeded trajectories stratified by run × outcome (primary5: 3 resolved
  + 3 unresolved each; paper50: 2 + 2 each, truncated to 40). One random R2 step each, with observation
  excerpt and both categorisations.
- `results/validation/human_review_sheet_24.csv`: the first 24 rows with empty columns
  `human_is_agent_action`, `human_expected_category`, `human_notes`. **Not yet annotated by a human.**
  The AI agent spot-read the rows while writing this report. That is not human validation and is not
  reported as such.
- `results/validation/paired_tasks_40.csv`: 40 seeded tasks × 5 primary models with observable labels
  (reference-file recall of the submitted patch, extra files, ran tests/scripts, resolved) and empty human
  columns for localisation correctness and strategy notes.

## Normalisation caveat
Length features (mean/max action length) compare SWE-agent's renderings of tool calls across models. All
models use the same renderer, but models differ in how much code they pass inside a call (Kimi median max
action length 5,053 chars vs gpt-oss 617). Length features therefore partly encode editing style
(whole-file `create` vs targeted `str_replace`). They are not normalised to tokens, and the R3 feature set
omits length entirely.
