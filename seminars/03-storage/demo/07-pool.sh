#!/usr/bin/env bash
# Слайд 43. Емкость, расход данных и метаданных, свободное место группы.
set -euo pipefail
source /demo/common.sh
sm3_load_lvm

sudo lvs -a -o \
  lv_name,lv_size,pool_lv,data_percent,metadata_percent,seg_monitor "$SM3_VG"
sudo vgs -o vg_name,vg_size,vg_free "$SM3_VG"
sudo lvmconfig --type full activation/thin_pool_autoextend_threshold
sudo lvmconfig --type full activation/thin_pool_autoextend_percent
echo 'В этой ВМ нет службы наблюдения. Авторасширение здесь не работает.'
