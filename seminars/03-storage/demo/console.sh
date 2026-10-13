# Настройка интерактивной оболочки учебной ВМ.
export PATH=/usr/bin:/bin:/sbin
export LC_ALL=C.UTF-8
export TERM=xterm
export COLUMNS=140 LINES=40
stty cols 140 rows 40
export PS1='СМ3> '
cd /demo

steps() {
  printf '%s\n' \
    '0  Подготовка до занятия: файл 2 ГиБ и проба fio' \
    '1  Окружение и устройства               [слайд 37]' \
    '2  Фоновая нагрузка                    [слайд 38]' \
    '3  Буферизованное и прямое чтение       [слайд 39]' \
    '4  Глубина очереди                     [слайд 40]' \
    '5  Таблица результатов                 [слайд 41]' \
    '6  Создать стенд LVM                   [слайд 42]' \
    '7  Посмотреть тонкий пул               [слайд 43]' \
    '8  Создать снимок                      [слайд 44]' \
    '9  Удалить учебные объекты             [слайд 45]' \
    '' \
    'show 3                 Показать исходник этапа' \
    'run 3                  Запустить только этот этап' \
    'show_fn sm3_fio        Показать определение общей функции' \
    'show_fn sm3_check_loop Показать защитную проверку' \
    'steps                  Показать список этапов' \
    'finish                 Завершить ВМ и сохранить результаты'
}
step_file() {
  [[ ${1:-} =~ ^[0-9]$ ]] || { echo 'Нужен номер от 0 до 9.' >&2; return 1; }
  local files=(/demo/0"$1"-*.sh)
  test "${#files[@]}" -eq 1 && test -f "${files[0]}" || return 1
  printf '%s\n' "${files[0]}"
}
show() {
  local file
  file=$(step_file "${1:-}") || return 1
  nl -ba "$file"
}
show_fn() {
  [[ ${1:-} =~ ^sm3_[a-z_]+$ ]] || return 1
  # Показать исходные переносы строк, ничего не выполняя.
  awk -v signature="$1() {" '
    $0 == signature { active=1; seen=1 }
    active { print }
    active && $0 == "}" { exit }
    END { if (!seen) exit 1 }
  ' /demo/common.sh
}
run() {
  local file result
  file=$(step_file "${1:-}") || return 1
  printf '\nЗапуск: %s\n\n' "${file##*/}"
  bash "$file"
  result=$?
  printf '\nКод завершения: %s. Следующий этап сам не запускается.\n' "$result"
  return "$result"
}
finish() {
  if test -f /work/sm03/fio-lab/lvm.img; then
    local attached
    attached=$(losetup -j /work/sm03/fio-lab/lvm.img) || return 1
    if test -n "$attached"; then
      echo 'Образ LVM еще подключен. Сначала выполните очистку этапа 9.'
      return 1
    fi
  fi
  echo 'Завершение демонстрации. Журнал сохранится на компьютере.'
  exit
}
echo 'Учебная ВМ готова. Команды практикума еще не выполнялись.'
steps
