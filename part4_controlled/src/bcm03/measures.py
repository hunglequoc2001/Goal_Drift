"""Task-grounded behaviour measures for the Exp03 full study (pilot report §P8 corrections; FULL_STUDY_ANALYSIS_PLAN.md §3).

Three constructs are kept apart:
  correctness      final functional correctness from the executable oracle (resolved; FAIL_TO_PASS / PASS_TO_PASS status),
  appropriateness  whether the agent's intervention fits the task (edit scope vs the gold patch, edit necessity on C1,
                   adaptation to the changed requirement on C2, regressions),
  consistency      agreement between two runs of the same model on the same task (pair level).
Only quantities derived from the final repository state and the oracle are called "task-grounded". Action-sequence
similarity comes from the same trace as the BCM features, so it is reported as trace-derived and is never used as
independent validation of BCM.

Attempt-level columns added by attempt_measures(): edited, n_src_files, scope_precision, scope_recall, harmful,
f2p_frac, and per variant c1_class / c2_class.
Edits are read from the final repository state (`state_files`, full study: `git diff` of the sandbox when the agent
stops) when available, else from the submitted diff (pilot). Submissions that are not a diff (an agent that "submits"
the sentence "No changes required") fail the official grader; they are kept as format failures and classified
separately, not silently counted as wrong decisions (pilot addendum A1).
Pair-level measures (pair_measures): outcome_concord, edit_decision_agree, file_jacc_cond, func_jacc_cond, seq_sim.
Cell summaries (cell_summary): solve rate p, chance concordance p^2+(1-p)^2 and the chance-corrected concordance.
"""
import json
import re

import numpy as np
import pandas as pd

TEST_PATH = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_tests?\.py$|(^|/)conftest\.py$")
RECOG = re.compile(r"already\s+(?:been\s+)?(?:fixed|implemented|handled|resolved|addressed|correct|in place|present|applied)"
                   r"|no\s+(?:code\s+)?changes?\s+(?:are\s+|is\s+)?(?:needed|necessary|required)"
                   r"|(?:issue|bug|problem)\s+(?:appears|seems|is)\s+(?:to\s+be\s+)?(?:already\s+)?(?:fixed|resolved)"
                   r"|works?\s+as\s+expected", re.I)


SEP = "\x1f"


def patch_lines(diff):
    """Normalised changed lines (+/-, whitespace-collapsed) in non-test source files of a unified diff."""
    out, keep = set(), False
    for l in (diff or "").splitlines():
        if l.startswith("diff --git "):
            f = l.split(" b/")[-1]
            keep = not TEST_PATH.search(f) and f.endswith(".py")
        elif keep and l[:1] in "+-" and not l.startswith(("+++", "---")):
            t = " ".join(l[1:].split())
            if t:
                out.add(l[0] + t)
    return out


def split(s):
    return set(filter(None, (s or "").split("|")))


def src_files(edited_files):
    return {f for f in split(edited_files) if not TEST_PATH.search(f)}


def sub_kind(submission):
    s = (submission or "").strip()
    return "empty" if not s else ("diff" if "diff --git" in s else "text")


def attempt_measures(T, gold_files):
    """T: attempts with edited_files, edited_funcs, resolved, variant, instance_id, exit_status, sub_kind, sub_claims_noop,
    optional state_files/state_funcs (final repository state) and oracle test-status columns."""
    T = T.copy()
    use_state = "state_files" in T and T.state_files.notna().all()
    T["edit_source"] = "state" if use_state else "submission"
    S = [src_files(e) for e in (T.state_files if use_state else T.edited_files)]
    funcs = T.state_funcs if use_state else T.edited_funcs
    G = [gold_files[i] for i in T.instance_id]
    T["src_files"] = ["|".join(sorted(s)) for s in S]
    T["src_funcs"] = ["|".join(sorted(f for f in split(fn) if f.split("::")[0] in s)) for fn, s in zip(funcs, S)]
    T["edited"] = [len(s) > 0 for s in S]
    T["n_src_files"] = [len(s) for s in S]
    T["scope_precision"] = [len(s & g) / len(s) if s else np.nan for s, g in zip(S, G)]
    T["scope_recall"] = [len(s & g) / len(g) if g else np.nan for s, g in zip(S, G)]
    T["touches_gold_src"] = [bool(s & g) for s, g in zip(S, G)]
    if "p2p_fail" in T:
        T["harmful"] = T.p2p_fail > 0                          # a previously passing test now fails
        T["f2p_frac"] = T.f2p_pass / T.f2p_total.where(T.f2p_total > 0)
    # C1 'already fixed'. Correct decision = no functional change, stated by submitting. Final-state correctness is
    # `resolved_state` when the final repository state was graded (full study), else the official `resolved`.
    c1 = T.variant == "C1"
    ok = T.resolved_state.astype("boolean").fillna(T.resolved).astype(bool) if "resolved_state" in T else T.resolved.astype(bool)
    sub = T.exit_status == "Submitted"
    T["c1_class"] = None
    T.loc[c1 & sub & ~T.edited & (T.sub_kind == "empty") & ok, "c1_class"] = "recognized_noop"
    T.loc[c1 & sub & ~T.edited & (T.sub_kind == "text") & T.sub_claims_noop, "c1_class"] = "recognized_noop_text_submission"
    T.loc[c1 & ~sub & ~T.edited, "c1_class"] = "inaction"              # ran out of steps/context; nothing decided
    T.loc[c1 & T.edited & ok, "c1_class"] = "harmless_edit"            # unnecessary, tests still pass
    T.loc[c1 & T.edited & ~ok, "c1_class"] = "harmful_edit"            # introduced a failure / regression
    T.loc[c1 & T.c1_class.isna(), "c1_class"] = "other"                # e.g. text submission without a no-change claim
    T["c1_correct_decision"] = T.c1_class.isin(["recognized_noop", "recognized_noop_text_submission"]).where(c1)
    # C2 changed requirement: graded by the revised oracle (resolved) and, as a diagnostic, by the original oracle
    if "resolved_orig_oracle" in T:
        c2 = T.variant == "C2"
        T["c2_class"] = None
        T.loc[c2 & T.resolved, "c2_class"] = "adapted"
        T.loc[c2 & ~T.resolved & T.resolved_orig_oracle.fillna(False).astype(bool), "c2_class"] = "persisted_original"
        T.loc[c2 & ~T.resolved & ~T.resolved_orig_oracle.fillna(False).astype(bool), "c2_class"] = "failed"
    return T


def claims_noop(text):
    return bool(RECOG.search(text or "")) or bool(re.search(r"\bno (?:code )?changes?\b|\bnothing to (?:fix|change)\b", text or "", re.I))


def recognition_evidence(messages):
    """True if an assistant message states that the problem is already solved (C1 audit aid; heuristic, human-validated)."""
    return any(m.get("role") == "assistant" and RECOG.search(str(m.get("content") or "")) for m in messages)


def jacc_cond(a, b):
    """Jaccard of two edit sets, defined only when both runs edited something (pilot §P8: empty==empty is not agreement)."""
    a, b = split(a), split(b)
    return len(a & b) / len(a | b) if a and b else np.nan


def patch_sim_cond(a, b):
    """Jaccard of normalised changed source lines; defined only when both runs changed source code."""
    a, b = set(filter(None, (a or "").split(SEP))), set(filter(None, (b or "").split(SEP)))
    return len(a & b) / len(a | b) if a and b else np.nan


def f2p_agree(r, s):
    """Share of FAIL_TO_PASS tests on which two runs have the same pass/fail status (no tests run = all fail)."""
    ids = lambda x: set(json.loads(x)) if isinstance(x, str) and x else set()
    a, b = ids(getattr(r, "f2p_passed_ids", None)), ids(getattr(s, "f2p_passed_ids", None))
    n = max(r.f2p_total, s.f2p_total)
    return 1 - len(a ^ b) / n if n else np.nan


def lev_sim(a, b):
    a, b = a.split("|") if a else [], b.split("|") if b else []
    if not a and not b:
        return 1.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return 1.0 - prev[-1] / max(len(a), len(b))


PAIR = {  # name -> (function of two attempt rows, task-grounded?)
    "patch_sim_cond": (lambda r, s: patch_sim_cond(r.src_patch_lines, s.src_patch_lines), True),
    "f2p_agree": (f2p_agree, True),
    "outcome_concord": (lambda r, s: float(r.resolved == s.resolved), True),
    "edit_decision_agree": (lambda r, s: float(r.edited == s.edited), True),
    "file_jacc_cond": (lambda r, s: jacc_cond(r.src_files, s.src_files), True),
    "func_jacc_cond": (lambda r, s: jacc_cond(r.src_funcs, s.src_funcs), True),
    "seq_sim": (lambda r, s: lev_sim(r.cat_seq, s.cat_seq), False),
}


def pair_measures(r, s):
    return {k: f(r, s) for k, (f, _) in PAIR.items()}


def cell_summary(g):
    """Outcome agreement is uninformative without the solve rate (an always-failing agent agrees perfectly)."""
    p = g.resolved.mean()
    n = len(g)
    obs = 1.0 if n < 2 else (p * n * (p * n - 1) + (1 - p) * n * ((1 - p) * n - 1)) / (n * (n - 1))
    exp = p ** 2 + (1 - p) ** 2
    return pd.Series(dict(n=n, solve_rate=p, outcome_concord=obs, concord_chance=exp,
                          concord_kappa=(obs - exp) / (1 - exp) if exp < 1 else np.nan,
                          edit_rate=g.edited.mean()))
