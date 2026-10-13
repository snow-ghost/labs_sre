#!/usr/bin/env bash
# До занятия. Подготовить файл 2 ГиБ и проверить io_uring.
set -euo pipefail
source /demo/common.sh

sm3_check_tools
test ! -e "$SM3_ROOT" || {
  echo 'Каталог уже существует. Повторная подготовка запрещена.'
  exit 1
}
mkdir -p "$SM3_RESULTS"
cd "$SM3_ROOT"
sm3_prepare_file
sm3_fio probe --rw=randread --bs=4k --direct=1 \
  --ioengine=io_uring --iodepth=4 --runtime=3
sha256sum "$SM3_ROOT/fio-lab/test.bin" > "$SM3_ROOT/before.sha256"
touch "$SM3_ROOT/ready"
echo 'Подготовка завершена. Можно начинать с этапа 1.'
