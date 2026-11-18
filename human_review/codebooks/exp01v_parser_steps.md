# Exp01-V parser steps (24 rows)
Question: is `role_step_example` a real agent action (a command/tool call the agent issued), and is the author parser's
`author_step_example` one? Context: Exp01-V V4 (role-aware parser vs authors' loader).
- `human_is_role_step_a_real_agent_action`: yes / no / unclear
- `human_notes`: free text (e.g. "author step is narration, not an action").
Estimated time: 20 min.

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).
