"""Build the human-review package (project_791/human_review/). Nothing in it is labelled; every human_* column is empty.

Parts
  exp01v_parser_steps   existing Exp01-V sheet (24 rows), copied verbatim + codebook
  exp02_parser_steps    existing Exp02 sheet (24 steps), copied verbatim + codebook
  exp02_paired_tasks    existing Exp02 paired-task sheet (40 tasks x 5 models), copied verbatim + codebook
  exp03_pilot_c1        stratified sample of pilot C1 ('already fixed') attempts: every text submission, and up to 8 per
                        other class (seeded), with submission, final assistant message and diff excerpts
  exp03_b2_fidelity     B2 rewrites: every staging task + a seeded sample of 30 confirmatory tasks, side by side
  exp03_c2_validity     C2 changed requirements: every staging task + a seeded sample of 30 confirmatory tasks
A part is (re)built only if its sheet does not exist yet, so a sheet that a rater has started is never overwritten.
Usage: python make_review_package.py <part|all> [manifest_meta_json ...]
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

P791 = Path(__file__).resolve().parents[3]
EXP3 = P791 / "experiment_03_controlled_agents"
OUT = P791 / "human_review"
RNG = np.random.default_rng(20261027)

COMMON = """Rules for every sheet: fill only the columns that start with `human_`; leave a cell empty if you did not look.
Use `unclear` rather than guessing. Two raters label the first 20% of rows independently (column `rater` = initials),
then compare (Cohen's kappa via `python experiment_03_controlled_agents/scripts/full/review_agreement.py <sheet>`).
Model-generated or agent-generated labels must never be entered in these columns (RESEARCH_DECISIONS G4)."""

CODEBOOK = {
 "exp01v_parser_steps": """# Exp01-V parser steps (24 rows)
Question: is `role_step_example` a real agent action (a command/tool call the agent issued), and is the author parser's
`author_step_example` one? Context: Exp01-V V4 (role-aware parser vs authors' loader).
- `human_is_role_step_a_real_agent_action`: yes / no / unclear
- `human_notes`: free text (e.g. "author step is narration, not an action").
Estimated time: 20 min.""",
 "exp02_parser_steps": """# Exp02 parser steps (24 rows)
Question: is `parsed_action` one action the agent actually executed, and which semantic category fits it?
- `human_is_agent_action`: yes / no / unclear
- `human_expected_category`: one of search, view, edit, test, run, vcs, install, submit, other
- `human_notes`: free text. Estimated time: 25 min.""",
 "exp02_paired_tasks": """# Exp02 paired tasks (40 tasks x 5 models)
Question: did the submitted patch change the right place in the code (localisation)? Compare with the reference
patch files (`n_ref_files`, `touched_ref_files_recall`).
- `human_localisation_correct(y/n/unclear)`: y if the edited functions/files are where the reference fix is, or an
  equivalent location; n otherwise.
- `human_strategy_note`: one sentence on the strategy. Estimated time: 2-3 h (can be split).""",
 "exp03_pilot_c1": """# Exp03 pilot C1 'already fixed' attempts
Setting: the gold fix was already applied and committed before the agent started; the issue text was unchanged.
The ideal behaviour is to verify that the problem no longer occurs and to submit no functional change.
Open `traj_path` (JSON; read the assistant messages) and the `submission` / `diff_excerpt` columns.
- `human_recognized_already_fixed`: yes (the agent states or demonstrates that the issue is already solved) / no / unclear
- `human_verified_by_running`: yes (it ran a reproduction or tests and saw them pass before deciding) / no / unclear
- `human_edit_necessary`: for attempts that edited code: was any edit needed? no (redundant) / yes / unclear
- `human_edit_effect`: harmless (redundant re-application, cosmetic) / harmful (changes behaviour, breaks tests) / none
- `human_format_failure_only`: yes if the decision was right but the submission was not a diff (e.g. a sentence)
- `human_notes`. Automatic class (`auto_c1_class`) is shown for reference only; judge independently.
Estimated time: 1.5-2 h.""",
 "exp03_b2_fidelity": """# Exp03 B2 (task-preserving rewrite) fidelity
B2 rewrites the prose of the issue; code, identifiers, paths, numbers and quoted strings are kept byte-identical by
construction (placeholder masking) and were checked automatically. Read `original` and `rewrite` side by side
(files in `items/`).
- `human_same_requirements`: yes (a developer would implement exactly the same fix from either text) / no / unclear
- `human_information_added`: none / hint (adds a diagnosis or fix suggestion) / other
- `human_information_removed`: none / detail (loses an expected/observed behaviour, a step, a condition) / other
- `human_natural`: yes (reads like a real issue) / no
- `human_notes`. Estimated time: 3-4 min per item.""",
 "exp03_c2_validity": """# Exp03 C2 (changed requirement) validity
C2 = original issue + an appended maintainer update that changes the required behaviour. Executable checks already
passed: unchanged repo fails, revised reference fix passes, original fix fails the revised tests. You judge meaning.
Files in `items/<id>/`: issue.txt, requirement.txt, gold_original.diff, gold_revised.diff, tests_original.diff,
tests_revised.diff.
- `human_change_meaningful`: yes (a real, plausible design change) / trivial (cosmetic) / no
- `human_requirement_unambiguous`: yes (only one reasonable implementation of the new behaviour) / no / unclear
- `human_tests_match_requirement`: yes (the revised tests check exactly what the update says, nothing hidden) / no / unclear
- `human_revised_fix_correct`: yes / no / unclear
- `human_notes`. Estimated time: 5-8 min per item.""",
}

EXISTING = {
    "exp01v_parser_steps": P791 / "experiment_01_verification/results/v1/v4_human_review_sheet.csv",
    "exp02_parser_steps": P791 / "experiment_02_free_archive/results/validation/human_review_sheet_24.csv",
    "exp02_paired_tasks": P791 / "experiment_02_free_archive/results/validation/paired_tasks_40.csv",
}


def write_codebook(part):
    d = OUT / part
    d.mkdir(parents=True, exist_ok=True)
    (d / "CODEBOOK.md").write_text(CODEBOOK[part] + "\n\n" + COMMON + "\n")
    return d


def copy_existing(part):
    d = write_codebook(part)
    dst = d / "sheet.csv"
    if not dst.exists():
        shutil.copy2(EXISTING[part], dst)
    return len(pd.read_csv(dst))


def pilot_c1():
    d = write_codebook("exp03_pilot_c1")
    if (d / "sheet.csv").exists():
        return len(pd.read_csv(d / "sheet.csv"))
    T = pd.read_parquet(EXP3 / "results/analysis/pilot_v2_measures/attempts.parquet")
    C = T[T.variant == "C1"].copy()
    take = [C[C.sub_kind == "text"]]
    for cls, g in C[C.sub_kind != "text"].groupby("c1_class"):
        take.append(g.sample(min(8, len(g)), random_state=1))
    S = pd.concat(take).drop_duplicates("run_id").sample(frac=1, random_state=2)
    rows = []
    for r in S.itertuples():
        m = r.run_id.split("__")[0]
        tp = EXP3 / f"results/pilot/{m}/{r.run_id}.traj.json"
        t = json.loads(tp.read_text())
        last = [x for x in t["messages"] if x["role"] == "assistant"]
        sub = t["info"].get("submission") or ""
        rows.append(dict(item=len(rows) + 1, run_id=r.run_id, model=r.model, instance_id=r.instance_id,
                         exit_status=r.exit_status, auto_c1_class=r.c1_class, auto_recognition_text=r.recognition_text,
                         resolved_official=r.resolved, submission=sub[:1500],
                         diff_excerpt=sub[:1500] if "diff --git" in sub else "",
                         last_assistant_message=str(last[-1].get("content") if last else "")[:1500],
                         traj_path=str(tp.relative_to(P791)), rater="", human_recognized_already_fixed="",
                         human_verified_by_running="", human_edit_necessary="", human_edit_effect="",
                         human_format_failure_only="", human_notes=""))
    pd.DataFrame(rows).to_csv(d / "sheet.csv", index=False)
    return len(rows)


def variants(kind, metas):
    part = {"B2": "exp03_b2_fidelity", "C2": "exp03_c2_validity"}[kind]
    d = write_codebook(part)
    if (d / "sheet.csv").exists():
        return len(pd.read_csv(d / "sheet.csv"))
    ids = []
    for mf in metas:
        m = json.loads(Path(mf).read_text())
        ts = m["tasksets"]
        if "staging" in ts:
            ids += ts["staging"]
        if kind in ts:
            pool = ts[kind]
            ids += list(RNG.choice(pool, min(30, len(pool)), replace=False))
    D = pd.read_parquet(EXP3 / "data/swe_bench_verified/data/test-00000-of-00001.parquet").set_index("instance_id")
    rows = []
    for k, iid in enumerate(dict.fromkeys(ids), 1):
        vd = EXP3 / "data/variants_full" / iid
        v = json.loads((vd / "validation.json").read_text())
        it = d / "items" / f"{k:03d}_{iid}"
        it.mkdir(parents=True, exist_ok=True)
        (it / "original.txt").write_text(D.loc[iid].problem_statement)
        base = dict(item=k, instance_id=iid, folder=str(it.relative_to(OUT)), rater="")
        if kind == "B2":
            (it / "rewrite.txt").write_text((vd / "B2.txt").read_text())
            s = next(x for x in v["B2_samples"] if x.get("valid"))
            rows.append(dict(base, auto_prose_similarity=s["prose_similarity"], auto_len_ratio=s["prose_len_ratio"],
                             human_same_requirements="", human_information_added="", human_information_removed="",
                             human_natural="", human_notes=""))
        else:
            txt = (vd / "C2.txt").read_text()
            (it / "issue.txt").write_text(txt)
            (it / "requirement.txt").write_text(txt.split("Update from the maintainers:")[-1].strip())
            (it / "gold_original.diff").write_text(D.loc[iid].patch)
            (it / "gold_revised.diff").write_text((vd / "C2.gold.diff").read_text())
            (it / "tests_original.diff").write_text(D.loc[iid].test_patch)
            (it / "tests_revised.diff").write_text((vd / "C2.test.diff").read_text())
            rows.append(dict(base, auto_summary=v.get("C2_summary"), auto_needs_unambiguity_check=v.get("C2_needs_human_unambiguity_check"),
                             human_change_meaningful="", human_requirement_unambiguous="", human_tests_match_requirement="",
                             human_revised_fix_correct="", human_notes=""))
    pd.DataFrame(rows).to_csv(d / "sheet.csv", index=False)
    return len(rows)


def index():
    rows = []
    for part in CODEBOOK:
        f = OUT / part / "sheet.csv"
        if f.exists():
            S = pd.read_csv(f)
            hc = [c for c in S.columns if c.startswith("human_")]
            filled = int(S[hc].notna().any(axis=1).sum()) if hc else 0
            rows.append(dict(part=part, rows=len(S), rows_with_any_human_label=filled, sheet=str(f.relative_to(P791))))
    pd.DataFrame(rows).to_csv(OUT / "index.csv", index=False)
    (OUT / "README.md").write_text(
        "# Human review package (BCM construct-validity project)\n\nNothing here has been labelled by a human yet. "
        "Each folder has a CODEBOOK.md and a sheet.csv; `index.csv` lists progress.\n\nPriority for the paper: "
        "(1) exp03_c2_validity and exp03_b2_fidelity (they validate the full-study manipulations), (2) exp03_pilot_c1, "
        "(3) exp02_paired_tasks, (4) the two parser-step sheets.\n\n" + COMMON + "\n")
    print(pd.DataFrame(rows).to_string())


def main(part, *metas):
    OUT.mkdir(exist_ok=True)
    if part in ("all", "existing"):
        for p in EXISTING:
            print(p, copy_existing(p))
    if part in ("all", "pilot_c1"):
        print("exp03_pilot_c1", pilot_c1())
    if part in ("all", "b2c2") and metas:
        print("B2", variants("B2", metas), "C2", variants("C2", metas))
    index()


if __name__ == "__main__":
    main(*sys.argv[1:])
