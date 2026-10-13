#!/usr/bin/env bash
# Общие функции из seminar-source.md. Формирует build_demo.py.
grep -qw sm03_lab=1 /proc/cmdline || {
  printf '%s\n' 'Этот скрипт запускается только внутри учебной ВМ.'
  exit 90
}
export PATH=/usr/bin:/bin:/sbin
trap 'printf "\nЭтап прерван пользователем.\n"; exit 130' INT
trap 'exit 143' TERM
SM3_ROOT=/work/sm03
SM3_RESULTS=$SM3_ROOT/fio-lab/results
sudo() { "$@"; }

sm3_load_lvm() {
  local -a saved
  test -f "$SM3_ROOT/fio-lab/lvm-state.txt" || {
    echo 'Нет состояния LVM. Сначала выполните этап 6.'
    return 1
  }
  mapfile -t saved < "$SM3_ROOT/fio-lab/lvm-state.txt" || return 1
  test "${#saved[@]}" -eq 3 || return 1
  SM3_IMAGE=${saved[0]}
  SM3_LOOP=${saved[1]}
  SM3_VG=${saved[2]}
  sm3_check_loop
}

sm3_observe() {
  LC_ALL=C S_TIME_FORMAT=ISO iostat -x -y -t -k 1 >> "$SM3_ROOT/iostat.txt" &
  observer=$!
  trap 'kill "$observer" 2>/dev/null || true; wait "$observer" 2>/dev/null || true' EXIT
}

sm3_table() {
  python3 /demo/results.py "$SM3_RESULTS" "$@"
}
sm3_check_tools() {
  local tool
  for tool in fio iostat pidstat lvm thin_check losetup python3; do
    command -v "$tool" || return 1
  done
  sudo modprobe loop || return 1
  sudo modprobe dm_thin_pool || return 1
  sudo modprobe dm_snapshot || return 1
}

sm3_prepare_directory() {
  SM3_ROOT=$(mktemp -d "$(pwd -P)/sm3.XXXXXX") || return 1
  cd "$SM3_ROOT" || return 1
  mkdir fio-lab || return 1
  pwd
  findmnt -T ./fio-lab || return 1
  df -hT ./fio-lab || return 1
  lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
}

sm3_prepare_file() {
  test "$PWD" = "${SM3_ROOT:?}" || return 1
  test ! -e ./fio-lab/test.bin || return 1
  test ! -L ./fio-lab/test.bin || return 1
  fio --name=prepare --filename=./fio-lab/test.bin \
    --size=2G --rw=write --bs=1M --ioengine=psync \
    --direct=1 --end_fsync=1 --group_reporting=1 \
    --output-format=json --output=./fio-lab/prepare.json || return 1
  stat -c '%n %s bytes' ./fio-lab/test.bin
}

sm3_new_results() {
  local next_results
  next_results=$(mktemp -d "${SM3_ROOT:?}/fio-lab/results.XXXXXX") \
    || return 1
  SM3_RESULTS=$next_results
  printf '%s\n' "$SM3_RESULTS"
}

sm3_fio() {
  local name="${1:?}" status out
  shift
  [[ "$name" =~ ^[a-zA-Z0-9-]+$ ]] || return 1
  out="${SM3_RESULTS:?}/$name.json"
  if test -e "$out" || test -L "$out" \
    || test -e "$SM3_RESULTS/$name.time" \
    || test -L "$SM3_RESULTS/$name.time"; then
    printf 'Результат уже существует: %s\n' "$out"
    return 1
  fi
  date -Is > "$SM3_RESULTS/$name.time" || return 1
  if fio --readonly --allow_file_create=0 --name="$name" \
    --filename="${SM3_ROOT:?}/fio-lab/test.bin" --size=2G \
    --numjobs=1 --time_based=1 --group_reporting=1 \
    --output-format=json --output="$out" "$@"; then
    status=0
  else
    status=$?
  fi
  date -Is >> "$SM3_RESULTS/$name.time" || return 1
  printf 'exit=%s\n' "$status" >> "$SM3_RESULTS/$name.time" || return 1
  return "$status"
}

sm3_compare_cache() {
  local pass
  for pass in 1 2; do
    sm3_fio "bufread-$pass" --rw=read --bs=1M --direct=0 \
      --ioengine=psync --iodepth=1 --runtime=45 || return 1
  done
  sm3_fio dirread --rw=read --bs=1M --direct=1 \
    --ioengine=psync --iodepth=1 --runtime=45
}

sm3_compare_depth() {
  local depth
  for depth in 1 4 16 64; do
    sm3_fio "rr-q$depth" --rw=randread --bs=4k --direct=1 \
      --ioengine=io_uring --iodepth="$depth" --ramp_time=5 \
      --runtime=30 || return 1
  done
}

sm3_check_loop() {
  local details backing
  [[ ${SM3_LOOP:-} =~ ^/dev/loop[0-9]+$ ]] || return 1
  [[ ${SM3_VG:-} =~ ^vg_sm3_[0-9]+_[0-9]+$ ]] || return 1
  test "${SM3_IMAGE:-}" = "${SM3_ROOT:?}/fio-lab/lvm.img" || return 1
  test -f "${SM3_IMAGE:-}" || return 1
  test ! -L "$SM3_IMAGE" || return 1
  test -b "$SM3_LOOP" || return 1
  details=$(sudo losetup --list --json --output BACK-FILE \
    "$SM3_LOOP") || return 1
  backing=$(printf '%s\n' "$details" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["loopdevices"][0]["back-file"])') \
    || return 1
  test "$backing" = "$SM3_IMAGE" || return 1
  test "$(sudo losetup --list --noheadings --raw \
    --output OFFSET "$SM3_LOOP")" = 0 || return 1
  test "$(sudo blockdev --getsize64 "$SM3_LOOP")" = 4294967296
}

sm3_prepare_lvm() {
  test "$PWD" = "${SM3_ROOT:?}" || return 1
  test ! -e "$SM3_ROOT/fio-lab/lvm.img" || return 1
  test ! -L "$SM3_ROOT/fio-lab/lvm.img" || return 1
  SM3_IMAGE="$SM3_ROOT/fio-lab/lvm.img"
  SM3_VG="vg_sm3_$(date +%s)_$$"
  sudo vgs -o vg_name >/dev/null || return 1
  if sudo vgs "$SM3_VG" >/dev/null 2>&1; then
    printf '%s\n' 'Такая группа уже существует. Остановка.'
    return 1
  fi
  truncate -s 4G "$SM3_IMAGE" || return 1
  SM3_LOOP=$(sudo losetup --find --show --nooverlap "$SM3_IMAGE") \
    || return 1
  printf '%s\n' "$SM3_IMAGE" "$SM3_LOOP" "$SM3_VG" \
    > ./fio-lab/lvm-state.txt || return 1
  sm3_check_loop || return 1
  sudo losetup --list "$SM3_LOOP" || return 1
  lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$SM3_LOOP"
}

sm3_create_lvm() {
  sm3_check_loop || return 1
  sudo pvcreate "$SM3_LOOP" || return 1
  sudo vgcreate "$SM3_VG" "$SM3_LOOP" || return 1
  sudo lvcreate --type thin-pool -n pool -L 3G \
    "$SM3_VG" || return 1
  sudo lvcreate --type thin -n app -V 8G \
    --thinpool pool "$SM3_VG" || return 1
  sudo lvs -a -o+devices "$SM3_VG"
}

sm3_snapshot() {
  sm3_check_loop || return 1
  test "$(sudo pvs --noheadings -o vg_name "$SM3_LOOP" \
    | tr -d '[:space:]')" = "$SM3_VG" || return 1
  sudo lvcreate --snapshot -n app_snap "$SM3_VG/app" || return 1
  sudo lvs -a -o \
    lv_name,origin,pool_lv,data_percent,metadata_percent "$SM3_VG"
}

sm3_check_vg() {
  local names
  sm3_check_loop || return 1
  test "$(sudo pvs --noheadings -o vg_name "$SM3_LOOP" \
    | tr -d '[:space:]')" = "${SM3_VG:?}" || return 1
  test "$(sudo pvs --noheadings -o pv_name \
    --select "vg_name=$SM3_VG" | tr -d '[:space:]')" = "$SM3_LOOP" \
    || return 1
  names=$(sudo lvs --noheadings -o lv_name "$SM3_VG") || return 1
  names=$(printf '%s\n' "$names" | awk '{$1=$1;print}' | LC_ALL=C sort)
  test "$names" = $'app\napp_snap\npool'
}

sm3_verify_detached() {
  local attempt attached
  for attempt in 1 2 3 4 5; do
    attached=$(sudo losetup -j "${SM3_IMAGE:?}") || return 1
    test -z "$attached" && return 0
    sleep 1
  done
  printf '%s\n' 'Образ еще подключен; сохраните его и проверьте потребителей.'
  return 1
}

sm3_cleanup() {
  local lv
  sm3_check_vg || return 1
  for lv in app_snap app pool; do
    sudo lvremove "$SM3_VG/$lv" || return 1
  done
  sudo vgremove "$SM3_VG" || return 1
  sm3_check_loop || return 1
  sudo pvremove "$SM3_LOOP" || return 1
  sudo losetup -d "$SM3_LOOP" || return 1
  sm3_verify_detached
}

sm3_restore_state() {
  local saved
  local -a state
  read -r -p 'Рабочий каталог SM3_ROOT: ' saved || return 1
  test -d "$saved/fio-lab" || return 1
  SM3_ROOT=$(cd "$saved" && pwd -P) || return 1
  mapfile -t state < "$SM3_ROOT/fio-lab/lvm-state.txt" || return 1
  test "${#state[@]}" -eq 3 || return 1
  SM3_IMAGE=${state[0]}
  SM3_LOOP=${state[1]}
  SM3_VG=${state[2]}
  test "$SM3_IMAGE" = "$SM3_ROOT/fio-lab/lvm.img" || return 1
  [[ "$SM3_LOOP" =~ ^/dev/loop[0-9]+$ ]] || return 1
  [[ "$SM3_VG" =~ ^vg_sm3_[0-9]+_[0-9]+$ ]] || return 1
  cd "$SM3_ROOT" || return 1
  sudo losetup -j "$SM3_IMAGE" || return 1
  printf 'Образ: %s\nУстройство: %s\nГруппа: %s\n' \
    "$SM3_IMAGE" "$SM3_LOOP" "$SM3_VG"
}
