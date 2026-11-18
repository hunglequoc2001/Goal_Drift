# Human review package (BCM construct-validity project)

Nothing here has been labelled by a human yet. Each folder has a CODEBOOK.md and a sheet.csv; `index.csv` lists progress.

Priority for the paper: (1) exp03_c2_validity and exp03_b2_fidelity (they validate the full-study manipulations), (2) exp03_pilot_c1, (3) exp02_paired_tasks, (4) the two parser-step sheets.

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).
