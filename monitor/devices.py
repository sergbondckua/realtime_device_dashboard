import logging
import subprocess
import threading
import time
import concurrent.futures
import platform

from config import DEVICES_IP_MAP

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Глобальний словник для зберігання статусу
status = {}

IS_WINDOWS = platform.system().lower() == "windows"


def ping_device_robust(ip: str, retries: int = 3, timeout: int = 1) -> bool:
    """
    Надійно пінгує пристрій, роблячи кілька спроб.
    Повертає True, якщо хоча б одна спроба була успішною.
    """
    for i in range(retries):
        try:
            if IS_WINDOWS:
                # -n <count> — кількість пакетів
                # -w <timeout> — таймаут у мілісекундах
                cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
            else:
                # Linux/Mac
                cmd = ["ping", "-c", "1", "-W", str(timeout), "-n", ip]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                return True
            if i < retries - 1:
                time.sleep(0.5)
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    return False


def monitor_devices(interval: int = 10):
    devices = DEVICES_IP_MAP

    while True:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
            future_to_device = {
                executor.submit(ping_device_robust, device["ip"]): device
                for device in devices
            }

            for future in concurrent.futures.as_completed(future_to_device):
                device = future_to_device[future]
                ip = device["ip"]
                name = device["name"]

                try:
                    is_alive = future.result()
                except Exception as e:
                    logger.error("Помилка при виконанні завдання: %s", str(e))
                    is_alive = False

                status[ip] = {
                    "ip": ip,
                    "name": name,
                    "alive": is_alive,
                    "status": "🟢 ONLINE" if is_alive else "🔴 OFFLINE",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

        time.sleep(interval)


def start_monitoring():
    """Запускає моніторинг у фоновому потоці."""
    thread = threading.Thread(target=monitor_devices, args=(10,), daemon=True)
    thread.start()
    logger.info("🚀 Моніторинг запущено...")
