"""Собрать общие функции демонстрации из проверенного текста семинара."""
from pathlib import Path
import re
import subprocess

BASE = Path(__file__).resolve().parent


def build():
    raw = (BASE / "seminar-source.md").read_text()
    functions = re.findall(r"^sm3_[a-z_]+\(\) \{\n.*?^\}", raw, re.M | re.S)
    if len(functions) != 15:
        raise ValueError(f"Изменился состав функций семинара: {len(functions)}")
    header = '''#!/usr/bin/env bash
# Общие функции из seminar-source.md. Формирует build_demo.py.
grep -qw sm03_lab=1 /proc/cmdline || {
  printf '%s\\n' 'Этот скрипт запускается только внутри учебной ВМ.'
  exit 90
}
export PATH=/usr/bin:/bin:/sbin
trap 'printf "\\nЭтап прерван пользователем.\\n"; exit 130' INT
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
'''
    destination = BASE / "demo/common.sh"
    destination.write_text(header + "\n\n".join(functions) + "\n")
    for script in (BASE / "demo").glob("*.sh"):
        subprocess.run(["bash", "-n", str(script)], check=True)


if __name__ == "__main__":
    build()
