#!/usr/bin/env bash
# Слайд 44. Снимок пустого тонкого тома.
set -euo pipefail
source /demo/common.sh
sm3_load_lvm

test "$(sudo pvs --noheadings -o vg_name "$SM3_LOOP" \
  | tr -d '[:space:]')" = "$SM3_VG"
sudo lvcreate --snapshot -n app_snap "$SM3_VG/app"
sudo lvs -a -o \
  lv_name,origin,pool_lv,data_percent,metadata_percent "$SM3_VG"
