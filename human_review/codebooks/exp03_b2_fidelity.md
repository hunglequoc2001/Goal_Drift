# Exp03 B2 (task-preserving rewrite) fidelity
B2 rewrites the prose of the issue; code, identifiers, paths, numbers and quoted strings are kept byte-identical by
construction (placeholder masking) and were checked automatically. Read `original` and `rewrite` side by side
(files in `items/`).
- `human_same_requirements`: yes (a developer would implement exactly the same fix from either text) / no / unclear
- `human_information_added`: none / hint (adds a diagnosis or fix suggestion) / other
- `human_information_removed`: none / detail (loses an expected/observed behaviour, a step, a condition) / other
- `human_natural`: yes (reads like a real issue) / no
- `human_notes`. Estimated time: 3-4 min per item.

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).
