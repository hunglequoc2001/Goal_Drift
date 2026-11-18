"""Build a blind copy of human_review/ for raters.
Removed: sheet_ai_review.csv, PRIORITY_SPOTCHECK.csv, every automatic/AI verdict column, outcome columns (resolved),
and model identities (runs -> M1..M5, C1 trajectories reduced to messages with model names replaced by "agent").
Long text cells (C1 submissions) are moved to files so the sheets open cleanly in a spreadsheet program.
Every blind sheet has `row_id` (= row index of the original sheet.csv) and a `rater` column.
Writes <out>/ (package, includes REVIEWER_GUIDE.md copied from human_review/) and <key>/ (unblinding key; never ship).
Usage: python build_blind_package.py <out_dir> <key_dir>
"""
import json
import re
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]; HR = ROOT / "human_review"
out, key = Path(sys.argv[1]), Path(sys.argv[2])
shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True); key.mkdir(parents=True, exist_ok=True)


def sheet(part, keep, human, extra=None):
    s = pd.read_csv(HR / part / "sheet.csv")
    b = pd.DataFrame({"row_id": range(len(s))})
    for c in keep:
        b[c] = s[c].values if c in s else (extra[c] if extra is not None else "")
    b["rater"] = ""
    for c in human:
        b[c] = ""
    (out / part).mkdir(exist_ok=True)
    b.to_csv(out / part / "sheet.csv", index=False)
    return s


# B2 / C2: item files are pure task text; drop auto columns (C2 auto_summary is generator-written)
for part, human in [("exp03_b2_fidelity", ["human_same_requirements", "human_information_added",
                                           "human_information_removed", "human_natural", "human_notes"]),
                    ("exp03_c2_validity", ["human_change_meaningful", "human_requirement_unambiguous",
                                           "human_tests_match_requirement", "human_revised_fix_correct", "human_notes"])]:
    s = sheet(part, ["item", "instance_id", "folder"], human)
    shutil.copytree(HR / part / "items", out / part / "items")

# Exp02 paired tasks: blind the five runs
s = pd.read_csv(HR / "exp02_paired_tasks/sheet.csv")
runs = sorted(s.run.unique()); code = {r: f"M{i + 1}" for i, r in enumerate(runs)}
pd.DataFrame({"run": runs, "code": [code[r] for r in runs]}).to_csv(key / "exp02_run_codes.csv", index=False)
(out / "exp02_paired_tasks/items").mkdir(parents=True)
folder_of = {}
for d in sorted((HR / "exp02_paired_tasks/items").iterdir()):
    iid = (d / "instance_id.txt").read_text().strip()
    t = out / "exp02_paired_tasks/items" / d.name; t.mkdir()
    for f in ["issue.txt", "reference_fix.diff", "instance_id.txt"]:
        shutil.copy(d / f, t / f)
    for r in runs:
        if (d / f"submitted_{r}.diff").exists():
            shutil.copy(d / f"submitted_{r}.diff", t / f"submitted_{code[r]}.diff")
    folder_of[iid] = f"exp02_paired_tasks/items/{d.name}"
b = pd.DataFrame({"row_id": range(len(s)), "folder": s.instance_id.map(folder_of).values,
                  "model_code": s.run.map(code).values, "repo": s.repo.values, "repo_language": s.repo_language.values,
                  "rater": "", "human_localisation_correct": "", "human_strategy_note": ""})
assert b.folder.notna().all()
b.to_csv(out / "exp02_paired_tasks/sheet.csv", index=False)

# Parser-step sheets: hide parser categories, outcome and system names
sheet("exp02_parser_steps", ["instance_id", "repo", "step_idx", "parsed_action", "obs_excerpt"],
      ["human_is_agent_action", "human_expected_category", "human_notes"])
sheet("exp01v_parser_steps", ["author_row", "author_step_example", "role_step_example"],
      ["human_is_role_step_a_real_agent_action", "human_notes"])

# C1: one folder per item, model-free trajectory
s = pd.read_csv(HR / "exp03_pilot_c1/sheet.csv")
names = sorted(s.model.unique(), key=len, reverse=True)
pat = re.compile("|".join(re.escape(n) for n in names) + r"|hosted_vllm/\S+?(?=[\"'\s])", re.I)
folders = []
for i, r in s.iterrows():
    f = f"exp03_pilot_c1/items/{int(r['item']):03d}_{r.instance_id}"; folders.append(f)
    t = out / f; t.mkdir(parents=True)
    tj = json.loads((HR / "exp03_pilot_c1/trajectories" / Path(r.traj_path).name).read_text())
    (t / "trajectory.json").write_text(pat.sub("agent", json.dumps({"messages": tj["messages"]}, indent=1)))
    (t / "submission.txt").write_text("" if pd.isna(r.submission) else str(r.submission))
    (t / "run_info.txt").write_text(f"exit_status: {r.exit_status}\n")
b = pd.DataFrame({"row_id": range(len(s)), "item": s["item"].values, "instance_id": s.instance_id.values,
                  "folder": folders, "rater": ""})
for c in ["human_recognized_already_fixed", "human_verified_by_running", "human_edit_necessary", "human_edit_effect",
          "human_format_failure_only", "human_notes"]:
    b[c] = ""
b.to_csv(out / "exp03_pilot_c1/sheet.csv", index=False)
leak = [p for p in (out / "exp03_pilot_c1/items").rglob("*") if p.is_file() and pat.search(p.read_text())]
assert not leak, leak

shutil.copy(HR / "REVIEWER_GUIDE.md", out / "REVIEWER_GUIDE.md")
bad = [p for p in out.rglob("*") if p.is_file() and re.search(r"ai_review|PRIORITY_SPOTCHECK|auto_", p.name)]
assert not bad, bad
print("ok", sum(1 for _ in out.rglob("*") if _.is_file()), "files")
