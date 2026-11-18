"""Stage F manual-validation sample: 30 records per source, stratified by system and length.

Writes
  results/validation/F_sample.csv          sampled records (ids, system, length tercile)
  results/validation/F_steps.csv           every role-aware step with regex and semantic categories
  results/validation/F_sheet.md            raw agent turns next to parsed steps, for reading
The semantic labeller is a second, independent rule set keyed on the executed tool/verb
(not on free-text regexes); disagreements are what the annotator reviews by hand.
"""
import json
import re

import numpy as np
import pandas as pd

from . import ROOT, load_config
from .features import categorize

OUT = ROOT / "results/validation"
FIRST = re.compile(r"^(?:cd\s+\S+\s*(?:&&|;)\s*)*(\S+)(?:\s+(\S+))?", re.S)


def semantic_category(cmd):
    m = FIRST.match(cmd.strip())
    if not m:
        return "other"
    a, b = m.group(1), (m.group(2) or "")
    if a == "str_replace_editor":
        return {"view": "view", "str_replace": "edit", "create": "edit", "insert": "edit",
                "undo_edit": "edit"}.get(b, "other")
    if a in ("submit", "exit"):
        return "submit"
    if a in ("cat", "head", "tail", "open", "goto", "scroll_up", "scroll_down", "less", "nl", "more"):
        return "view"
    if a == "sed":
        return "edit" if "-i" in cmd.split("\n")[0] else "view"
    if a in ("grep", "egrep", "rg", "find", "find_file", "search_dir", "search_file", "ls", "tree", "locate", "ag"):
        return "search"
    if a == "git" and b == "grep":
        return "search"
    if a in ("edit", "create", "patch", "insert") or (a == "git" and b in ("apply", "checkout")):
        return "edit"
    if a in ("pytest", "tox", "nosetests") or re.search(r"-m\s+(pytest|unittest)|\bruntests?\b|\btest_\w+\.py\b|tests?/", cmd.split("\n")[0]):
        return "test"
    if a in ("echo", "printf") and ">" in cmd.split("\n")[0]:
        return "edit"
    if a in ("python", "python3"):
        return "run"
    return "other"


def main():
    cfg = load_config()
    n_per = cfg["experiments"]["F_manual_validation_per_source"]
    rng = np.random.default_rng(cfg["experiments"]["F_manual_validation_seed"])
    OUT.mkdir(parents=True, exist_ok=True)
    fr = pd.read_parquet(ROOT / "results/tables/features_role_aware.parquet")
    picks = []
    for src, g in fr.groupby("source"):
        g = g.copy()
        g["len_tercile"] = pd.qcut(g["n_actions"].rank(method="first"), 3, labels=["short", "mid", "long"])
        strata = list(g.groupby(["agent_system", "len_tercile"], observed=True))
        base, extra = divmod(n_per, len(strata))
        order = rng.permutation(len(strata))
        for k, si in enumerate(order):
            key, sg = strata[si]
            take = base + (1 if k < extra else 0)
            picks.append(sg.loc[rng.choice(sg.index, min(take, len(sg)), replace=False)])
    sample = pd.concat(picks)
    sample[["author_row", "source", "source_row_id", "instance_id", "agent_system", "len_tercile",
            "n_actions", "resolved"]].to_csv(OUT / "F_sample.csv", index=False)
    raw = pd.read_parquet(ROOT / "data/interim/cohort_raw.parquet",
                          filters=[("author_row", "in", sample["author_row"].tolist())])
    steps_rows, sheet = [], ["# F manual-validation sheet\n"]
    for r in raw.sort_values(["source", "agent_system", "author_row"]).itertuples():
        steps = json.loads(r.role_steps)
        obs = json.loads(r.role_obs_head)
        author_steps = json.loads(r.author_steps)
        if r.source == "swe_smith":
            msgs = json.loads(r.raw)
            agent_turns = [m for m in msgs if m.get("role") == "assistant"]
            agent_text = [(m.get("action") or m.get("content") or "") if isinstance(m.get("content"), str) or m.get("action")
                          else str(m.get("content")) for m in agent_turns]
        else:
            msgs = json.loads(r.raw)
            agent_turns = [m for m in msgs if m.get("role") == "ai"]
            agent_text = [m.get("text") or "" for m in agent_turns]
        sheet.append(f"\n## row {r.author_row} | {r.source} | {r.agent_system} | {r.instance_id}\n"
                     f"raw messages {len(msgs)}, agent turns {len(agent_turns)}, author steps {len(author_steps)}, "
                     f"role-aware steps {len(steps)}\n")
        for i, s in enumerate(steps):
            rc, sc = categorize(s), semantic_category(s)
            steps_rows.append({"author_row": r.author_row, "source": r.source, "agent_system": r.agent_system,
                               "step": i, "command": s[:300], "regex_category": rc, "semantic_category": sc,
                               "obs_head": obs[i][:200] if i < len(obs) else ""})
            flag = "" if (rc == sc or (rc == "other" and sc in ("other", "run", "submit"))) else "  <-- DISAGREE"
            sheet.append(f"- [{i}] `{s[:140].replace(chr(10), ' ⏎ ')}` regex={rc} semantic={sc}{flag}")
        tail = agent_text[-1][-300:].replace("\n", " ⏎ ") if agent_text else ""
        sheet.append(f"\n  last agent turn (tail): `{tail}`\n")
    pd.DataFrame(steps_rows).to_csv(OUT / "F_steps.csv", index=False)
    (OUT / "F_sheet.md").write_text("\n".join(sheet))
    st = pd.DataFrame(steps_rows)
    print(len(sample), "records", len(st), "steps")
    print(pd.crosstab([st["source"], st["semantic_category"]], st["regex_category"]))


if __name__ == "__main__":
    main()
