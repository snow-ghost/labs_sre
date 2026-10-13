#!/usr/bin/env bash
# Слайд 41. Сравнить семь запусков и проверить исходный файл.
set -euo pipefail
source /demo/common.sh
test -f "$SM3_ROOT/ready"

sm3_table bufread-1 bufread-2 dirread rr-q1 rr-q4 rr-q16 rr-q64
sha256sum -c "$SM3_ROOT/before.sha256"
printf '\nНаблюдения iostat: %s/iostat.txt\n' "$SM3_ROOT"
tail -n 18 "$SM3_ROOT/iostat.txt"
# Последние строки нужны для показа формата, а не для усреднения всего теста.
