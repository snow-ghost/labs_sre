#!/usr/bin/env bash
# Слайд 40. Меняется только глубина: 1, 4, 16, 64.
set -euo pipefail
source /demo/common.sh
test -f "$SM3_ROOT/ready"
sm3_observe

for depth in 1 4 16 64; do
  printf '\nГлубина %s: 5 секунд прогрева и 30 секунд измерения.\n' "$depth"
  sm3_fio "rr-q$depth" --rw=randread --bs=4k --direct=1 \
    --ioengine=io_uring --iodepth="$depth" --ramp_time=5 --runtime=30
  sm3_table "rr-q$depth"
done
