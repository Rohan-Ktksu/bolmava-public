"""Turn Locust's <prefix>_stats.csv into a Markdown table with p50/p95/p99, throughput, failures and the test hardware."""
import csv
import os
import platform
import sys


def hardware() -> str:
    cpu = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as f:
            cpu = next(line.split(":", 1)[1].strip() for line in f if line.startswith("model name"))
        with open("/proc/meminfo") as f:
            mem = f"{int(f.readline().split()[1]) / 1024 / 1024:.1f} GiB RAM"
    except (OSError, StopIteration):
        mem = "RAM unknown"
    return f"{platform.system()} {platform.release()}, {os.cpu_count()} logical CPUs ({cpu}), {mem}, Python {platform.python_version()}"


def main(stats_csv: str, settings: str) -> None:
    rows = list(csv.DictReader(open(stats_csv, newline="")))
    print(f"### Performance benchmark (fictional data, local disposable database)\n\n- Settings: {settings}\n- Hardware: {hardware()}\n")
    print("| Request | Count | Failures | p50 ms | p95 ms | p99 ms | Requests/s |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        name = "**All requests**" if r["Name"] == "Aggregated" else r["Name"]
        print(f"| {name} | {r['Request Count']} | {r['Failure Count']} | {r['50%']} | {r['95%']} | {r['99%']} | {float(r['Requests/s']):.1f} |")


if __name__ == "__main__":
    main(sys.argv[1], " ".join(sys.argv[2:]) or "unspecified")
