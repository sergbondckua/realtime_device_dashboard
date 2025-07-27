import asyncio
import logging
import re
import platform
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Tuple
from functools import wraps

import aiofiles

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class InterfaceType(Enum):
    """Типи інтерфейсів за RFC 1213"""

    ETHERNET = "6"  # ethernetCsmacd
    FAST_ETHERNET = "62"  # fastEther
    GIGABIT_ETHERNET = "117"  # gigabitEthernet
    OTHER = "1"  # other
    PPPOE = "23"  # pppoe
    WIRELESS = "71"  # wireless
    SOFTWARE_LOOPBACK = "24"  # softwareLoopback


class OSInstructions(Enum):
    """Інструкції для встановлення SNMP на різних ОС"""

    DEBIAN_UBUNTU = "sudo apt-get install snmp snmp-mibs-downloader"
    DARWIN = "brew install net-snmp"
    WINDOWS = "Завантажте з https://www.net-snmp.org/download.html"
    REDHAT_CENTOS = "sudo yum install net-snmp-utils"
    ARCH = "sudo pacman -S net-snmp"
    DEFAULT = "Встановіть net-snmp пакет для вашої ОС"


@dataclass
class SNMPConfig:
    """Конфігурація для SNMP з'єднання"""

    # Таймаути
    COMMAND_TIMEOUT: int = 3
    SNMP_TIMEOUT: int = 3

    # Обмеження
    MAX_PHYSICAL_INTERFACES: int = 48
    MAX_RETRIES: int = 3
    MAX_CONCURRENT_REQUESTS: int = 10  # Максимум одночасних запитів

    # Підтримувані версії SNMP
    SUPPORTED_VERSIONS: tuple = ("1", "2c")

    # Типи інтерфейсів для фільтрації (фізичні інтерфейси)
    PHYSICAL_INTERFACE_TYPES: tuple = (
        InterfaceType.ETHERNET.value,
        InterfaceType.FAST_ETHERNET.value,
        InterfaceType.GIGABIT_ETHERNET.value,
        InterfaceType.PPPOE.value,
        InterfaceType.WIRELESS.value,
    )


@dataclass
class InterfaceStats:
    """Структура даних для статистики інтерфейсу"""

    index: int
    name: str
    alias: str
    speed: int
    in_octets: int
    out_octets: int
    in_pkts: int
    out_pkts: int
    in_errors: int
    out_errors: int
    admin_status: int
    oper_status: int

    @property
    def total_octets(self) -> int:
        """Загальна кількість переданих байтів"""
        return self.in_octets + self.out_octets

    @property
    def total_errors(self) -> int:
        """Загальна кількість помилок"""
        return self.in_errors + self.out_errors


def async_retry(max_retries: int = 3, delay: float = 1.0):
    """Декоратор для асинхронного retry з exponential backoff"""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2**attempt)  # Exponential backoff
                        logger.warning(
                            "Спроба %d/%d не вдалась: %s. Чекаємо %.1fs перед наступною спробою",
                            attempt + 1,
                            max_retries,
                            e,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            "Усі %d спроб вичерпано: %s", max_retries, e
                        )
            raise last_exception

        return wrapper

    return decorator


class SNMPToolsChecker:
    """Клас для перевірки наявності SNMP-інструментів в системі"""

    @classmethod
    async def is_installed(cls) -> bool:
        """
        Асинхронно перевіряє, чи встановлені ВСІ необхідні SNMP-інструменти в системі.
        Повертає True, лише якщо всі інструменти доступні.
        """
        config = SNMPConfig()

        try:
            # Асинхронно виконуємо перевірку
            proc = await asyncio.create_subprocess_exec(
                "snmpwalk",
                "-V",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.DEVNULL,
            )

            try:
                await asyncio.wait_for(
                    proc.wait(), timeout=config.COMMAND_TIMEOUT
                )
                if proc.returncode == 0:
                    logger.debug(
                        "Усі необхідні SNMP-інструменти успішно знайдені."
                    )
                    return True
            except asyncio.TimeoutError:
                proc.kill()
                raise

        except Exception as e:
            logger.error("Помилка перевірки інструмента SNMP: %s", e)
            await cls._log_installation_instructions()
            return False

        await cls._log_installation_instructions()
        return False

    @classmethod
    async def _log_installation_instructions(cls):
        """Асинхронно виводить інструкції для встановлення SNMP залежно від ОС"""
        os_name = platform.system()

        # Маппінг ОС на інструкції
        os_instructions = {
            "Linux": await cls._get_linux_instruction(),
            "Darwin": OSInstructions.DARWIN.value,
            "Windows": OSInstructions.WINDOWS.value,
        }

        instruction = os_instructions.get(
            os_name, OSInstructions.DEFAULT.value
        )
        logger.warning(
            "SNMP утиліти не знайдено.\n" "Будь ласка, встановіть їх:\n" "%s",
            instruction,
        )

    @staticmethod
    async def _get_linux_instruction() -> str:
        try:
            async with aiofiles.open("/etc/os-release", "r") as f:
                content = (await f.read()).lower()

                if "ubuntu" in content or "debian" in content:
                    return OSInstructions.DEBIAN_UBUNTU.value
                elif any(x in content for x in ["centos", "rhel", "fedora"]):
                    return OSInstructions.REDHAT_CENTOS.value
                elif "arch" in content:
                    return OSInstructions.ARCH.value
        except FileNotFoundError:
            pass

        return OSInstructions.DEFAULT.value


class AsyncSwitchSNMP:
    """Асинхронний клас для роботи з комутатором через SNMP"""

    # Системні OID
    OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"  # sysDescr (Модель, прошивка)
    OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"  # sysName (Системне ім'я)
    OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"  # sysUpTime (Uptime)
    OID_SYS_MAC = "1.3.6.1.2.1.2.2.1.6"  # ifPhysAddress (базова MAC-адреса)

    # Константи OID для статистики інтерфейсів
    OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"  # ifIndex
    OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"  # ifType
    OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"  # ifSpeed
    OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr
    OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"  # ifInOctets
    OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"  # ifOutOctets
    OID_IF_IN_PKTS = "1.3.6.1.2.1.2.2.1.11"  # ifInUcastPkts
    OID_IF_OUT_PKTS = "1.3.6.1.2.1.2.2.1.17"  # ifOutUcastPkts
    OID_IF_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus
    OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"  # ifAdminStatus
    OID_IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias
    OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"  # ifInErrors
    OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"  # ifOutErrors

    def __init__(
        self, host: str, community: str = "public", version: str = "2c"
    ):
        self.host = host
        self.community = community
        self.version = version
        self.config = SNMPConfig()
        self._semaphore = asyncio.Semaphore(
            self.config.MAX_CONCURRENT_REQUESTS
        )
        self._is_snmp_available = None  # Кешування результату

    async def _check_snmp_availability(self) -> bool:
        """Кешовано перевіряє доступність SNMP інструментів"""
        if self._is_snmp_available is None:
            self._is_snmp_available = await SNMPToolsChecker.is_installed()
        return self._is_snmp_available

    @async_retry(max_retries=SNMPConfig.MAX_RETRIES, delay=1.0)
    async def get_system_info(self) -> Dict[str, Optional[str]]:
        """
        Асинхронно отримує основну системну інформацію про пристрій.
        """
        if not await self._check_snmp_availability():
            logger.error(
                "Спроба отримати інформацію про систему при відсутніх SNMP інструментах"
            )
            return {}

        try:
            # Паралельно отримуємо системну інформацію
            system_tasks = [
                self._snmp_get(self.OID_SYS_DESCR),
                self._snmp_get(self.OID_SYS_NAME),
                self._snmp_get(self.OID_SYS_UPTIME),
            ]

            model, system_name, uptime = await asyncio.gather(*system_tasks)

            # Отримуємо базову MAC-адресу
            mac_address = await self._get_base_mac_address()

            info = {
                "model": model,
                "system_name": system_name,
                "uptime": uptime,
                "mac_address": mac_address,
            }

            logger.info("Системна інформація успішно отримана.")
            return info

        except Exception as e:
            logger.error(
                "Критична помилка при отриманні системної інформації: %s",
                e,
                exc_info=True,
            )
            return {}

    async def _get_base_mac_address(self) -> str:
        """Асинхронно отримує базову MAC-адресу пристрою"""
        if_types = await self._snmp_walk(self.OID_IF_TYPE)

        for index, if_type in if_types.items():
            # Перевіряємо, чи це фізичний інтерфейс
            if if_type in self.config.PHYSICAL_INTERFACE_TYPES:
                mac_oid = f"{self.OID_SYS_MAC}.{index}"
                mac_addr = await self._snmp_get(mac_oid)
                if mac_addr and mac_addr.strip():
                    return self._format_mac_address(mac_addr.strip())

        return "00:00:00:00:00:00"

    @staticmethod
    def _format_mac_address(mac_string: str) -> str:
        """Форматує MAC-адресу у стандартний вигляд"""
        # Видаляємо всі пробіли та розділяємо по байтах
        clean_mac = mac_string.replace(" ", "")
        if len(clean_mac) == 12:  # Hex без розділювачів
            return ":".join(clean_mac[i : i + 2] for i in range(0, 12, 2))
        else:
            # Припускаємо, що це вже форматована MAC-адреса
            return mac_string.replace(" ", ":")

    @async_retry(max_retries=SNMPConfig.MAX_RETRIES, delay=1.0)
    async def get_interfaces_stats(self) -> Dict[int, InterfaceStats]:
        """
        Асинхронно отримує статистику всіх інтерфейсів комутатора через SNMP

        Returns:
            Словник зі статистикою інтерфейсів, де ключ - індекс інтерфейсу,
            значення - об'єкт InterfaceStats
        """
        if not await self._check_snmp_availability():
            logger.error(
                "Спроба отримати статистику при відсутніх SNMP інструментах"
            )
            return {}

        try:
            # Отримуємо індекси інтерфейсів
            if_indexes = await self._get_interface_indexes()
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
                self.OID_IF_ADMIN_STATUS,
            ]

            # Паралельно збираємо всі дані
            logger.debug(
                "Початок паралельного збору даних для %d OID", len(target_oids)
            )
            start_time = asyncio.get_event_loop().time()

            oid_tasks = [self._snmp_walk(oid) for oid in target_oids]
            oid_results = await asyncio.gather(*oid_tasks)

            end_time = asyncio.get_event_loop().time()
            logger.debug(
                "Паралельний збір даних завершено за %s.2f секунди",
                end_time - start_time,
            )

            # Створюємо словник результатів
            oid_data = dict(zip(target_oids, oid_results))

            # Формуємо результат для кожного інтерфейсу
            interfaces = {}
            for index in if_indexes:
                interfaces[index] = InterfaceStats(
                    index=index,
                    name=oid_data[self.OID_IF_DESCR].get(index, ""),
                    alias=oid_data[self.OID_IF_ALIAS].get(index, ""),
                    speed=self._safe_int(
                        oid_data[self.OID_IF_SPEED].get(index, "")
                    ),
                    in_octets=self._safe_int(
                        oid_data[self.OID_IF_IN_OCTETS].get(index)
                    ),
                    out_octets=self._safe_int(
                        oid_data[self.OID_IF_OUT_OCTETS].get(index)
                    ),
                    in_pkts=self._safe_int(
                        oid_data[self.OID_IF_IN_PKTS].get(index)
                    ),
                    out_pkts=self._safe_int(
                        oid_data[self.OID_IF_OUT_PKTS].get(index)
                    ),
                    in_errors=self._safe_int(
                        oid_data[self.OID_IF_IN_ERRORS].get(index)
                    ),
                    out_errors=self._safe_int(
                        oid_data[self.OID_IF_OUT_ERRORS].get(index)
                    ),
                    admin_status=self._safe_int(
                        oid_data[self.OID_IF_ADMIN_STATUS].get(index)
                    ),
                    oper_status=self._safe_int(
                        oid_data[self.OID_IF_STATUS].get(index)
                    ),
                )

            logger.info(
                "Отримано статистику для %d інтерфейсів", len(interfaces)
            )
            return interfaces

        except Exception as e:
            logger.error(
                "Критична помилка при отриманні статистики: %s",
                e,
                exc_info=True,
            )
            return {}

    async def _get_interface_indexes(self) -> List[int]:
        """Асинхронно отримує список індексів фізичних інтерфейсів"""
        indexes = await self._snmp_walk(self.OID_IF_TYPE)
        return [
            index
            for index, value in indexes.items()
            if (
                value in self.config.PHYSICAL_INTERFACE_TYPES
                and index <= self.config.MAX_PHYSICAL_INTERFACES
            )
        ]

    @staticmethod
    def _safe_int(value: Optional[str]) -> int:
        """Безпечне перетворення в ціле число"""
        try:
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0

    async def _snmp_walk(self, base_oid: str) -> Dict[int, str]:
        """
        Асинхронно виконує SNMP walk для вказаного базового OID і повертає результати

        Args:
            base_oid: Базовий OID для walk

        Returns:
            Словник {index: value} для всіх знайдених інстансів
        """
        async with self._semaphore:  # Обмежуємо кількість одночасних запитів
            try:
                # Створюємо процес асинхронно
                proc = await asyncio.create_subprocess_exec(
                    "snmpwalk",
                    "-v",
                    self.version,
                    "-c",
                    self.community,
                    "-OQ",  # Тільки OID та значення
                    "-On",  # Числовий формат
                    self.host,
                    base_oid,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Чекаємо завершення з таймаутом
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.config.SNMP_TIMEOUT
                )

                if proc.returncode == 0:
                    return self._parse_snmp_walk_output(stdout.decode())
                else:
                    logger.error(
                        "SNMP walk помилка для %s: %s}",
                        base_oid,
                        stderr.decode().strip(),
                    )
                    return {}

            except asyncio.TimeoutError:
                logger.error(
                    "Таймаут виконання SNMP walk для OID %s", base_oid
                )
                try:
                    proc.kill()
                except:
                    pass
                return {}
            except Exception as e:
                logger.error("Невідома помилка при виконанні SNMP walk: %s", e)
                return {}

    async def _snmp_get(self, oid: str) -> Optional[str]:
        """
        Асинхронно виконує SNMP get для вказаного OID і повертає значення.

        Args:
            oid: OID для запиту.

        Returns:
            Значення або None, якщо сталася помилка.
        """
        async with self._semaphore:  # Обмежуємо кількість одночасних запитів
            try:
                # Створюємо процес асинхронно
                proc = await asyncio.create_subprocess_exec(
                    "snmpget",
                    "-v",
                    self.version,
                    "-c",
                    self.community,
                    "-Oqv",  # Вивід лише значення
                    self.host,
                    oid,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                # Чекаємо завершення з таймаутом
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.config.SNMP_TIMEOUT
                )

                if proc.returncode == 0:
                    value_raw = stdout.decode().strip()
                    # Видаляємо лапки зі значення якщо вони є
                    if value_raw.startswith('"') and value_raw.endswith('"'):
                        value_raw = value_raw[1:-1]
                    return value_raw
                else:
                    logger.warning(
                        "Не вдалося отримати OID %s: %s",
                        oid,
                        stderr.decode().strip(),
                    )
                    return None

            except asyncio.TimeoutError:
                logger.warning("Таймаут виконання SNMP get для OID %s", oid)
                try:
                    proc.kill()
                except:
                    pass
                return None
            except Exception as e:
                logger.warning(
                    "Невідома помилка при SNMP get для OID %s: %s",
                    oid,
                    e,
                )
                return None

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
            value_raw = match.group(2).strip()

            # Видаляємо лапки зі значення якщо вони є
            if value_raw.startswith('"') and value_raw.endswith('"'):
                value_raw = value_raw[1:-1]

            results[index] = value_raw

        return results

    @staticmethod
    async def get_multiple_switches_stats(switches_config: List[Tuple[str, str, str]]
    ) -> Dict[str, Dict[int, InterfaceStats]]:
        """
        Асинхронно отримує статистику з кількох комутаторів паралельно

        Args:
            switches_config: Список кортежів (host, community, version)

        Returns:
            Словник {host: {interface_index: InterfaceStats}}
        """
        tasks = []
        hosts = []
        system_info = []

        for host, community, version in switches_config:
            switch = AsyncSwitchSNMP(host, community, version)
            tasks.append(switch.get_interfaces_stats())
            system_info.append(switch.get_system_info())
            hosts.append(host)

        logger.info(
            "Початок паралельного збору даних з %d комутаторів",
            len(switches_config),
        )
        start_time = asyncio.get_event_loop().time()
        results_stats = await asyncio.gather(*tasks, return_exceptions=True)
        results_system_info = await asyncio.gather(
            *system_info, return_exceptions=True
        )
        end_time = asyncio.get_event_loop().time()
        logger.info(
            "Паралельний збір з %d комутаторів завершено за %.2f секунд",
            len(switches_config),
            end_time - start_time,
        )

        # Формуємо результат
        switches_stats = {}
        for i, host in enumerate(hosts):
            sys_info = results_system_info[i]
            stats = results_stats[i]

            if isinstance(sys_info, Exception) or isinstance(stats, Exception):
                logger.error(
                    "Помилка отримання даних з %s: %s",
                    host,
                    sys_info if isinstance(sys_info, Exception) else stats,
                )
                switches_stats[host] = {}
            else:
                switches_stats[host] = {
                    "system_info": sys_info,
                    "interfaces": stats,
                }

        return switches_stats


async def main():
    """Основна асинхронна функція"""
    try:
        # Ініціалізація комутатора
        switch = AsyncSwitchSNMP("192.168.5.20", "public", "2c")

        # Паралельно отримуємо системну інформацію та статистику інтерфейсів
        logger.info("Початок паралельного збору даних...")
        start_time = asyncio.get_event_loop().time()

        system_info_task = switch.get_system_info()
        interfaces_stats_task = switch.get_interfaces_stats()

        system_info, stats = await asyncio.gather(
            system_info_task, interfaces_stats_task
        )

        end_time = asyncio.get_event_loop().time()
        logger.info(f"Загальний час виконання: {end_time - start_time:.2f}с")

        # Виводимо результати
        print("--- Системна інформація ---")
        print(system_info)
        for key, value in system_info.items():
            print(f"{key}: {value}")
        print("-" * 40)

        for idx, interface in stats.items():
            print(f"Інтерфейс {idx}:")
            print(f"  Ім'я: {interface.name}")
            print(f"  Alias: {interface.alias}")
            print(
                f"  Статус: {'UP' if interface.oper_status == 1 else 'DOWN'}"
            )
            print(f"  Admin статус: {interface.admin_status}")
            print(f"  Oper статус: {interface.oper_status}")
            print(f"  Вхідні байти: {interface.in_octets}")
            print(f"  Вихідні байти: {interface.out_octets}")
            print(f"  Загалом байтів: {interface.total_octets}")
            print(f"  Помилки: {interface.in_errors} / {interface.out_errors}")
            print(f"  Загалом помилок: {interface.total_errors}")
            print("-" * 40)

        # Приклад роботи з кількома комутаторами
        print("\n--- Тест з кількома комутаторами ---")
        switches_config = [
            ("172.24.145.145", "public", "2c"),
            ("192.168.5.1", "public", "2c"),  # Додайте більше комутаторів
            ("192.168.5.11", "public", "2c"),  # Додайте більше комутаторів
        ]

        multi_results = await switch.get_multiple_switches_stats(
            switches_config
        )
        for host, interfaces in multi_results.items():
            print(f"Комутатор {host}: {len(interfaces)} інтерфейсів")

    except Exception as e:
        logger.error(f"Невідома помилка: {e}", exc_info=True)
        print(f"Помилка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
