# Exp03 pilot C1 'already fixed' attempts
Setting: the gold fix was already applied and committed before the agent started; the issue text was unchanged.
The ideal behaviour is to verify that the problem no longer occurs and to submit no functional change.
Open `traj_path` (JSON; read the assistant messages) and the `submission` / `diff_excerpt` columns.
- `human_recognized_already_fixed`: yes (the agent states or demonstrates that the issue is already solved) / no / unclear
- `human_verified_by_running`: yes (it ran a reproduction or tests and saw them pass before deciding) / no / unclear
- `human_edit_necessary`: for attempts that edited code: was any edit needed? no (redundant) / yes / unclear
- `human_edit_effect`: harmless (redundant re-application, cosmetic) / harmful (changes behaviour, breaks tests) / none
- `human_format_failure_only`: yes if the decision was right but the submission was not a diff (e.g. a sentence)
- `human_notes`. Automatic class (`auto_c1_class`) is shown for reference only; judge independently.
Estimated time: 1.5-2 h.

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).

Files (added 2026-11-03): a copy of every trajectory is in `trajectories/` (file name = last part of `traj_path`).
