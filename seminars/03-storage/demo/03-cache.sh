#!/usr/bin/env bash
# Слайд 39. Два буферизованных чтения и одно прямое, по 45 секунд.
set -euo pipefail
source /demo/common.sh
test -f "$SM3_ROOT/ready"
sm3_observe

for pass in 1 2; do
  printf '\nБуферизованное чтение, запуск %s, 45 секунд.\n' "$pass"
  sm3_fio "bufread-$pass" --rw=read --bs=1M --direct=0 \
    --ioengine=psync --iodepth=1 --runtime=45
  sm3_table "bufread-$pass"
done
printf '\nПрямое чтение, 45 секунд.\n'
sm3_fio dirread --rw=read --bs=1M --direct=1 \
  --ioengine=psync --iodepth=1 --runtime=45
sm3_table bufread-1 bufread-2 dirread
