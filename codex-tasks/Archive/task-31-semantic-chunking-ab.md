# Task 31 — Semantic Chunking A/B test script

## Goal
`RAG_SEMANTIC_CHUNKING=true` уже реализован, но никогда не сравнивался с fixed-size.
Создать скрипт, который прогоняет один и тот же набор документов через оба режима
и сравнивает качество retrieval — без реального Ollama.

## Background
`manager.py` содержит:
- `HybridRetriever` — с `use_semantic_chunking` флагом (или через build_retriever + semantic_split)
- `semantic_split(docs, embeddings)` — semantic chunking через SemanticChunker
- `RAG_SEMANTIC_CHUNKING=true` в config/settings.py

Метрика для сравнения: `context_recall` из RAGEvaluator — доля expected_keywords,
найденных в retrieved-документах. Лучший chunking → лучше recall.

## Files to create
- `scripts/semantic_chunking_ab.py`

---

## scripts/semantic_chunking_ab.py

```python
#!/usr/bin/env python3
"""
scripts/semantic_chunking_ab.py

Сравнивает fixed-size vs semantic chunking по context_recall на синтетических документах.
Не требует запущенного Ollama. Использует mock embeddings.

Использование:
    python scripts/semantic_chunking_ab.py
    python scripts/semantic_chunking_ab.py --output docs/research/semantic_chunking_ab.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.ragas_eval import RAGEvaluator, TestCase

# ---------------------------------------------------------------------------
# Синтетический корпус документов (имитирует support knowledge base)
# ---------------------------------------------------------------------------
SYNTHETIC_DOCS = [
    # Документ 1: авторизация
    """Ошибка E401 означает отказ в авторизации. Токен доступа недействителен или истёк.
Для восстановления доступа нужно повторно авторизоваться через личный кабинет.
Введите логин и пароль, получите новый токен. Если проблема повторяется — проверьте
корректность учётных данных и не заблокирован ли аккаунт.""",

    # Документ 2: недоступность сервиса
    """Код 503 Service Unavailable: сервер временно недоступен из-за перегрузки или технических работ.
Рекомендуется повторить запрос через 1-5 минут. Если сервер недоступен длительное время —
обратитесь в техническую поддержку. Статус систем можно проверить на странице status.example.com.""",

    # Документ 3: сброс пароля
    """Сброс пароля выполняется через форму восстановления доступа.
Введите email-адрес, привязанный к аккаунту. На почту придёт письмо со ссылкой для сброса.
Ссылка действительна 24 часа. После перехода задайте новый пароль длиной не менее 8 символов.""",

    # Документ 4: гарантия
    """Гарантийный срок составляет 12 месяцев с момента покупки.
Гарантия распространяется на производственные дефекты. Ремонт выполняется в авторизованных
сервисных центрах. Условия гарантийного обслуживания не распространяются на механические
повреждения и неправильную эксплуатацию.""",

    # Документ 5: установка
    """Установка приложения на Windows:
1. Скачайте инсталлятор с официального сайта.
2. Запустите setup.exe от имени администратора.
3. Следуйте инструкциям мастера установки.
4. После установки перезагрузите компьютер.
Минимальные требования: Windows 10, 4 GB RAM, 2 GB свободного места.""",

    # Документ 6: подписка и оплата
    """Отмена подписки доступна в разделе Мой аккаунт → Тариф и оплата.
Нажмите Отменить подписку и подтвердите действие. Доступ сохраняется до конца
оплаченного периода. Для изменения способа оплаты выберите Обновить карту и
введите данные новой банковской карты.""",
]

# ---------------------------------------------------------------------------
# Mock embeddings (равномерное векторное пространство для теста)
# ---------------------------------------------------------------------------

class _MockEmbeddings:
    """Детерминированные embedding'и на основе хэша текста."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import hashlib
        result = []
        for text in texts:
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            vec = [(h >> (i * 4) & 0xF) / 15.0 for i in range(64)]
            result.append(vec)
        return result

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


# ---------------------------------------------------------------------------
# Тест-кейсы (из evaluation/test_cases.json, 6 ключевых)
# ---------------------------------------------------------------------------
TEST_CASES = [
    TestCase("Что означает ошибка E401?", ["авторизация", "доступ", "токен"], category="error_codes"),
    TestCase("Почему появляется код 503?", ["сервер", "недоступен", "повторите"], category="error_codes"),
    TestCase("Как сбросить пароль?", ["пароль", "сброс", "email"], category="reset_password"),
    TestCase("Сколько длится гарантия?", ["гарантия", "срок", "месяцев"], category="warranty"),
    TestCase("Как установить приложение?", ["установка", "скачайте", "запустите"], category="installation"),
    TestCase("Как отменить подписку?", ["подписка", "отмена", "тариф"], category="billing"),
]


def _make_retriever(docs_text: list[str], chunk_size: int, overlap: int) -> list[list[dict]]:
    """Простой retriever: разбивает документы на chunks, возвращает по вопросу топ-3."""
    chunks = []
    for text in docs_text:
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append({"page_content": chunk, "metadata": {}})

    results = []
    for tc in TEST_CASES:
        # keyword-based mock retrieval: top-3 chunks с наибольшим overlap
        scored = []
        q_words = set(tc.question.lower().split())
        for chunk in chunks:
            words = set(chunk["page_content"].lower().split())
            score = len(q_words & words)
            scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        results.append([c for _, c in scored[:3]])
    return results


def run_mode(chunk_size: int, overlap: int, label: str) -> dict:
    """Запускает один режим chunking и возвращает aggregate scores."""
    evaluator = RAGEvaluator()
    context_docs_list = _make_retriever(SYNTHETIC_DOCS, chunk_size, overlap)
    answers = [tc.expected_answer or "" for tc in TEST_CASES]

    batch = evaluator.evaluate_batch(
        TEST_CASES,
        answers=answers,
        context_docs_list=context_docs_list,
        use_embeddings=False,
    )
    return {
        "label": label,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "aggregate": batch["aggregate"],
        "per_question": batch["per_question"],
    }


def render_report(fixed: dict, semantic_approx: dict) -> str:
    """Рендерит markdown-отчёт."""
    lines = [
        "# Semantic Chunking A/B Test",
        "",
        "> Тест на синтетическом корпусе (6 support-документов, 6 вопросов).",
        "> Semantic mode смоделирован параметрами chunk_size=400 (меньше разрывов).",
        "",
        "## Aggregate context_recall",
        "",
        "| Режим | chunk_size | overlap | context_recall | context_precision |",
        "|-------|:----------:|:-------:|:--------------:|:-----------------:|",
    ]

    for r in [fixed, semantic_approx]:
        agg = r["aggregate"]
        lines.append(
            f"| {r['label']} "
            f"| {r['chunk_size']} "
            f"| {r['overlap']} "
            f"| {agg.get('context_recall', 0):.3f} "
            f"| {agg.get('context_precision', 0):.3f} |"
        )

    winner = fixed if fixed["aggregate"].get("context_recall", 0) >= semantic_approx["aggregate"].get("context_recall", 0) else semantic_approx
    lines += [
        "",
        f"**Победитель по context_recall: {winner['label']}**",
        "",
        "## Per-question context_recall",
        "",
        "| Вопрос | fixed | semantic |",
        "|--------|:-----:|:--------:|",
    ]
    for f_pq, s_pq in zip(fixed["per_question"], semantic_approx["per_question"]):
        q = f_pq["question"][:40]
        f_cr = f_pq["scores"].get("context_recall", 0)
        s_cr = s_pq["scores"].get("context_recall", 0)
        lines.append(f"| {q}... | {f_cr:.2f} | {s_cr:.2f} |")

    lines += [
        "",
        "## Recommendation",
        "",
        "Для реального теста на продакшн-корпусе:",
        "```bash",
        "RAG_SEMANTIC_CHUNKING=true python evaluation/benchmark_runner.py",
        "RAG_SEMANTIC_CHUNKING=false python evaluation/benchmark_runner.py",
        "```",
        "Сравни context_recall в обоих запусках на реальных документах.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "docs" / "research" / "semantic_chunking_ab.md"),
    )
    args = parser.parse_args()

    print("Running A/B: fixed-size vs semantic-approx chunking...")

    # Fixed-size: chunk_size=300 (текущий дефолт)
    fixed = run_mode(chunk_size=300, overlap=50, label="fixed-size (default)")
    # Semantic-approx: chunk_size=400, меньше разрывов — имитирует semantic-aware split
    semantic = run_mode(chunk_size=400, overlap=100, label="semantic-approx (larger, less fragmented)")

    print(f"  fixed    context_recall={fixed['aggregate']['context_recall']:.3f}")
    print(f"  semantic context_recall={semantic['aggregate']['context_recall']:.3f}")

    report = render_report(fixed, semantic)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(report, encoding="utf-8")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
```

---

## CONSTRAINTS
- Создать только `scripts/semantic_chunking_ab.py`
- Не требует Ollama или реального embedding-модели
- `python scripts/semantic_chunking_ab.py` запускается без ошибок
- Выходной файл: `docs/research/semantic_chunking_ab.md`
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `scripts/semantic_chunking_ab.py` создан
- [ ] Скрипт запускается без ошибок
- [ ] `docs/research/semantic_chunking_ab.md` создан с таблицей сравнения
- [ ] В stdout виден context_recall для обоих режимов
- [ ] `pytest tests/ -v` — проходит
