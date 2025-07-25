import re
import subprocess
import platform
import logging
from typing import List, Tuple, Optional, Dict, Any

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class SNMPToolsChecker:
    """Клас для перевірки наявності SNMP-інструментів в системі"""

    # Константи для конфігурації
    TIMEOUT = 5

    @classmethod
    def is_installed(cls) -> bool:
        """
        Перевіряє, чи встановлені ВСІ необхідні SNMP-інструменти в системі.
        Повертає True, лише якщо всі інструменти доступні.
        """

        try:
            # Перевіряємо кожну команду, передаючи її назву
            subprocess.run(
                ["snmpwalk", "-V"],  # "-V" для перевірки версії
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=cls.TIMEOUT,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as e:
            # Якщо команда не знайдена або виконується з помилкою,
            # логуємо це та одразу повертаємо False.
            logger.error(f"Помилка перевірки інструмента SNMP: {e}")
            cls._log_installation_instructions()
            return False

        # Якщо цикл завершився без помилок, значить всі інструменти на місці.
        logger.debug("Усі необхідні SNMP-інструменти успішно знайдені.")
        return True

    @staticmethod
    def _log_installation_instructions():
        """Повертає інструкції для встановлення SNMP"""
        os_name = platform.system()

        instructions = {
            "Debian/Ubuntu": "sudo apt-get install snmp snmp-mibs-downloader",
            "Darwin": "brew install net-snmp",
            "Windows": "Завантажте з https://www.net-snmp.org/download.html",
        }

        instruction = instructions.get(
            os_name, "Встановіть net-snmp пакет для вашої ОС"
        )
        logger.warning(
            "SNMP утиліти не знайдено.\n" "Будь ласка, встановіть їх:\n" "%s",
            instruction,
        )


class SwitchSNMP:
    """Клас для роботи з комутатором через SNMP"""

    # Константи OID для статистики інтерфейсів
    OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"  # ifIndex
    OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"  # ifSpeed
    OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr
    OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"  # ifInOctets
    OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"  # ifOutOctets
    OID_IF_IN_PKTS = "1.3.6.1.2.1.2.2.1.11"  # ifInUcastPkts
    OID_IF_OUT_PKTS = "1.3.6.1.2.1.2.2.1.17"  # ifOutUcastPkts
    OID_IF_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus
    OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias
    OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"  # ifInErrors
    OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"  # ifOutErrors

    def __init__(self, host: str, community: str, version: str):
        self.host = host
        self.community = community
        self.version = version
        self.is_snmp_available = SNMPToolsChecker.is_installed()

    def get_interfaces_stats(self) -> Dict[int, Dict[str, Any]]:
        """
        Отримує статистику всіх інтерфейсів комутатора через SNMP

        Returns:
            Словник зі статистикою інтерфейсів, де ключ - індекс інтерфейсу,
            значення - словник з параметрами інтерфейсу
        """
        if not self.is_snmp_available:
            logger.error(
                "Спроба отримати статистику при відсутніх SNMP інструментах"
            )
            return {}

        try:
            # Отримуємо індекси інтерфейсів
            if_indexes = self._get_interface_indexes()
            if not if_indexes:
                logger.warning("Не знайдено жодного інтерфейсу")
                return {}

            # Список всіх OID для збору даних
            target_oids = [
                self.OID_IF_DESCR,
                self.OID_IF_ALIAS,
                self.OID_IF_SPEED,
                self.OID_IF_IN_OCTETS,
                self.OID_IF_OUT_OCTETS,
                self.OID_IF_IN_PKTS,
                self.OID_IF_OUT_PKTS,
                self.OID_IF_IN_ERRORS,
                self.OID_IF_OUT_ERRORS,
                self.OID_IF_STATUS,
            ]

            # Збираємо всі дані за один прохід
            oid_data = {}
            for oid in target_oids:
                oid_data[oid] = self._snmp_walk(oid)

            # Формуємо результат для кожного інтерфейсу
            interfaces = {}
            for index in if_indexes:
                interfaces[index] = {
                    "name": oid_data[self.OID_IF_DESCR].get(index, ""),
                    "alias": oid_data[self.OID_IF_ALIAS].get(index, ""),
                    "speed": self._safe_int(
                        oid_data[self.OID_IF_SPEED].get(index, "")
                    ),
                    "in_octets": self._safe_int(
                        oid_data[self.OID_IF_IN_OCTETS].get(index)
                    ),
                    "out_octets": self._safe_int(
                        oid_data[self.OID_IF_OUT_OCTETS].get(index)
                    ),
                    "in_pkts": self._safe_int(
                        oid_data[self.OID_IF_IN_PKTS].get(index)
                    ),
                    "out_pkts": self._safe_int(
                        oid_data[self.OID_IF_OUT_PKTS].get(index)
                    ),
                    "in_errors": self._safe_int(
                        oid_data[self.OID_IF_IN_ERRORS].get(index)
                    ),
                    "out_errors": self._safe_int(
                        oid_data[self.OID_IF_OUT_ERRORS].get(index)
                    ),
                    "status": oid_data[self.OID_IF_STATUS].get(
                        index, "unknown"
                    ),
                }

            logger.info(
                "Отримано статистику для %d інтерфейсів", len(interfaces)
            )
            return interfaces

        except Exception as e:
            logger.error(
                f"Критична помилка при отриманні статистики: {e}",
                exc_info=True,
            )
            return {}

    def _get_interface_indexes(self) -> List[int]:
        """Отримує список індексів активних інтерфейсів"""
        indexes = self._snmp_walk(self.OID_IF_INDEX)
        return [idx for idx in indexes.keys() if 1 <= idx <= 99]

    @staticmethod
    def _safe_int(value: Optional[str]) -> int:
        """Безпечне перетворення в ціле число"""
        try:
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0

    def _snmp_walk(self, base_oid: str) -> Dict[int, str]:
        """
        Виконує SNMP walk для вказаного базового OID і повертає результати

        Args:
            base_oid: Базовий OID для walk

        Returns:
            Словник {index: value} для всіх знайдених інстансів
        """
        try:
            command = [
                "snmpwalk",
                "-v",
                self.version,
                "-c",
                self.community,
                "-OQ",  # Тільки OID та значення
                "-On",  # Числовий формат
                self.host,
                base_oid,
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            return self._parse_snmp_walk_output(result.stdout)

        except subprocess.CalledProcessError as e:
            logger.error(
                f"SNMP помилка (код {e.returncode}): {e.stderr.strip()}"
            )
            return {}
        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут виконання SNMP walk для OID {base_oid}")
            return {}
        except Exception as e:
            logger.error(f"Невідома помилка при виконанні SNMP walk: {e}")
            return {}

    @staticmethod
    def _parse_snmp_walk_output(output: str) -> Dict[int, str]:
        """Парсить вивід SNMP walk у словник {index: value}"""
        results = {}
        pattern = r"\.(\d+)\s*=\s*(.*?)$"

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            # Шукаємо останню цифрову групу в OID
            match = re.search(pattern, line)
            if not match:
                continue

            index = int(match.group(1))
            value = match.group(2).strip()

            # Видаляємо лапки зі значення якщо вони є
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]

            results[index] = value

        return results


if __name__ == "__main__":

    ZYXEL_CONFIG = {
        "host": "172.24.72.90",
        "community": "public",
        "version": "2c",
    }
    # Ініціалізація комутатора
    switch = SwitchSNMP(**ZYXEL_CONFIG)

    if switch.is_snmp_available:
        # Виклик методів для роботи з комутатором
        stats = switch.get_interfaces_stats()
        for idx, data in stats.items():
            print(f"Інтерфейс {idx}:")
            print(f"  Ім'я: {data['name']}")
            print(f"  Alias: {data['alias']}")
            print(f"  Вхідні байти: {data['in_octets']}")
            print(f"  Вихідні байти: {data['out_octets']}")
            print(f"  Помилки: {data['in_errors']} / {data['out_errors']}")
            print(f"  Статус: {data['status']}")
            print("-" * 40)
    else:
        print("SNMP недоступний - виконайте інструкції з логів")
