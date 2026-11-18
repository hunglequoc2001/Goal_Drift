"""Inter-rater agreement for a human-review sheet that two raters labelled on overlapping rows.
Convention: the two raters' copies are <sheet>.<initials>.csv (same rows/item ids); kappa per human_* column on the
rows both labelled. Usage: python review_agreement.py <sheet_rater1.csv> <sheet_rater2.csv>
"""
import sys

import pandas as pd
from sklearn.metrics import cohen_kappa_score

a, b = (pd.read_csv(f).set_index("item") for f in sys.argv[1:3])
for c in [c for c in a.columns if c.startswith("human_") and c != "human_notes"]:
    both = a[c].notna() & b[c].reindex(a.index).notna()
    if both.sum() >= 2:
        x, y = a.loc[both, c].astype(str), b[c].reindex(a.index)[both].astype(str)
        print(f"{c}: n={both.sum()} agreement={(x == y).mean():.2f} kappa={cohen_kappa_score(x, y):.2f}")
