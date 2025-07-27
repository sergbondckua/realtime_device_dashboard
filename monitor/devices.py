import subprocess
import threading
import time

from config import DEVICES_IP_MAP

status = {}


def ping_device(ip):
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False


def monitor_devices(interval=5):

    devices = DEVICES_IP_MAP

    while True:
        for device in devices:
            ip = device[0]
            name = device[0]
            alive = ping_device(ip)
            status[ip] = {
                "ip": ip,
                "name": name,
                "alive": alive,
                "offline": not alive,
                "status": "🟢 ONLINE" if alive else "🔴 OFFLINE",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        time.sleep(interval)


# Запуск в окремому потоці
def start_monitoring():
    thread = threading.Thread(target=monitor_devices, daemon=True)
    thread.start()
