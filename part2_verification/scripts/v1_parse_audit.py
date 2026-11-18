"""V1-V4: independent audit of the Exp01 parsing claims, read directly from raw source shards.

Checks
  V1  zero-step rows: count rows the UNCHANGED author pipeline gave total_steps==0
      (from the author's own CSV written in Exp01) and test, from raw messages, whether
      those trajectories actually contain agent tool calls.
  V2  source asymmetry: role composition of what the author parser calls a "step".
  V3  shipped SHAP matrix: BCM with and without empty rows; number of distinct vectors.
  V4  role-aware parser invariants vs. independent references:
        SWE-smith structured -> dataset's own per-message `action` field
        SWE-smith plain      -> count of <function=...> blocks in assistant turns
        Nebius               -> count of ai turns, ai turns without code fence
      plus a seeded sample sheet for human review.

Usage: python v1_parse_audit.py <out_dir>
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from bcm_validity.parsers import role_aware_nebius, role_aware_swe_smith

ROOT = Path("/gpfs_common/share02/gaise/qle3/project_791/bcm-validity")
SHIP = ROOT / "external/colm-agent-eval/results/files"
FUNC = re.compile(r"<function=([\w\-]+)>")
FENCE = re.compile(r"```[^\n`]*\n(.*?)```", re.S)


def bcm(phi):
    n = np.linalg.norm(phi, axis=1)
    u = phi[n > 1e-9] / n[n > 1e-9, None]
    k = len(u)
    s = u.sum(0)
    return float((s @ s - k) / (k * (k - 1))) if k > 1 else np.nan


def load_raw(sel):
    out = {}
    for (src, shard), g in sel.groupby(["source", "shard"]):
        t = pq.read_table(ROOT / "data/raw" / src / "data" / shard)
        col = "messages" if src == "swe_smith" else "trajectory"
        c = t.column(col)
        for r in g.itertuples():
            out[r.author_row] = c[int(r.offset)].as_py()
    return out


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sel = pd.read_csv(ROOT / "data/manifests/cohort_author_selection.csv")
    author_csv = pd.read_csv(ROOT / "runs/author_archival/tbf/data/raw_behavioral_dataframe.csv")
    assert len(author_csv) == len(sel)
    assert (author_csv.instance_id.values == sel.instance_id.values).all()
    raw = load_raw(sel)
    res = {}

    # ---------------- V1
    rows = []
    for r in sel.itertuples():
        m = raw[r.author_row]
        a_steps = int(author_csv.total_steps.iloc[r.author_row])
        if r.source == "swe_smith":
            msgs = json.loads(m)
            has_mt = any("message_type" in x for x in msgs)
            n_tool_calls = sum(1 for x in msgs if x.get("tool_calls"))
            n_func = sum(len(FUNC.findall(x.get("content") if isinstance(x.get("content"), str) else str(x.get("content"))))
                         for x in msgs if x.get("role") == "assistant")
            n_action_field = sum(1 for x in msgs if x.get("message_type") == "action" and x.get("action"))
            rows.append(dict(author_row=r.author_row, source=r.source, system=r.agent_system,
                             format="structured" if has_mt else "plain", author_steps=a_steps,
                             n_tool_calls=n_tool_calls, n_function_blocks=n_func,
                             n_action_field=n_action_field, n_messages=len(msgs)))
        else:
            roles = Counter(x.get("role") for x in m)
            rows.append(dict(author_row=r.author_row, source=r.source, system=r.agent_system,
                             format="swe-agent", author_steps=a_steps, n_messages=len(m),
                             n_ai=roles.get("ai", 0), n_user=roles.get("user", 0),
                             n_system=roles.get("system", 0)))
    v = pd.DataFrame(rows)
    v.to_csv(out / "v1_per_row.csv", index=False)
    sm = v[v.source == "swe_smith"]
    t1 = sm.groupby(["system", "format"]).agg(
        n=("author_row", "size"), zero_author=("author_steps", lambda s: int((s == 0).sum())),
        zero_but_has_actions=("n_function_blocks", "size")).reset_index()
    z = sm[sm.author_steps == 0]
    t1["zero_but_has_actions"] = [int(((z.system == a) & (z.format == f) &
                                       ((z.n_function_blocks > 0) | (z.n_tool_calls > 0))).sum())
                                  for a, f in zip(t1.system, t1.format)]
    t1.to_csv(out / "v1_zero_step_by_system.csv", index=False)
    res["V1_total_zero_swe_smith"] = int((sm.author_steps == 0).sum())
    res["V1_zero_rows_all_plain"] = bool((z.format == "plain").all())
    res["V1_zero_rows_with_agent_actions"] = int(((z.n_function_blocks > 0) | (z.n_tool_calls > 0)).sum())
    res["V1_nebius_zero"] = int((v[v.source == "nebius"].author_steps == 0).sum())
    print(t1.to_string(), flush=True)

    # ---------------- V2: role composition of author "steps" (Nebius takes every message with text)
    neb = v[v.source == "nebius"]
    res["V2_nebius_author_steps_eq_n_messages_frac"] = float((neb.author_steps == neb.n_messages).mean())
    res["V2_nebius_ai_fraction_of_author_steps"] = float(neb.n_ai.sum() / neb.author_steps.sum())
    st = sm[sm.format == "structured"]
    # author SWE-smith step = `content` of action messages; compare with thought / action fields
    same_thought = tot = cmd_in_content = 0
    for r in st.itertuples():
        for x in json.loads(raw[r.author_row]):
            if x.get("message_type") == "action" and x.get("content"):
                tot += 1
                same_thought += x.get("content") == x.get("thought")
                a = (x.get("action") or "").strip()
                cmd_in_content += bool(a) and a in x.get("content")
    res["V2_smith_structured_author_steps"] = tot
    res["V2_smith_author_step_equals_thought_frac"] = same_thought / max(tot, 1)
    res["V2_smith_author_step_contains_command_frac"] = cmd_in_content / max(tot, 1)

    # ---------------- V3: shipped SHAP matrix
    S = np.load(SHIP / "oof_shap_matrix.npy")
    sysv = sel.agent_system.values
    empty = (author_csv.total_steps.values == 0)
    t3 = []
    for g in sorted(set(sysv)):
        m = sysv == g
        t3.append(dict(system=g, n=int(m.sum()), n_empty=int((m & empty).sum()),
                       bcm_all=bcm(S[m]), bcm_nonempty=bcm(S[m & ~empty]),
                       distinct_shap_in_empty=len(np.unique(S[m & empty].round(12), axis=0)) if (m & empty).any() else 0))
    pd.DataFrame(t3).to_csv(out / "v3_shipped_bcm_empty.csv", index=False)
    print(pd.DataFrame(t3).to_string(), flush=True)

    # ---------------- V4: role-aware parser invariants
    inv = []
    for r in sel.itertuples():
        m = raw[r.author_row]
        if r.source == "swe_smith":
            steps, obs, fmt = role_aware_swe_smith(m)
            msgs = json.loads(m)
            if fmt == "structured":
                ref = [x.get("action", "").strip() for x in msgs
                       if x.get("message_type") == "action" and x.get("tool_calls")]
                ref_n = len(ref)
                exact = sum(a == b for a, b in zip(steps, ref)) if len(steps) == ref_n else -1
            else:
                ref_n = sum(len(FUNC.findall(str(x.get("content")))) for x in msgs if x.get("role") == "assistant")
                exact = np.nan
            inv.append(dict(author_row=r.author_row, system=r.agent_system, format=fmt,
                            n_role=len(steps), n_ref=ref_n, exact_action_match=exact))
        else:
            steps, obs, fmt = role_aware_nebius(m)
            ai = [x for x in m if x.get("role") == "ai"]
            no_fence = sum(1 for x in ai if not FENCE.search(x.get("text") or ""))
            multi = sum(1 for x in ai if len(FENCE.findall(x.get("text") or "")) > 1)
            inv.append(dict(author_row=r.author_row, system=r.agent_system, format=fmt,
                            n_role=len(steps), n_ref=len(ai), ai_without_fence=no_fence,
                            ai_with_multiple_fences=multi))
    I = pd.DataFrame(inv)
    I.to_csv(out / "v4_role_aware_invariants.csv", index=False)
    summ = I.groupby(["system", "format"]).agg(
        n=("author_row", "size"), zero_role=("n_role", lambda s: int((s == 0).sum())),
        count_match_frac=("n_role", "size")).reset_index()
    summ["count_match_frac"] = [float((I[(I.system == a) & (I.format == f)].n_role ==
                                       I[(I.system == a) & (I.format == f)].n_ref).mean())
                                for a, f in zip(summ.system, summ.format)]
    st_ = I[I.format == "structured"]
    res["V4_structured_rows_with_exact_command_match_all_steps"] = float(
        (st_.exact_action_match == st_.n_ref).mean())
    nb = I[I.format == "swe-agent"]
    res["V4_nebius_ai_turns_without_fence_frac"] = float(nb.ai_without_fence.sum() / nb.n_ref.sum())
    res["V4_nebius_ai_turns_multiple_fences_frac"] = float(nb.ai_with_multiple_fences.sum() / nb.n_ref.sum())
    summ.to_csv(out / "v4_role_aware_summary.csv", index=False)
    print(summ.to_string(), flush=True)

    # human-review sheet: 24 seeded rows, 4 per system, one action each
    rng = np.random.default_rng(20261026)
    sheet = []
    for g in sorted(set(sysv)):
        ids = rng.choice(sel.author_row[sel.agent_system == g].values, 4, replace=False)
        for i in ids:
            r = sel.iloc[i]
            m = raw[i]
            steps = (role_aware_swe_smith(m) if r.source == "swe_smith" else role_aware_nebius(m))[0]
            a_steps = json.loads(author_csv.raw_trajectory_sequence.iloc[i])
            k = int(rng.integers(len(steps))) if steps else -1
            sheet.append(dict(author_row=i, system=g, n_author_steps=len(a_steps), n_role_steps=len(steps),
                              author_step_example=(a_steps[min(max(k, 0), len(a_steps) - 1)][:400] if a_steps else ""),
                              role_step_example=(steps[k][:400] if k >= 0 else ""),
                              human_is_role_step_a_real_agent_action="", human_notes=""))
    pd.DataFrame(sheet).to_csv(out / "v4_human_review_sheet.csv", index=False)
    json.dump(res, open(out / "v1_v4_summary.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
