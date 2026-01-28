import logging
import sys
import structlog
import os
import gzip
import shutil
import hashlib
import queue
import atexit
from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
from structlog.types import Processor


# --- ФУНКЦИИ ХЭШИРОВАНИЯ И РОТАЦИИ ---

def calculate_sha256(file_path: str) -> str:
    """Вычисляет SHA256 хэш файла для защиты целостности."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def archive_and_hash_rotator(source: str, dest: str):
    """
    Ротатор: сжимает лог в .gz, считает хэш и удаляет оригинал.
    """
    dest_gz = dest + ".gz"
    try:
        with open(source, 'rb') as f_in:
            with gzip.open(dest_gz, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        file_hash = calculate_sha256(dest_gz)

        with open(dest_gz + ".sha256", "w") as f_hash:
            f_hash.write(file_hash)

        if os.path.exists(source):
            os.remove(source)
    except Exception as e:
        sys.stderr.write(f"Error rotating logs: {e}\n")


# --- НАСТРОЙКА ЛОГГЕРА ---

def setup_logging(json_logs: bool = False, log_level: str = "INFO", log_file: str = "app.log"):
    """
    Настраивает асинхронное (буферизированное) логирование с ротацией и хэшированием.
    """

    # 1. Процессоры Structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 2. Создаем "реальные" хендлеры (Консоль + Файл)
    handlers = []

    # А. Консольный хендлер (Цветной или JSON)
    if json_logs:
        console_renderer = structlog.processors.JSONRenderer()
    else:
        console_renderer = structlog.dev.ConsoleRenderer(colors=True)

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            console_renderer,
        ],
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)

    # Б. Файловый хендлер (Ротация + Хэширование)
    if log_file:
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        file_handler.rotator = archive_and_hash_rotator
        file_handler.namer = lambda name: name

        # В файл пишем без цветов, но структурно
        if json_logs:
            file_renderer = structlog.processors.JSONRenderer()
        else:
            file_renderer = structlog.dev.ConsoleRenderer(colors=False)

        file_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                file_renderer,
            ],
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # 3. Настраиваем КЭШИРОВАНИЕ (QueueListener)
    # Создаем очередь для логов
    log_queue = queue.Queue(-1)

    # QueueHandler - это то, что мы добавим в логгер. Он просто кидает лог в очередь.
    queue_handler = QueueHandler(log_queue)

    # QueueListener - это отдельный поток, который забирает из очереди и пишет в реальные хендлеры
    listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()

    # Останавливаем слушатель при выходе из приложения
    atexit.register(listener.stop)

    # 4. Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.handlers = []  # Удаляем старые
    root_logger.setLevel(log_level.upper())

    # Добавляем только QueueHandler!
    # Приложение -> QueueHandler -> Queue -> [QueueListener Thread] -> Console/File
    root_logger.addHandler(queue_handler)

    # Перехват логов Uvicorn
    for _log in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logger = logging.getLogger(_log)
        logger.handlers = []
        logger.propagate = True