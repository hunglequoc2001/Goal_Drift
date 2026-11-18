#!/bin/bash
# Pull task images listed in a CSV (column 4 = image) into /share/gaise/qle3/sif, ${2:-3} in parallel. Skips existing.
# Usage: pull_images.sh <csv> [n_parallel]
set -uo pipefail
module load apptainer/1.4.2-1
SIF=/share/gaise/qle3/sif
tail -n +2 "$1" | cut -d, -f1,4 | while IFS=, read iid img; do
  f=$SIF/$iid.sif; [ -s "$f" ] && continue
  echo "$iid $img"
done | xargs -P ${2:-3} -L 1 bash -c 't0=$(date +%s); apptainer pull -F /share/gaise/qle3/sif/$0.sif docker://$1 > logs/pull/$0.log 2>&1 && echo "ok $0 $(( $(date +%s)-t0 ))s" || echo "FAIL $0"'
ls -la $SIF
