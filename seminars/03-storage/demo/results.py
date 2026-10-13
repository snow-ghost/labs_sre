"""Вывести только запрошенные результаты, без пропуска отсутствующих запусков."""
from pathlib import Path
import json
import sys

folder = Path(sys.argv[1])
print("Запуск | IOPS | МиБ/с | p50, мс | p95, мс | p99, мс")
for name in sys.argv[2:]:
    path = folder / (name + ".json")
    timing = path.with_suffix(".time")
    if not timing.is_file() or timing.read_text().splitlines()[-1:] != ["exit=0"]:
        raise SystemExit(f"{name}: запуск не завершен успешно, результат не сравнивается")
    report = json.loads(path.read_text())
    if len(report["jobs"]) != 1:
        raise SystemExit(f"{name}: требуется одно задание")
    job = report["jobs"][0]
    data = job["read"]
    if job["error"] or not data["total_ios"]:
        raise SystemExit(f"{name}: ошибка или отсутствие чтений")
    percentiles = data["clat_ns"]["percentile"]
    delays = [percentiles[key] / 1_000_000 for key in
              ("50.000000", "95.000000", "99.000000")]
    print(name, round(data["iops"], 1), round(data["bw_bytes"] / 1048576, 2),
          *(round(value, 3) for value in delays), sep=" | ")
    print("Распределение глубины:", job["iodepth_level"])
