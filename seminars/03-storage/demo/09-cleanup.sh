#!/usr/bin/env bash
# Слайд 45. Проверить принадлежность объектов и удалить их по порядку.
set -euo pipefail
source /demo/common.sh
sm3_load_lvm
sm3_check_vg

# Подтверждения y вводятся вручную после проверки имени объекта.
for lv in app_snap app pool; do
  sudo lvremove "$SM3_VG/$lv"
done
sudo vgremove "$SM3_VG"
sm3_check_loop
sudo pvremove "$SM3_LOOP"
sudo losetup -d "$SM3_LOOP"
sm3_verify_detached
touch "$SM3_ROOT/cleaned"
echo 'Учебные объекты удалены. Файл образа и результаты сохранены.'
