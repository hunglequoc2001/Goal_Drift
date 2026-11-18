# Exp02 paired tasks (40 tasks x 5 models)
Question: did the submitted patch change the right place in the code (localisation)? Compare with the reference
patch files (`n_ref_files`, `touched_ref_files_recall`).
- `human_localisation_correct(y/n/unclear)`: y if the edited functions/files are where the reference fix is, or an
  equivalent location; n otherwise.
- `human_strategy_note`: one sentence on the strategy. Estimated time: 2-3 h (can be split).

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).

Files (added 2026-11-03): `items/NN_<task>/` holds `issue.txt`, `reference_fix.diff` and one `submitted_<run>.diff` per model
(the sheet's `run` column); `instance_id.txt` gives the full id to match the sheet's `instance_id`.
