from bcm03.analysis import jacc, lev_sim
from bcm03.ingest import changed_lines, diff_targets

DIFF = """diff --git a/pkg/mod.py b/pkg/mod.py
index 1..2 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -10,3 +10,4 @@ def foo(x):
     a = 1
+    b = 2
-    c = 3
diff --git a/repro.py b/repro.py
new file mode 100644
--- /dev/null
+++ b/repro.py
@@ -0,0 +1 @@
+print(1)
"""


def test_diff_targets():
    mod, new, funcs = diff_targets(DIFF)
    assert mod == {"pkg/mod.py"} and new == {"repro.py"} and funcs == {"pkg/mod.py::foo"}
    assert changed_lines(DIFF) == 3


def test_similarities():
    assert lev_sim("a|b|c", "a|b|c") == 1.0
    assert lev_sim("a|b", "a|c") == 0.5
    assert lev_sim("", "") == 1.0
    assert jacc("", "") == 1.0 and jacc("x|y", "y") == 0.5
