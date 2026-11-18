import os; os.environ.setdefault("X","1")
import sys; sys.path.insert(0, "/gpfs_common/share02/gaise/qle3/project_791/experiment_03_controlled_agents/scripts")
from minisweagent.environments.singularity import SingularityEnvironment
from run_agent import EXEC_ARGS
import os; os.chdir("/tmp")
env = SingularityEnvironment(image=sys.argv[1], executable="apptainer", exec_args=EXEC_ARGS, cwd="/testbed", timeout=60)
for c in ["pwd && git status --short | head -3 && python --version", "echo hi > /testbed/zz.txt && cat /testbed/zz.txt && git -C /testbed status --short"]:
    print(env.execute({"command": c}))
env.cleanup()
