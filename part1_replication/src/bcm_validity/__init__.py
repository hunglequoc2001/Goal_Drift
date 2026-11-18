"""Independent, paper-faithful BCM pipeline and measurement-validity audit."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config():
    return yaml.safe_load((ROOT / "configs/experiment.yaml").read_text())
