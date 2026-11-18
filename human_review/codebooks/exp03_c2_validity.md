# Exp03 C2 (changed requirement) validity
C2 = original issue + an appended maintainer update that changes the required behaviour. Executable checks already
passed: unchanged repo fails, revised reference fix passes, original fix fails the revised tests. You judge meaning.
Files in `items/<id>/`: issue.txt, requirement.txt, gold_original.diff, gold_revised.diff, tests_original.diff,
tests_revised.diff.
- `human_change_meaningful`: yes (a real, plausible design change) / trivial (cosmetic) / no
- `human_requirement_unambiguous`: yes (only one reasonable implementation of the new behaviour) / no / unclear
- `human_tests_match_requirement`: yes (the revised tests check exactly what the update says, nothing hidden) / no / unclear
- `human_revised_fix_correct`: yes / no / unclear
- `human_notes`. Estimated time: 5-8 min per item.

Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4).
