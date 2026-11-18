"""Parsers for native SWE-agent 1.1 function-calling trajectories (SWE-bench Pro public archive).

Four representations of the SAME .traj record:

R0 ``author_smith``  literal application of the BCM authors' SWE-smith loader
                     (colm-agent-eval/data/load_swebench.py:25-34): one step per history message
                     with message_type == "action" and non-empty ``content``. ``content`` is the
                     model's visible thought text, so a model that hides its reasoning yields
                     (almost) no steps.
R1 ``author_all``    literal analogue of the authors' Nebius loader (:73-85): every history message
                     with non-empty text, incl. system prompt, task statement and observations.
R2 ``role_aware``    one step per model-proposed tool call: history messages with
                     message_type == "action" that carry tool_calls. The step string is SWE-agent's
                     own rendering of the call (``action`` field, identical renderer for all models
                     in a cohort). Harness messages without a tool call (e.g. "Exit due to cost
                     limit") are excluded and counted. The following tool observation is kept for
                     error features.
R3 ``semantic``      R2 steps labelled by a tool-semantic categoriser (``semantic_category``)
                     instead of the BCM regexes.
"""
import ast
import json
import re
import shlex

HARNESS_EXIT_RE = re.compile(r"^\s*Exit due to", re.I)


def _calls(tc):
    if not tc:
        return []
    if isinstance(tc, str):
        try:
            tc = ast.literal_eval(tc)
        except (ValueError, SyntaxError):
            tc = json.loads(tc)
    return tc if isinstance(tc, list) else []


def _text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in c)
    return "" if c is None else str(c)


def author_smith(history):
    return [m["content"] for m in history
            if isinstance(m, dict) and m.get("message_type") == "action" and m.get("content")]


def author_all(history):
    out = []
    for m in history:
        s = _text(m.get("content")).strip()
        if s and s != "None":
            out.append(s)
    return out


def role_aware(history):
    """Return dict(steps, obs, tools, n_harness_msgs, n_multi_call_msgs, n_action_msgs)."""
    steps, obs, tools = [], [], []
    n_harness = n_multi = n_action = 0
    for i, m in enumerate(history):
        if m.get("message_type") != "action":
            continue
        n_action += 1
        calls = _calls(m.get("tool_calls"))
        if not calls:
            n_harness += 1
            continue
        if len(calls) > 1:
            n_multi += 1
        nxt = next((history[j] for j in range(i + 1, len(history))
                    if history[j].get("message_type") == "observation"), None)
        o = _text(nxt.get("content")) if nxt else ""
        # SWE-agent renders one ``action`` string per message; with multiple calls fall back to
        # rendering each call ourselves (never observed in the smoke sample).
        if len(calls) == 1 and (m.get("action") or "").strip():
            rendered = [m["action"].strip()]
        else:
            rendered = [render_call(c) for c in calls]
        for c, r in zip(calls, rendered):
            steps.append(r)
            obs.append(o)
            tools.append(c.get("function", {}).get("name", ""))
    return dict(steps=steps, obs=obs, tools=tools, n_harness_msgs=n_harness,
                n_multi_call_msgs=n_multi, n_action_msgs=n_action)


def render_call(call):
    fn = call.get("function", {})
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except ValueError:
        args = {"_raw": fn.get("arguments")}
    name = fn.get("name", "")
    if name == "bash":
        return str(args.get("command", "")).strip()
    return " ".join([name] + [str(v) for v in args.values() if v not in (None, "")]).strip()


# ------------------------------------------------------------------ semantic categoriser
SEARCH_CMDS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "find", "fd", "ls", "tree", "locate", "git grep"}
VIEW_CMDS = {"cat", "head", "tail", "less", "more", "nl", "wc", "bat", "file", "stat", "diff", "jq"}
TEST_PAT = re.compile(r"(\bpytest\b|python[0-9.]*\s+-m\s+(pytest|unittest)|\bgo\s+test\b|\bnpm\s+(run\s+)?test|"
                      r"\byarn\s+(run\s+)?test|\bnpx\s+(jest|mocha|vitest)|\bjest\b|\bmocha\b|\bvitest\b|\btox\b|"
                      r"\bmake\s+test|\bpnpm\s+(run\s+)?test|\bnose2?tests?\b|\bctest\b|\bcargo\s+test)")
RUN_PAT = re.compile(r"^(python[0-9.]*|node|go\s+run|bash|sh|ruby|php|npx\s+ts-node|ts-node)\s+\S+")
EDIT_PAT = re.compile(r"(\bsed\s+(-[a-zA-Z]*i|--in-place)|\bperl\s+-[a-zA-Z]*i|\bgit\s+apply\b|\bpatch\s+-|"
                      r"(^|[;&|]\s*)(cat|echo|printf)\b[^|]*>{1,2}\s*\S|\btee\b|<<\s*['\"]?EOF)")
INSTALL_PAT = re.compile(r"\b(pip3?\s+install|npm\s+(install|ci)\b|yarn\s+(add|install)|go\s+(get|mod)\b|apt(-get)?\s+install)")
VCS_PAT = re.compile(r"^\s*git\s+(status|diff|log|show|stash|checkout|reset|branch|blame)\b")
CATEGORIES = ["search", "view", "edit", "test", "run", "vcs", "install", "submit", "other"]


def semantic_category(step):
    s = step.strip()
    if s == "submit" or s.startswith("submit "):
        return "submit"
    if s.startswith("str_replace_editor"):
        parts = s.split()
        sub = parts[1] if len(parts) > 1 else ""
        return "view" if sub == "view" else "edit" if sub in {"create", "str_replace", "insert", "undo_edit"} else "other"
    first_line = s.splitlines()[0] if s else ""
    if EDIT_PAT.search(s):
        return "edit"
    if TEST_PAT.search(s):
        return "test"
    if INSTALL_PAT.search(s):
        return "install"
    if VCS_PAT.search(first_line):
        return "vcs"
    head = _first_command(first_line)
    if head in SEARCH_CMDS or first_line.lstrip().startswith("git grep"):
        return "search"
    if head == "sed" and re.search(r"\bsed\s+-n\b", first_line):
        return "view"
    if head in VIEW_CMDS:
        return "view"
    if RUN_PAT.search(_strip_cd(first_line)):
        return "run"
    return "other"


def _strip_cd(line):
    return re.sub(r"^\s*cd\s+\S+\s*(&&|;)\s*", "", line)


def _first_command(line):
    line = _strip_cd(line)
    try:
        toks = shlex.split(line, posix=True)
    except ValueError:
        toks = line.split()
    while toks and ("=" in toks[0] and not toks[0].startswith("-")):  # env assignments
        toks = toks[1:]
    return toks[0] if toks else ""
