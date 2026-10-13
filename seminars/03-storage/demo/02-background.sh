#!/usr/bin/env bash
# Слайд 38. Статистика устройства до запуска fio.
set -euo pipefail
source /demo/common.sh
test -f "$SM3_ROOT/ready"

LC_ALL=C S_TIME_FORMAT=ISO iostat -xz -y -t -k 1 10
pidstat -d 1 5
# В минимальной ВМ нет journalctl. Читаем кольцевой журнал ядра.
dmesg | tail -n 20
