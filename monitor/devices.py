import logging
import subprocess
import threading
import time
import concurrent.futures

from config import DEVICES_IP_MAP

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Глобальний словник для зберігання статусу. Потокобезпечний у нашому випадку.
status = {}


def ping_device_robust(ip: str, retries: int = 3, timeout: int = 1) -> bool:
    """
    Надійно пінгує пристрій, роблячи кілька спроб.
    Повертає True, якщо хоча б одна спроба була успішною.
    """
    for i in range(retries):
        try:
            # Використовуємо 3 пакети для надійності, але чекаємо не більше `timeout` секунд
            # для всієї команди.
            # Опція -n (чисельний вивід) запобігає DNS-запитам.
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout), "-n", ip],
                capture_output=True,  # Захоплюємо вивід замість DEVNULL
                text=True,
                check=False,  # Не викидати виняток при ненульовому коді повернення
            )
            if result.returncode == 0:
                return True  # Успіх з першої ж вдалої спроби
            # Невелика пауза між спробами, щоб не "спамити" мережу
            if i < retries - 1:
                time.sleep(0.5)
        except (subprocess.SubprocessError, FileNotFoundError):
            # Помилка запуску процесу ping (наприклад, він не встановлений)
            return False
    # Якщо всі спроби були невдалі
    return False


def monitor_devices(interval: int = 10):
    """
    Моніторить пристрої паралельно, використовуючи ThreadPoolExecutor.
    """
    devices = DEVICES_IP_MAP

    while True:
        # Створюємо пул потоків для паралельного виконання завдань
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(devices)
        ) as executor:
            # Створюємо словник {future: device} для відстеження завдань
            future_to_device = {
                executor.submit(ping_device_robust, device["ip"]): device
                for device in devices
            }

            # Обробляємо результати по мірі їх надходження
            for future in concurrent.futures.as_completed(future_to_device):
                device = future_to_device[future]
                ip = device["ip"]
                name = device["name"]

                try:
                    is_alive = future.result()
                except Exception as e:
                    logger.error("Помилка при виконанні завдання: %s", str(e))
                    is_alive = False

                # Оновлюємо глобальний статус
                status[ip] = {
                    "ip": ip,
                    "name": name,
                    "alive": is_alive,  # Залишаємо один ключ замість двох (alive, offline)
                    "status": "🟢 ONLINE" if is_alive else "🔴 OFFLINE",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

        # Виводимо статус для демонстрації
        # print("\n--- Поточний статус пристроїв ---")
        # for ip, data in status.items():
        #     print(f"{data['name']:<20} {data['ip']:<15} {data['status']}")
        # print("----------------------------------\n")

        time.sleep(interval)


def start_monitoring():
    """Запускає моніторинг у фоновому потоці."""
    thread = threading.Thread(target=monitor_devices, args=(10,), daemon=True)
    thread.start()
    logger.info("🚀 Моніторинг запущено...")


# --- Приклад використання ---
if __name__ == "__main__":
    start_monitoring()

    # Головний потік може робити щось інше або просто чекати
    try:
        while True:
            # Демонстрація, що головний потік не заблокований
            time.sleep(1)
            # Можна додати логіку для виводу статусу тут, якщо потрібно
            # current_status = status.copy() # Копіюємо для безпечної ітерації
            # print(current_status)
    except KeyboardInterrupt:
        print("\n🛑 Моніторинг зупинено.")
