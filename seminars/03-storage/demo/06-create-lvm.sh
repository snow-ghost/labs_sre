#!/usr/bin/env bash
# Слайд 42. Новый образ, петлевое устройство, группа, пул и тонкий том.
set -euo pipefail
source /demo/common.sh
test -f "$SM3_ROOT/ready"
cd "$SM3_ROOT"

sm3_prepare_lvm
sm3_check_loop
sudo pvcreate "$SM3_LOOP"
sudo vgcreate "$SM3_VG" "$SM3_LOOP"
sudo lvcreate --type thin-pool -n pool -L 3G "$SM3_VG"
sudo lvcreate --type thin -n app -V 8G --thinpool pool "$SM3_VG"
sudo lvs -a -o+devices "$SM3_VG"
