"""Trajectory parsers.

Two representations are produced from the same raw record:

* ``author``: an exact re-implementation of the action extraction in the author
  loader (external/colm-agent-eval/data/load_swebench.py:25-34 for SWE-smith and
  :73-85 for Nebius). It is kept bug-for-bug, including the SWE-smith filter on
  ``message_type == "action"`` that yields nothing for plain role/content records.
* ``role_aware``: one step per agent tool action, with system prompts, task
  statements and observations excluded. The observation that follows each action
  is kept alongside it so error features can be computed per step.

Role rules per source (documented in reports/05_methods_and_threats.md):

SWE-smith, structured records (any message carries ``message_type``):
    step  = message with message_type == "action" and a non-empty tool call;
    text  = canonical command built from tool_calls (see ``canonical_command``);
    obs   = the next message with message_type == "observation".
SWE-smith, plain records (role/content only):
    step  = each ``<function=NAME>...</function>`` block in an assistant message;
    text  = canonical command built from its ``<parameter=K>V</parameter>`` tags;
    obs   = the next user/tool message.
Nebius (SWE-agent ``role`` in {system, user, ai}):
    step  = each ``ai`` message that contains a fenced code block;
    text  = the last fenced block (SWE-agent executes the final block);
    obs   = the next ``user`` message.
"""
import ast
import json
import re

FUNC_RE = re.compile(r"<function=([\w\-]+)>(.*?)(?:</function>|$)", re.S)
PARAM_RE = re.compile(r"<parameter=([\w\-]+)>(.*?)(?:</parameter>|(?=<parameter=)|$)", re.S)
FENCE_RE = re.compile(r"```[^\n`]*\n(.*?)```", re.S)


# --------------------------------------------------------------------------- author

def author_swe_smith_actions(messages_field):
    """Bug-for-bug copy of load_swebench.py:22-34."""
    action_sequence = []
    try:
        messages = json.loads(messages_field) if isinstance(messages_field, str) else messages_field
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict) and msg.get("message_type") == "action":
                    content = msg.get("content", "")
                    if content:
                        action_sequence.append(content)
    except Exception:
        pass
    return action_sequence


def author_nebius_actions(trajectory_data):
    """Bug-for-bug copy of load_swebench.py:70-85."""
    action_sequence = []
    try:
        messages = json.loads(trajectory_data) if isinstance(trajectory_data, str) else trajectory_data
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get("text") if msg.get("text") is not None else msg.get("system_prompt", "")
                    content_str = str(content).strip()
                    if content_str and content_str != "None":
                        action_sequence.append(content_str)
                elif isinstance(msg, str):
                    action_sequence.append(msg)
    except Exception:
        pass
    return action_sequence


# ----------------------------------------------------------------------- role-aware

def canonical_command(name, params):
    """One string per tool call, identical across SWE-smith encodings.

    bash -> the command itself; submit -> "submit"; other tools -> name followed
    by parameter values in their given order (matches the dataset's own
    ``action`` field, e.g. "str_replace_editor view /testbed")."""
    if name == "bash":
        return str(params.get("command", "")).strip()
    vals = [str(v) for v in params.values() if v is not None and str(v) != ""]
    return " ".join([name] + vals).strip()


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in content)
    return "" if content is None else str(content)


def _tool_calls(tc):
    if tc is None:
        return []
    if isinstance(tc, str):
        try:
            tc = ast.literal_eval(tc)
        except (ValueError, SyntaxError):
            try:
                tc = json.loads(tc)
            except ValueError:
                return []
    out = []
    for call in tc if isinstance(tc, list) else []:
        fn = call.get("function", {}) if isinstance(call, dict) else {}
        args = fn.get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"_raw": args}
        out.append((fn.get("name"), args if isinstance(args, dict) else {"_raw": str(args)}))
    return out


def role_aware_swe_smith(messages_field):
    """Return (steps, observations, fmt) for a SWE-smith record."""
    msgs = json.loads(messages_field) if isinstance(messages_field, str) else messages_field
    structured = any(isinstance(m, dict) and "message_type" in m for m in msgs)
    steps, obs = [], []
    if structured:
        for i, m in enumerate(msgs):
            if m.get("message_type") != "action":
                continue
            calls = [c for c in _tool_calls(m.get("tool_calls")) if c[0]]
            if not calls:
                continue
            nxt = next((msgs[j] for j in range(i + 1, len(msgs))
                        if msgs[j].get("message_type") == "observation"), None)
            o = _content_text(nxt.get("content")) if nxt else ""
            for name, args in calls:
                steps.append(canonical_command(name, args))
                obs.append(o)
        return steps, obs, "structured"
    for i, m in enumerate(msgs):
        if m.get("role") != "assistant":
            continue
        text = _content_text(m.get("content"))
        blocks = FUNC_RE.findall(text)
        if not blocks:
            continue
        nxt = next((msgs[j] for j in range(i + 1, len(msgs))
                    if msgs[j].get("role") in ("user", "tool")), None)
        o = _content_text(nxt.get("content")) if nxt else ""
        for name, body in blocks:
            params = {k: v.strip("\n") for k, v in PARAM_RE.findall(body)}
            steps.append(canonical_command(name, params))
            obs.append(o)
    return steps, obs, "plain"


def role_aware_nebius(trajectory):
    """Return (steps, observations, fmt) for a Nebius SWE-agent record."""
    msgs = list(trajectory)
    steps, obs = [], []
    for i, m in enumerate(msgs):
        if m.get("role") != "ai":
            continue
        text = m.get("text") or ""
        blocks = FENCE_RE.findall(text)
        if not blocks:
            continue
        nxt = next((msgs[j] for j in range(i + 1, len(msgs)) if msgs[j].get("role") == "user"), None)
        steps.append(blocks[-1].strip())
        obs.append((nxt.get("text") or "") if nxt else "")
    return steps, obs, "swe-agent"
