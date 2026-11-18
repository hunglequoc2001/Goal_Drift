# Exp02 parser steps (24 rows)
Question: is `parsed_action` one action the agent actually executed, and which semantic category fits it?
- `human_is_agent_action`: yes / no / unclear
- `human_expected_category`: one of search, view, edit, test, run, vcs, install, submit, other
- `human_notes`: free text. Estimated time: 25 min.

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).
