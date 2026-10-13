#!/usr/bin/env bash
# Слайд 37. Путь от тестового файла до устройства.
set -euo pipefail
source /demo/common.sh
test -f "$SM3_ROOT/ready"

date -Is
uname -r
fio --version
iostat -V
findmnt -T "$SM3_ROOT/fio-lab"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT "$SM3_ROOT/fio-lab"
free -h
