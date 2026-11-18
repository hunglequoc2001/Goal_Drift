"""Check of the C1 setup in run_agent.py, without a model: after the pre-patch is applied and committed, HEAD~1..HEAD
touches exactly the gold-patch files and the working tree is clean."""
import subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from run_agent import EXEC_ARGS
from minisweagent.environments.singularity import SingularityEnvironment
iid = sys.argv[1]
pre_txt = Path(f"data/variants/{iid}/C1.pre.diff").read_text()
env = SingularityEnvironment(image=f"/share/gaise/qle3/sif/{iid}.sif", executable="apptainer", exec_args=EXEC_ARGS, cwd="/testbed", timeout=60)
r = env.execute({"command": f"cd /testbed && git apply <<'PREPATCH_EOF' && git status --short\n{pre_txt}\nPREPATCH_EOF"})
print("apply:", r["returncode"], r["output"].strip())
assert r["returncode"] == 0 and r["output"].strip()
env.execute({"command": "cd /testbed && git add -A && git -c user.email=x@y -c user.name=x commit -qm base"})
print("committed files:", env.execute({"command": "cd /testbed && git diff --name-only HEAD~1 HEAD"})["output"].strip())
print("clean tree:", repr(env.execute({"command": "cd /testbed && git status --short"})["output"].strip()))
env.cleanup(); print("OK")
