#!/usr/bin/env python3
# scripts/content_pipeline.py
# --- agent_meta ---
# role: content-pipeline-cli
# contract: CLI для запуска пайплайна загрузки контента
# owner: backend-core
# --- /agent_meta ---

"""
CLI скрипт для загрузки контента психолога.

Использование:
    python scripts/content_pipeline.py --file data/content.json
    python scripts/content_pipeline.py --file data/content.json --dry-run
    python scripts/content_pipeline.py --file data/content.json --verbose

Формат JSON:
    {
        "source": {
            "source_type": "yandex_disk",
            "title": "Яндекс Диск психолога",
            "url": "https://disk.yandex.ru/d/abc123"
        },
        "content": [
            {
                "slug": "stress_management_01",
                "title": "Управление стрессом",
                "topic": "mind",
                "content_type": "lesson",
                "full_text": "Полный текст урока..."
            }
        ]
    }

Секция source опциональна. Если не указана, используется manual по умолчанию.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.content_pipeline import ContentInput, ContentInputBatch
from app.services.content_pipeline import ContentPipeline


# Настройка логирования
def setup_logging(verbose: bool = False) -> None:
    """Настраивает логирование."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_content_file(file_path: Path) -> ContentInputBatch:
    """Загружает и валидирует JSON файл с контентом.

    Args:
        file_path: Путь к JSON файлу.

    Returns:
        ContentInputBatch с данными источника и списком материалов.

    Raises:
        FileNotFoundError: Если файл не найден.
        ValueError: Если формат файла некорректен.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    with file_path.open(encoding="utf-8") as fp:
        data = json.load(fp)

    # Валидация через Pydantic
    return ContentInputBatch.model_validate(data)


def validate_only(inputs: list[ContentInput], pipeline: ContentPipeline) -> None:
    """Выполняет только валидацию без записи.

    Args:
        inputs: Список входных данных.
        pipeline: Экземпляр пайплайна.
    """
    logger = logging.getLogger("vmeste.scripts.content_pipeline")
    logger.info("=" * 60)
    logger.info("РЕЖИМ ВАЛИДАЦИИ (dry-run)")
    logger.info("=" * 60)

    duplicates = 0
    new_items = 0

    for item in inputs:
        if pipeline.check_duplicate(item.slug):
            logger.warning("  [ДУБЛИКАТ] %s — %s", item.slug, item.title)
            duplicates += 1
        else:
            logger.info("  [НОВЫЙ] %s — %s", item.slug, item.title)
            new_items += 1

    logger.info("-" * 60)
    logger.info("Итого: %d новых, %d дубликатов", new_items, duplicates)
    logger.info("Для загрузки уберите флаг --dry-run")


def run_pipeline(inputs: list[ContentInput], pipeline: ContentPipeline) -> int:
    """Запускает пайплайн загрузки.

    Args:
        inputs: Список входных данных.
        pipeline: Экземпляр пайплайна.

    Returns:
        Код возврата (0 = успех, 1 = есть ошибки).
    """
    logger = logging.getLogger("vmeste.scripts.content_pipeline")
    logger.info("=" * 60)
    logger.info("ЗАПУСК ПАЙПЛАЙНА")
    logger.info("=" * 60)

    result = pipeline.process_batch(inputs)

    # Вывод результатов
    logger.info("-" * 60)
    for item in result.results:
        if item.success:
            logger.info(
                "  [OK] %s — %d чанков, %d эмбеддингов",
                item.slug,
                item.chunks_count,
                item.embeddings_count,
            )
        elif item.error == "duplicate":
            logger.warning("  [ПРОПУЩЕН] %s — дубликат", item.slug)
        else:
            logger.error("  [ОШИБКА] %s — %s", item.slug, item.error)

    logger.info("=" * 60)
    logger.info("ИТОГО:")
    logger.info("  Всего материалов: %d", result.total)
    logger.info("  Добавлено: %d", result.inserted)
    logger.info("  Пропущено (дубликаты): %d", result.skipped)
    logger.info("  Ошибок: %d", result.failed)
    logger.info("=" * 60)

    return 0 if result.failed == 0 else 1


def parse_args() -> argparse.Namespace:
    """Парсит аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Загрузка контента психолога в PostgreSQL и ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
    python scripts/content_pipeline.py --file data/content.json
    python scripts/content_pipeline.py --file data/content.json --dry-run
    python scripts/content_pipeline.py --file data/content.json --verbose
        """,
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Путь к JSON файлу с контентом",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только валидация без записи в БД",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод (DEBUG уровень)",
    )
    return parser.parse_args()


def main() -> int:
    """Точка входа скрипта."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger("vmeste.scripts.content_pipeline")

    try:
        # Загрузка файла
        logger.info("Загрузка файла: %s", args.file)
        batch = load_content_file(args.file)
        logger.info("Загружено %d материалов", len(batch.content))

        # Логируем информацию об источнике
        if batch.source:
            logger.info(
                "Источник: %s (%s)",
                batch.source.title,
                batch.source.source_type,
            )
        else:
            logger.info("Источник: manual (по умолчанию)")

        # Инициализация пайплайна с данными источника
        pipeline = ContentPipeline(source_input=batch.source)

        if args.dry_run:
            validate_only(batch.content, pipeline)
            return 0
        else:
            return run_pipeline(batch.content, pipeline)

    except FileNotFoundError as e:
        logger.error("Файл не найден: %s", e)
        return 1
    except json.JSONDecodeError as e:
        logger.error("Ошибка парсинга JSON: %s", e)
        return 1
    except Exception as e:
        logger.exception("Неожиданная ошибка: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
