"""Independent implementation of the 12 paper-defined features (paper Table 1).

Where the paper is silent, rules follow the author code
(external/colm-agent-eval/data/extract_features.py), cited per item:
  * category regexes and precedence edit > test > view > search (:37-79)
  * entropy uses log2 and adds 1e-9 inside the log (:91)
  * an empty sequence gets all-zero features, including consecutive_repetition_max=0 (:19-31)
  * step_velocity = category changes / total steps (:113-117), "other" counts as a category
The README descriptions (category entropy, step velocity as steps per unit length,
raw error counts) are NOT implemented.
"""
import re

import numpy as np

FEATURES = [
    "total_steps", "mean_action_length", "max_action_length",
    "file_search_count", "file_view_count", "file_edit_count",
    "test_execution_count", "action_entropy", "consecutive_repetition_max",
    "unique_action_ratio", "error_flag_count", "step_velocity",
]

SEARCH = [re.compile(p) for p in [
    r'find\b.*\b(?:file|class|method|function|dir|folder)',
    r'search\b.*\b(?:directory|codebase|repo|file|text|grep)',
    r'locate\b.*\b(?:class|file|module|widgets)',
    r'\bls\b', r'\bgrep\b']]
VIEW = [re.compile(p) for p in [
    r'(?:view|read|examine|open|check|inspect|look\s+at)\b.*\b(?:file|content|code|source|widgets\.py|\.py|\.json|\.md)',
    r'\bcat\b']]
EDIT = [re.compile(p) for p in [
    r'(?:edit|write|modify|patch|change|update|fix|replace|insert|save)\b.*\b(?:file|code|line|method|class|widgets\.py|\.py)',
    r'\bsed\b', r'<<<<<<<']]
TEST = [re.compile(p) for p in [
    r'(?:run|execute|try|check|perform)\b.*\b(?:test|pytest|suite|unittest|verification)',
    r'\btest\b.*\b(?:fail|pass|run|output)']]
ERROR = [re.compile(p) for p in [
    r'\b(?:name|type|value|key|index|attribute|zero-division|syntax|indentation)error\b',
    r'traceback', r'assert.*fail', r'failed\s+\d+\s+test', r'exception\b',
    r'issue\s+with\s+the\s+`?\w+`?\s+class']]


def _any(patterns, s):
    return any(p.search(s) for p in patterns)


def categorize(step):
    s = step.lower()
    if _any(EDIT, s):
        return "edit"
    if _any(TEST, s):
        return "test"
    if _any(VIEW, s):
        return "view"
    if _any(SEARCH, s):
        return "search"
    return "other"


def compute_features(steps, error_texts=None):
    """Return the 12 features for a list of step strings.

    ``error_texts`` (same length as ``steps``) lets the role-aware representation
    flag errors in the observation that follows each action; by default the step
    text itself is scanned, as in the author code."""
    steps = [str(s) for s in steps]
    n = len(steps)
    f = dict.fromkeys(FEATURES, 0.0)
    f["total_steps"] = n
    f["consecutive_repetition_max"] = 0
    if n == 0:
        return f
    lengths = np.array([len(s) for s in steps], dtype=float)
    f["mean_action_length"] = float(lengths.mean())
    f["max_action_length"] = float(lengths.max())
    cats = [categorize(s) for s in steps]
    f["file_search_count"] = cats.count("search") / n
    f["file_view_count"] = cats.count("view") / n
    f["file_edit_count"] = cats.count("edit") / n
    f["test_execution_count"] = cats.count("test") / n
    _, counts = np.unique(steps, return_counts=True)
    p = counts / n
    f["action_entropy"] = float(-np.sum(p * np.log2(p + 1e-9)))
    f["unique_action_ratio"] = len(counts) / n
    best = run = 1
    for a, b in zip(steps, steps[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    f["consecutive_repetition_max"] = best
    texts = steps if error_texts is None else [str(t) for t in error_texts]
    f["error_flag_count"] = sum(_any(ERROR, t.lower()) for t in texts) / n
    f["step_velocity"] = sum(a != b for a, b in zip(cats, cats[1:])) / n
    return f
