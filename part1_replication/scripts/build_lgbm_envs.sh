#!/bin/bash
# Build isolated venvs with historical LightGBM versions (downloads: run on xfer).
set -euo pipefail
PY=$(readlink -f /gpfs_common/share02/gaise/qle3/project_791/bcm-validity/.venv/bin/python)
BASE=/share/gaise/qle3/envs/bcm_lgbm
export PIP_CACHE_DIR=/share/gaise/qle3/pip_cache
mkdir -p $BASE
for v in 4.6.0 4.5.0 4.3.0 4.1.0 4.0.0 3.3.5; do
  d=$BASE/lgbm-$v
  [ -x $d/bin/python ] || $PY -m venv $d
  if [[ $v == 3.* ]]; then np="numpy<2"; else np="numpy==2.2.6"; fi
  $d/bin/python -m pip install -q --upgrade pip
  $d/bin/python -m pip install -q "lightgbm==$v" "$np" "scikit-learn==1.6.1" "pandas==2.2.3" "scipy<1.16" pyyaml pyarrow
  $d/bin/python -c "import lightgbm,numpy,sklearn;print('$v ok',lightgbm.__version__,numpy.__version__,sklearn.__version__)"
done
