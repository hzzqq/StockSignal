"""
StockSignal 服务启动等待脚本

用法：python wait_for_service.py <url> <log_file> <timeout_seconds>

循环请求给定 URL，直到成功或超时。每 1 秒探测一次，单次请求超时 2 秒。
"""
import sys
import time
import urllib.request


def main() -> int:
    if len(sys.argv) < 4:
        print("用法: wait_for_service.py <url> <log_file> <timeout_seconds>", file=sys.stderr)
        return 2

    url = sys.argv[1]
    log_path = sys.argv[2]
    timeout = int(sys.argv[3])

    with open(log_path, "w", encoding="utf-8") as log:
        t0 = time.time()
        n = 0
        log.write(f"waiting for {url} (timeout {timeout}s)\n")
        log.flush()

        while time.time() - t0 < timeout:
            n += 1
            try:
                urllib.request.urlopen(url, timeout=2)
                log.write(f"[{n}] OK\n")
                log.flush()
                return 0
            except Exception as e:  # noqa: BLE001
                log.write(f"[{n}] {type(e).__name__}: {e}\n")
                log.flush()
                if n in (10, 30, 60, 90, 120, 150):
                    print(f"  健康检查 #{n} 仍未就绪...", flush=True)
                time.sleep(1)

        log.write("TIMEOUT\n")
        log.flush()
        return 1


if __name__ == "__main__":
    sys.exit(main())
