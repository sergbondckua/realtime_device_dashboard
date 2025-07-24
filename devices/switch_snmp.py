import re
import subprocess
import platform
import logging
from typing import List, Tuple, Optional, Dict, Any

# Налаштування логування
logger = logging.getLogger(__name__)


class SNMPToolsChecker:
    """Клас для перевірки наявності SNMP-інструментів в системі"""

    # Константи для конфігурації
    TIMEOUT = 5
    CHECK_COMMANDS = [
        (
            ["snmpget", "--version"],
            "SNMP-інструменти встановлені (перевірка snmpget)",
        ),
        (
            ["snmpwalk", "-V"],
            "SNMP-інструменти встановлені (перевірка snmpwalk)",
        ),
    ]

    @classmethod
    def is_installed(cls) -> bool:
        """Перевіряє, чи встановлені SNMP-інструменти в системі"""
        for command, success_message in cls.CHECK_COMMANDS:
            try:
                subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=cls.TIMEOUT,
                )
                logger.info(success_message)
                return True
            except (
                subprocess.CalledProcessError,
                FileNotFoundError,
                subprocess.TimeoutExpired,
            ):
                continue

        cls._log_installation_instructions()
        return False

    @staticmethod
    def _log_installation_instructions():
        """Повертає інструкції для встановлення SNMP"""
        os_name = platform.system()

        instructions = {
            "Linux": "sudo apt-get install snmp snmp-mibs-downloader",
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
    OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr
    OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"  # ifInOctets
    OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"  # ifOutOctets
    OID_IF_IN_PKTS = "1.3.6.1.2.1.2.2.1.11"  # ifInUcastPkts
    OID_IF_OUT_PKTS = "1.3.6.1.2.1.2.2.1.17"  # ifOutUcastPkts
    OID_IF_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus
    OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias

    # Статуси інтерфейсів
    INTERFACE_STATUSES = {
        1: "up",
        2: "down",
        3: "testing",
        4: "unknown",
        5: "dormant",
        6: "notPresent",
        7: "lowerLayerDown",
    }

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

            # Збираємо дані для кожного інтерфейсу
            interfaces = {}
            for index in if_indexes:
                interfaces[index] = {
                    "name": self._snmp_get(self.OID_IF_DESCR + f".{index}"),
                    "alias": self._snmp_get(self.OID_IF_ALIAS + f".{index}"),
                    "in_octets": int(
                        self._snmp_get(self.OID_IF_IN_OCTETS + f".{index}")
                        or 0
                    ),
                    "out_octets": int(
                        self._snmp_get(self.OID_IF_OUT_OCTETS + f".{index}")
                        or 0
                    ),
                    "in_pkts": int(
                        self._snmp_get(self.OID_IF_IN_PKTS + f".{index}") or 0
                    ),
                    "out_pkts": int(
                        self._snmp_get(self.OID_IF_OUT_PKTS + f".{index}") or 0
                    ),
                    "status": self._get_interface_status(index),
                }

            logger.info(
                "Отримано статистику для %d інтерфейсів", len(interfaces)
            )
            return interfaces

        except Exception as e:
            logger.error(
                f"Помилка при отриманні статистики: {e}", exc_info=True
            )
            return {}

    def _get_interface_indexes(self) -> List[int]:
        """Отримує список індексів активних інтерфейсів"""
        # Використовуємо OID ifIndex (1.3.6.1.2.1.2.2.1.1) або ifDescr для отримання індексів
        output = self._snmp_walk(self.OID_IF_INDEX)
        return [index for index in output if 1 <= index <= 99]

    def _get_interface_status(self, index: int) -> str:
        """Отримує статус інтерфейсу у читабельному форматі"""
        status_code = self._snmp_get(self.OID_IF_STATUS + f".{index}")
        try:
            return self.INTERFACE_STATUSES.get(int(status_code), "unknown")
        except (ValueError, TypeError):
            return "unknown"

    def _snmp_get(self, oid: str) -> str:
        """
        Виконує SNMP get для вказаного OID і повертає значення

        Args:
            oid: OID для запиту

        Returns:
            Рядок зі значенням або пустий рядок у разі помилки
        """
        try:
            command = [
                "snmpget",
                "-v",
                self.version,
                "-c",
                self.community,
                "-Oqv",  # Тільки значення, без OID та типу
                self.host,
                oid,
            ]

            result = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=5
            )

            # Обрізаємо зайві пробіли та видаляємо лапки
            value = result.stdout.strip()
            print(value)
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            return value

        except subprocess.CalledProcessError as e:
            logger.error(
                f"SNMP помилка (код {e.returncode}): {e.stderr.strip()}"
            )
            return ""
        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут виконання SNMP запиту для OID {oid}")
            return ""
        except Exception as e:
            logger.error(f"Невідома помилка при виконанні SNMP: {e}")
            return ""

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
                command, capture_output=True, text=True, check=True, timeout=10
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

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            # Розділяємо ліву частину (OID+індекс) і значення
            if "=" not in line:
                continue

            oid_part, value_part = line.split("=", 1)
            oid_part = oid_part.strip()
            value_part = value_part.strip()

            # Видаляємо лапки зі значення якщо вони є
            if value_part.startswith('"') and value_part.endswith('"'):
                value_part = value_part[1:-1]

            # Спроба знайти числовий індекс
            index = None
            if "." in oid_part:
                # Розділяємо OID на частини, щоб знайти числовий OID (наприклад, ".1.3.6.1.2.1.2.2.1.1.1")
                parts = oid_part.split(".")
                try:
                    # Останній елемент має бути індексом
                    index = int(parts[-1])
                except ValueError:
                    pass

            if index is not None:
                results[index] = value_part
            else:
                logger.info(
                    "Не вдалося визначити індекс для рядка: %s", line
                )
        return results

    # Наприклад: get_system_info(), get_interfaces_stats(), тощо


if __name__ == "__main__":

    ZYXEL_CONFIG = {
        "host": "172.24.129.144",
        "community": "public",
        "version": "2c",
    }
    # Ініціалізація комутатора
    switch = SwitchSNMP(**ZYXEL_CONFIG)

    if switch.is_snmp_available:
        print("SNMP доступний")
        # Виклик методів для роботи з комутатором
        print(switch.get_interfaces_stats())
    else:
        print("SNMP недоступний - виконайте інструкції з логів")
