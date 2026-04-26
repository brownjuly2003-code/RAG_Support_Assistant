# seed_docs.py (root-level demo script)
"""
NOTE: Located in project root, not under demo/. The demo/ package only
contains test_questions.json and __init__.py. Run as `python seed_docs.py`.

Заполняет папку demo/docs демо-документами и создаёт файл с тестовыми вопросами.

Документы:
- warranty.md        — гарантийные условия;
- returns_policy.md  — политика возвратов;
- errors_e10_e30.md  — описание ошибок E10–E30.

Вопросы:
- demo/test_questions.json — список вопросов с ожидаемыми ключевыми словами
  для оценки качества retrieval (Recall@k).

Запуск:
    python demo/seed_docs.py
или:
    python -m demo.seed_docs
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


DOCS_CONTENT = {
    "warranty.md": """# Гарантийные условия

Гарантия на продукцию составляет 12 месяцев с момента покупки.

Гарантия действует при соблюдении следующих условий:
- товар используется по инструкции;
- сохранён кассовый или товарный чек;
- не вскрывался корпус устройства.

Гарантия не распространяется на:
- механические повреждения;
- следы попадания жидкости;
- последствия самостоятельного ремонта.

Для обращения по гарантии:
1. Подготовьте товар и чек.
2. Обратитесь в сервисный центр или службу поддержки.
3. Заполните форму обращения и опишите неисправность.
""",
    "returns_policy.md": """# Политика возвратов

Покупатель имеет право вернуть товар надлежащего качества
в течение 14 дней с момента покупки.

Условия возврата:
- сохранён товарный вид и упаковка;
- есть документы, подтверждающие покупку;
- товар не имеет следов эксплуатации.

Возврат денежных средств:
- производится на ту же карту или счёт, с которых была оплата;
- срок возврата денег — до 10 рабочих дней после приёмки товара.

Возвраты без чека, как правило, не принимаются.
""",
    "errors_e10_e30.md": """# Коды ошибок E10–E30

E10 — Недостаточный уровень воды.
Проверьте давление и подключение к водопроводу.

E20 — Проблема со сливом воды.
Возможные причины:
- засорён сливной фильтр;
- перегиб сливного шланга;
- неисправность сливного насоса.

E25 — Ошибка памяти.
Рекомендуется перезагрузить устройство и, при необходимости,
выполнить сброс к заводским настройкам.

E30 — Критическая системная ошибка.
Отключите устройство от сети и обратитесь в сервисный центр.
""",
}

TEST_QUESTIONS = [
    {
        "question": "Как долго действует гарантия на продукт?",
        "category": "warranty",
        "expected_keywords": ["12 месяцев", "год", "гарантия"],
    },
    {
        "question": "Что нужно, чтобы обратиться по гарантии?",
        "category": "warranty",
        "expected_keywords": ["чек", "служба поддержки", "форма обращения"],
    },
    {
        "question": "В течение какого времени можно вернуть товар?",
        "category": "returns",
        "expected_keywords": ["14 дней", "право вернуть", "с момента покупки"],
    },
    {
        "question": "Можно ли вернуть товар без чека?",
        "category": "returns",
        "expected_keywords": ["без чека", "как правило не принимаются"],
    },
    {
        "question": "Что означает ошибка E20?",
        "category": "errors",
        "expected_keywords": ["слив", "фильтр", "сливной шланг", "насос"],
    },
    {
        "question": "Как устранить ошибку E25?",
        "category": "errors",
        "expected_keywords": ["память", "перезагрузить", "сброс к заводским"],
    },
]


def docs_dir() -> Path:
    """Путь к директории demo/docs относительно корня проекта."""
    return Path(__file__).resolve().parent / "docs"


def seed_demo_docs(overwrite: bool = False) -> None:
    """
    Создаёт демо-документы.

    :param overwrite: если False — существующие файлы не трогаем,
                      можно править их вручную.
    """
    path = docs_dir()
    path.mkdir(parents=True, exist_ok=True)

    for filename, content in DOCS_CONTENT.items():
        file_path = path / filename
        if file_path.exists() and not overwrite:
            continue
        file_path.write_text(content, encoding="utf-8")


def seed_test_questions(path: str | Path = "demo/test_questions.json") -> None:
    """Сохраняет тестовые вопросы в JSON (для chunking-оценки)."""
    qpath = Path(path)
    qpath.parent.mkdir(parents=True, exist_ok=True)
    qpath.write_text(
        json.dumps(TEST_QUESTIONS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    seed_demo_docs(overwrite=False)
    seed_test_questions()
    print("Демо-документы и тестовые вопросы созданы.")
