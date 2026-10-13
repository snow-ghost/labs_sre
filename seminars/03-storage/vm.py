"""Изолированный прогон команд СМ3 в QEMU. Хостовые диски в ВМ не передаются."""

from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess
import sys
import argparse
import fcntl
import json
import platform
import tempfile
import time


BASE = Path(__file__).resolve().parent
CACHE = BASE / "cache"
PACKAGES = CACHE / "packages"
KERNEL_VERSION = platform.release()
MANUSCRIPT = BASE / "seminar-source.md"
WORK = ROOTFS = None
MODE = None


def check_host():
    if os.geteuid() == 0:
        raise ValueError("Запускайте от обычного пользователя, без sudo")
    if platform.machine() != "x86_64" or sys.version_info[:2] != (3, 12):
        raise ValueError("Стенд подготовлен для Ubuntu 24.04 x86_64 и Python 3.12")
    required = ("qemu-system-x86_64 qemu-img busybox cpio gzip zstd curl apt-cache "
                "dpkg-deb ldd find bash lsblk findmnt losetup blockdev truncate stat "
                "date mktemp tr sort awk tee iostat pidstat mkfs.ext4 lvm dmsetup "
                "thin_check thin_dump thin_repair sha256sum modprobe debugfs")
    missing = [name for name in required.split() if not shutil.which(name)]
    if missing:
        raise ValueError("Нужны команды: " + ", ".join(missing) + ". См. README.txt")
    with open("/dev/kvm", "rb+", buffering=0):
        pass
    if not (Path("/lib/modules") / KERNEL_VERSION).is_dir():
        raise ValueError("Нет модулей для ядра " + KERNEL_VERSION)
    free = shutil.disk_usage(BASE).free / 1024**3
    if free < 20:
        raise ValueError(f"Свободно {free:.1f} ГиБ; нужно не менее 20 ГиБ")
    memory = re.search(r"^MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text(), re.M)
    if not memory or int(memory[1]) < 5 * 1024**2:
        raise ValueError("Для запуска нужно не менее 5 ГиБ доступной памяти")
    for module in ("loop", "dm-thin-pool", "dm-snapshot", "ext4", "virtio_blk", "virtio_pci"):
        subprocess.run(["modprobe", "--show-depends", "--set-version", KERNEL_VERSION,
                        module], check=True, stdout=subprocess.DEVNULL)
    print(f"Готовность: KVM доступен, ядро {KERNEL_VERSION}, свободно {free:.1f} ГиБ.", flush=True)
    print("Системная установка fio не требуется: используется пакет внутри ВМ.", flush=True)


def download_package(name):
    metadata = subprocess.check_output(["apt-cache", "show", name], text=True)
    filename = re.search(r"^Filename: (.+)$", metadata, re.M)[1]
    checksum = re.search(r"^SHA256: (.+)$", metadata, re.M)[1]
    output = CACHE / Path(filename).name
    if not output.exists():
        partial = output.with_suffix(".partial")
        subprocess.run(["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "120",
                        "-o", str(partial), "https://archive.ubuntu.com/ubuntu/" + filename], check=True)
        if hashlib.sha256(partial.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Контрольная сумма загрузки {name} не совпала")
        partial.replace(output)
    if hashlib.sha256(output.read_bytes()).hexdigest() != checksum:
        raise ValueError(f"Контрольная сумма пакета {name} не совпала")
    subprocess.run(["dpkg-deb", "-x", str(output), str(PACKAGES)], check=True)
    print("Пакет проверен:", name, flush=True)


def copy_file(source, destination=None):
    source = Path(source)
    target = ROOTFS / str(destination or source).lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target, follow_symlinks=True)
    return target


def copy_binary(source, destination=None):
    copy_file(source, destination)
    env = dict(os.environ, LD_LIBRARY_PATH=str(PACKAGES / "usr/lib/x86_64-linux-gnu"))
    result = subprocess.run(["ldd", str(source)], env=env, text=True, capture_output=True)
    if "not found" in result.stdout:
        raise RuntimeError(result.stdout)
    for library in re.findall(r"(?:=> )?(/[\w/+.\-]+)", result.stdout):
        original = Path(library)
        if original.is_relative_to(PACKAGES):
            destination = Path("/") / original.relative_to(PACKAGES)
        else:
            destination = original
        copy_file(original, destination)


def write_asset(name, data, mode=0o644):
    path = ROOTFS / name.lstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    path.chmod(mode)


def main():
    if MODE not in ("full", "lvm", "demo"):
        raise ValueError("Режим: full, lvm или demo")
    if WORK.parent != BASE / "runs" or not WORK.name.startswith("run-"):
        raise ValueError("Недопустимый каталог прогона")
    for name in ("fio", "linux-image-" + KERNEL_VERSION, "libgfapi0", "libgfrpc0",
                 "libgfxdr0", "libglusterfs0", "libnbd0"):
        download_package(name)
    for folder in ("bin", "sbin", "proc", "sys", "dev", "tmp", "run", "work", "etc/lvm"):
        (ROOTFS / folder).mkdir(parents=True, exist_ok=True)
    copy_file("/usr/bin/busybox", "/bin/busybox")
    applets = subprocess.check_output(["/usr/bin/busybox", "--list"], text=True).split()
    for applet in applets:
        path = ROOTFS / "bin" / applet
        if not path.exists():
            path.symlink_to("busybox")
    for binary in ("bash", "lsblk", "findmnt", "losetup", "blockdev", "truncate", "stat",
                   "date", "mktemp", "tr", "sort", "awk", "tee", "iostat", "pidstat",
                   "mkfs.ext4", "lvm", "dmsetup", "thin_check", "thin_dump", "thin_repair",
                   "sha256sum", "modprobe"):
        source = shutil.which(binary)
        if not source:
            raise ValueError(f"Отсутствует {binary}")
        copy_binary(source, "/usr/bin/" + binary)
    # Python нужен для проверки настоящих JSON fio внутри гостевой машины.
    copy_binary("/usr/bin/python3.12", "/usr/bin/python3")
    shutil.copytree("/usr/lib/python3.12", ROOTFS / "usr/lib/python3.12", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "test", "tests"))
    for binary in (ROOTFS / "usr/lib/python3.12/lib-dynload").glob("*.so"):
        # Модули уже скопированы; переносим только их динамические зависимости.
        result = subprocess.run(["ldd", str(binary)], text=True, capture_output=True)
        for lib in re.findall(r"(?:=> )?(/[\w/+.\-]+)", result.stdout):
            if Path(lib).is_file():
                copy_file(lib)
    copy_binary(PACKAGES / "usr/bin/fio", "/usr/bin/fio")
    for name in ("pvs", "vgs", "lvs", "pvcreate", "pvremove", "vgcreate", "vgremove",
                 "lvcreate", "lvremove", "lvchange", "lvmconfig"):
        path = ROOTFS / "usr/bin" / name
        if not path.exists():
            path.symlink_to("lvm")
    # Пути этих вспомогательных программ заданы при сборке LVM.
    (ROOTFS / "usr/sbin").mkdir(parents=True, exist_ok=True)
    for name in ("thin_check", "thin_dump", "thin_repair", "modprobe"):
        link = ROOTFS / "usr/sbin" / name
        if not link.exists():
            link.symlink_to("../bin/" + name)
    modules = []
    for name in ("loop", "dm-thin-pool", "dm-snapshot", "ext4", "virtio_blk", "virtio_pci"):
        out = subprocess.check_output(["modprobe", "--show-depends", "--set-version",
                                       KERNEL_VERSION, name], text=True)
        for module in re.findall(r"^insmod (\S+)", out, re.M):
            if module not in modules:
                modules.append(module)
    module_dir = Path("/lib/modules") / KERNEL_VERSION
    for path in module_dir.glob("modules.*"):
        if path.is_file():
            copy_file(path)
    load = []
    for index, module in enumerate(modules):
        copy_file(module)
        target = ROOTFS / f"module-{index}.ko"
        if module.endswith(".zst"):
            with target.open("wb") as output:
                subprocess.run(["zstd", "-dc", module], stdout=output, check=True)
        elif module.endswith(".ko"):
            shutil.copy2(module, target)
        else:
            raise ValueError("Неподдерживаемое сжатие модуля: " + module)
        load.append(f"insmod /module-{index}.ko || exit 1")
    modprobe_alias = ROOTFS / "sbin/modprobe"
    if not modprobe_alias.exists():
        modprobe_alias.symlink_to("../usr/bin/modprobe")
    write_asset("/etc/passwd", "root:x:0:0:root:/root:/usr/bin/bash\n")
    write_asset("/etc/group", "root:x:0:\n")
    write_asset("/etc/lvm/lvm.conf", "devices { use_devicesfile=0 }\n"
                "activation { udev_sync=0 udev_rules=0 monitoring=0 }\n")
    guest_command = "/usr/bin/bash /run-seminar.sh"
    if MODE == "demo":
        from build_demo import build
        build()
        shutil.copytree("/usr/lib/locale/C.utf8", ROOTFS / "usr/lib/locale/C.utf8")
        shutil.copytree(BASE / "demo", ROOTFS / "demo")
        shutil.copytree(BASE / "demo", WORK / "scripts")
        guest_command = (
            "setsid -c /usr/bin/bash --noprofile --rcfile /demo/console.sh -i "
            "</dev/ttyS0 >/dev/ttyS0 2>&1"
        )
    write_asset("/init", "#!/bin/sh\nexport PATH=/usr/bin:/bin:/sbin\n"
                "test \"$$\" -eq 1 || exit 90\n"
                "mount -t proc proc /proc\nmount -t sysfs sysfs /sys\n"
                "grep -qw sm03_lab=1 /proc/cmdline || exit 91\n"
                "mount -t devtmpfs devtmpfs /dev\nmkdir -p /dev/pts /run/lvm\n"
                "mount -t devpts devpts /dev/pts\n" + "\n".join(load) + "\n"
                "mkfs.ext4 -q /dev/vda || { poweroff -f; exit 1; }\n"
                "mount /dev/vda /work || { poweroff -f; exit 1; }\n"
                + guest_command + "\nresult=$?\n"
                "echo SM03_GUEST_EXIT=$result\nsync\npoweroff -f\n", 0o755)
    raw = MANUSCRIPT.read_text()
    prep = raw.split("\n## Слайд 34.")[0]
    blocks = re.findall(r"```bash\n(.*?)\n```", prep, re.S)
    run = ["#!/usr/bin/bash", "set -eu -o pipefail", "export PATH=/usr/bin:/bin:/sbin",
           "grep -qw sm03_lab=1 /proc/cmdline || { echo 'Только внутри учебной ВМ'; exit 90; }",
           "cd /work", "sudo() { if [[ $1 == lvremove ]]; then shift; "
           "command lvremove --yes \"$@\"; else \"$@\"; fi; }", "export -f sudo",
           "trap 'echo SM03_FAILED_LINE=$LINENO' ERR", "echo SM03_BEGIN",
           "uname -r", "fio --version", "lvm version",
           "mkdir -p '/work/учебный каталог'", "cd '/work/учебный каталог'"]
    for block in blocks:
        if MODE == "lvm" and block.startswith(("sm3_prepare_file()", "sm3_new_results()")):
            continue
        run.append(block)
    run += ["echo SM03_PREPARE_PASS", "printf '%s\\n' \"$SM3_ROOT\" > /work/root-path.txt"]
    if MODE == "full":
        run.append("sha256sum ./fio-lab/test.bin > /work/before.sha256")
    run += ["LC_ALL=C S_TIME_FORMAT=ISO iostat -x -y -t -k 1 > /work/iostat.txt &",
            "observer=$!"]
    pieces = re.split(r"(?m)^## Слайд (\d+)\.[^\n]*\n", raw)
    sections = {int(pieces[i]): pieces[i+1] for i in range(1, len(pieces), 2)}
    # Нагрузки запускаются с размерами и длительностями из документа.
    for number in ((39, 40, 42, 44, 45) if MODE == "full" else (42, 44, 45)):
        section = sections[number].split("\n## Приложения")[0]
        selected = re.findall(r"```bash\n(.*?)\n```", section, re.S)
        for block in selected:
            if number == 45 and "sm3_cleanup()" in block:
                block = block.rsplit("\nsm3_cleanup", 1)[0]
                block += '\nlvcreate --snapshot -n extra "$SM3_VG/app"\n'
                block += 'if sm3_check_vg; then exit 72; fi\n'
                block += 'echo SM03_EXTRA_LV_REJECTED\n'
                block += 'lvremove -y "$SM3_VG/extra"\n'
                # Согласие на удаление относится только к этой одноразовой гостевой ВМ.
                block += "\nsm3_cleanup"
            run.append(block)
        run.append(f"echo SM03_SLIDE_{number}_PASS")
        if number == 42:
            run += ["saved_loop=$SM3_LOOP", "saved_vg=$SM3_VG",
                    "SM3_LOOP=/dev/vda; if sm3_check_loop; then exit 71; fi",
                    "SM3_LOOP=$saved_loop", "echo SM03_WRONG_DEVICE_REJECTED"]
        if number == 44:
            run += ["echo SM03_LVM_STATE", "lvs -a -o+data_percent,metadata_percent,devices \"$SM3_VG\"",
                    "vgs -o vg_name,vg_size,vg_free \"$SM3_VG\""]
    run += ["kill $observer", "test -s /work/iostat.txt", "echo SM03_IOSTAT_PASS"]
    if MODE == "full":
        run += ["sha256sum -c /work/before.sha256", "echo SM03_INPUT_UNCHANGED",
                "printf '%s\\n' \"$SM3_RESULTS\" > /work/results-path.txt"]
        extractor = re.search(r"```bash\n(python3 - .*?\nPY)\n```", raw, re.S)
        run += ["(\n" + extractor[1] + "\n) | tee /work/summary.txt", "echo SM03_JSON_PASS"]
    run += [f"echo SM03_MODE={MODE}", "echo SM03_ALL_PASS"]
    write_asset("/run-seminar.sh", "\n".join(run)+"\n", 0o755)
    shutil.copy2(ROOTFS / "run-seminar.sh", WORK / "guest-script.sh")
    subprocess.run(["bash", "-n", str(WORK / "guest-script.sh")], check=True)
    # Гостевая система не получает общих каталогов или сетевых интерфейсов.
    initramfs = WORK / "initramfs.gz"
    with initramfs.open("wb") as output:
        find = subprocess.Popen(["find", ".", "-print0"], cwd=ROOTFS, stdout=subprocess.PIPE)
        cpio = subprocess.Popen(["cpio", "--null", "-o", "--format=newc", "--owner=0:0"],
                                cwd=ROOTFS, stdin=find.stdout, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        find.stdout.close()
        gzip = subprocess.run(["gzip", "-1"], stdin=cpio.stdout, stdout=output, check=True)
        cpio.stdout.close()
        cpio.communicate()
        if cpio.returncode or find.wait():
            raise RuntimeError("Ошибка упаковки проверочной ВМ")
    disk = WORK / "guest.raw"
    if disk.exists():
        raise ValueError("Для каждого прогона требуется новый guest.raw")
    subprocess.run(["qemu-img", "create", "-f", "raw", str(disk), "16G"], check=True)
    kernel = PACKAGES / "boot" / f"vmlinuz-{KERNEL_VERSION}"
    print("Запуск QEMU: два процессора, 4 ГиБ памяти, только новый виртуальный диск.", flush=True)
    if MODE == "demo":
        launch_demo(kernel, initramfs, disk)
        return
    with (WORK / "serial.log").open("w") as serial:
        process = subprocess.Popen([
            "qemu-system-x86_64", "-enable-kvm", "-m", "4096", "-smp", "2",
            "-nographic", "-no-reboot", "-nic", "none",
            "-kernel", str(kernel), "-initrd", str(initramfs),
            "-append", "console=ttyS0 loglevel=3 panic=1 sm03_lab=1",
            "-drive", f"file={str(disk).replace(',', ',,')},format=raw,if=virtio,cache=none",
        ], stdout=serial, stderr=subprocess.STDOUT)
        started = time.monotonic()
        try:
            while process.poll() is None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    elapsed = int(time.monotonic() - started)
                    print(f"ВМ работает: {elapsed} с. Журнал: {WORK / 'serial.log'}", flush=True)
                    if elapsed > 900:
                        raise TimeoutError("Превышено 15 минут")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if process.returncode:
            raise RuntimeError(f"QEMU завершился с кодом {process.returncode}")
    log = (WORK / "serial.log").read_text(errors="replace")
    print("\n".join(line for line in log.splitlines() if "SM03_" in line), flush=True)
    if "SM03_ALL_PASS" not in log or "SM03_GUEST_EXIT=0" not in log:
        print(log[-6000:])
        raise SystemExit("Проверочный прогон не завершился успешно")
    export_results(disk)
    print(f"ПРОВЕРКА ПРОЙДЕНА. Результаты: {WORK / 'results'}", flush=True)


def launch_demo(kernel, initramfs, disk):
    """Живая консоль: каждый этап запускает преподаватель, лимита 15 минут нет."""
    log = str(WORK / "serial.log").replace(",", ",,")
    command = [
        "qemu-system-x86_64", "-enable-kvm", "-m", "4096", "-smp", "2",
        "-display", "none", "-monitor", "none", "-no-reboot", "-nic", "none",
        "-chardev", f"stdio,id=classroom,signal=off,logfile={log}",
        "-serial", "chardev:classroom", "-kernel", str(kernel), "-initrd", str(initramfs),
        "-append", "console=ttyS0 loglevel=3 panic=1 sm03_lab=1",
        "-drive", f"file={str(disk).replace(',', ',,')},format=raw,if=virtio,cache=none",
    ]
    print("Внутри ВМ: show 0, run 0; затем show 1, run 1. Выход: finish.", flush=True)
    process = subprocess.Popen(command)
    try:
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if process.returncode:
        raise RuntimeError(f"Демонстрация прервана, код QEMU: {process.returncode}")
    destination = WORK / "results"
    destination.mkdir()
    paths = {"iostat.txt": "/sm03/iostat.txt", "lvm-state.txt": "/sm03/fio-lab/lvm-state.txt"}
    for name in ("probe", "bufread-1", "bufread-2", "dirread", "rr-q1", "rr-q4", "rr-q16", "rr-q64"):
        for extension in ("json", "time"):
            paths[f"{name}.{extension}"] = f"/sm03/fio-lab/results/{name}.{extension}"
    for name, path in paths.items():
        result = subprocess.run(["debugfs", "-R", f'cat "{path}"', str(disk)],
                                capture_output=True, check=True)
        if result.stdout and b"File not found" not in result.stderr:
            (destination / name).write_bytes(result.stdout)
    (destination / "status.txt").write_text(
        "Интерактивная демонстрация завершена. Выполненные этапы и коды: ../serial.log\n"
        "Наличие этого файла не означает, что преподаватель выполнил все этапы.\n")
    print(f"\nЖурнал демонстрации: {WORK / 'serial.log'}")
    print(f"Сохраненные результаты: {destination}")


def export_results(disk):
    """Чтение только своего отключенного образа, без монтирования на хосте."""
    destination = WORK / "results"
    destination.mkdir()
    def read_guest(path):
        result = subprocess.run(["debugfs", "-R", f'cat "{path}"', str(disk)],
                                capture_output=True, check=True)
        if b"File not found" in result.stderr or not result.stdout:
            raise ValueError("Нет результата в гостевой системе: " + path)
        return result.stdout
    (destination / "iostat.txt").write_bytes(read_guest("/iostat.txt"))
    if MODE == "full":
        folder = read_guest("/results-path.txt").decode().strip()
        if not re.fullmatch(r"/work/учебный каталог/sm3\.[A-Za-z0-9]+/fio-lab/results\.[A-Za-z0-9]+", folder):
            raise ValueError("Неожиданный путь гостевых результатов")
        folder = folder.removeprefix("/work")
        for name in ["bufread-1", "bufread-2", "dirread", "rr-q1", "rr-q4", "rr-q16", "rr-q64"]:
            data = read_guest(f"{folder}/{name}.json")
            job = json.loads(data)["jobs"][0]
            if job["error"] or not job["read"]["total_ios"]:
                raise ValueError("Ошибка измерения " + name)
            (destination / (name + ".json")).write_bytes(data)
            (destination / (name + ".time")).write_bytes(read_guest(f"{folder}/{name}.time"))
        (destination / "summary.txt").write_bytes(read_guest("/summary.txt"))
    (destination / "status.txt").write_text(
        f"Проверка пройдена. Режим: {MODE}. Ядро: {KERNEL_VERSION}.\n"
        "Подробности выполнения и версии инструментов: ../serial.log\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Семинар 3: отдельная ВМ, без sudo на хосте")
    parser.add_argument("mode", choices=("check", "full", "lvm", "demo"))
    MODE = parser.parse_args().mode
    try:
        check_host()
        if MODE == "demo" and not sys.stdin.isatty():
            raise ValueError("Для демонстрации откройте обычный терминал и запустите bash demo.sh")
        if MODE != "check":
            CACHE.mkdir(exist_ok=True)
            with (CACHE / ".lock").open("w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError("Другой прогон уже работает; дождитесь его завершения") from None
                (BASE / "runs").mkdir(exist_ok=True)
                WORK = Path(tempfile.mkdtemp(prefix="run-", dir=BASE / "runs"))
                ROOTFS = WORK / "root"
                print("Каталог прогона:", WORK, flush=True)
                main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Ошибка: {error}\n")
