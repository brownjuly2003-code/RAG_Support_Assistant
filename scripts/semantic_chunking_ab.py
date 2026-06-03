#!/usr/bin/env python3
"""
scripts/semantic_chunking_ab.py

Сравнивает fixed-size vs semantic chunking по context_recall на синтетических документах.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.ragas_eval import RAGEvaluator, TestCase


SYNTHETIC_DOCS = [
    """Ошибка E401 означает отказ в авторизации. Токен доступа недействителен или истёк.
Для восстановления доступа нужно повторно авторизоваться через личный кабинет.
Введите логин и пароль, получите новый токен. Если проблема повторяется, проверьте
корректность учётных данных и не заблокирован ли аккаунт.""",
    """Код 503 Service Unavailable: сервер временно недоступен из-за перегрузки или технических работ.
Рекомендуется повторить запрос через 1-5 минут. Если сервер недоступен длительное время,
обратитесь в техническую поддержку. Статус систем можно проверить на странице status.example.com.""",
    """Сброс пароля выполняется через форму восстановления доступа.
Введите email-адрес, привязанный к аккаунту. На почту придёт письмо со ссылкой для сброса.
Ссылка действительна 24 часа. После перехода задайте новый пароль длиной не менее 8 символов.""",
    """Гарантийный срок составляет 12 месяцев с момента покупки.
Гарантия распространяется на производственные дефекты. Ремонт выполняется в авторизованных
сервисных центрах. Условия гарантийного обслуживания не распространяются на механические
повреждения и неправильную эксплуатацию.""",
    """Установка приложения на Windows:
1. Скачайте инсталлятор с официального сайта.
2. Запустите setup.exe от имени администратора.
3. Следуйте инструкциям мастера установки.
4. После установки перезагрузите компьютер.
Минимальные требования: Windows 10, 4 GB RAM, 2 GB свободного места.""",
    """Отмена подписки доступна в разделе Мой аккаунт → Тариф и оплата.
Нажмите Отменить подписку и подтвердите действие. Доступ сохраняется до конца
оплаченного периода. Для изменения способа оплаты выберите Обновить карту и
введите данные новой банковской карты.""",
]


TEST_CASES = [
    TestCase("Что означает ошибка E401?", ["авторизация", "доступ", "токен"], category="error_codes"),
    TestCase("Почему появляется код 503?", ["сервер", "недоступен", "повторить"], category="error_codes"),
    TestCase("Как сбросить пароль?", ["пароль", "сброс", "email"], category="reset_password"),
    TestCase("Сколько длится гарантия?", ["гарантия", "срок", "месяцев"], category="warranty"),
    TestCase("Как установить приложение?", ["установка", "скачайте", "запустите"], category="installation"),
    TestCase("Как отменить подписку?", ["подписка", "отмена", "тариф"], category="billing"),
]


class _MockEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.md5(text.encode("utf-8")).hexdigest()
            raw = int(digest, 16)
            vectors.append([(raw >> (index * 4) & 0xF) / 15.0 for index in range(64)])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _chunk_docs_fixed(docs_text: list[str], chunk_size: int, overlap: int) -> list[dict]:
    chunks: list[dict] = []
    step = max(chunk_size - overlap, 1)
    for text in docs_text:
        for start in range(0, len(text), step):
            chunk = text[start:start + chunk_size]
            if chunk.strip():
                chunks.append({"page_content": chunk, "metadata": {}})
    return chunks


def _chunk_docs_semantic_approx(docs_text: list[str]) -> list[dict]:
    embeddings = _MockEmbeddings()
    chunks: list[dict] = []
    for text in docs_text:
        paragraphs = [part.strip() for part in text.splitlines() if part.strip()]
        if not paragraphs:
            continue
        paragraph_vectors = embeddings.embed_documents(paragraphs)
        current = [paragraphs[0]]
        current_sum = sum(paragraph_vectors[0])
        for index in range(1, len(paragraphs)):
            candidate_sum = sum(paragraph_vectors[index])
            if abs(candidate_sum - current_sum) > 6 and len(" ".join(current)) >= 140:
                chunks.append({"page_content": "\n".join(current), "metadata": {}})
                current = [paragraphs[index]]
                current_sum = candidate_sum
            else:
                current.append(paragraphs[index])
                current_sum = (current_sum + candidate_sum) / 2
        if current:
            chunks.append({"page_content": "\n".join(current), "metadata": {}})
    return chunks


def _retrieve_top_chunks(chunks: list[dict]) -> list[list[dict]]:
    results: list[list[dict]] = []
    for test_case in TEST_CASES:
        scored = []
        query_words = set(test_case.question.lower().split())
        for chunk in chunks:
            words = set(chunk["page_content"].lower().split())
            score = len(query_words & words)
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        results.append([chunk for _, chunk in scored[:3]])
    return results


def run_mode(label: str, chunks: list[dict], chunk_size: str, overlap: str) -> dict:
    evaluator = RAGEvaluator()
    context_docs_list = _retrieve_top_chunks(chunks)
    answers = [test_case.expected_answer or "" for test_case in TEST_CASES]
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


def render_report(fixed: dict, semantic: dict) -> str:
    lines = [
        "# Semantic Chunking A/B Test",
        "",
        "> Тест на синтетическом корпусе: 6 документов, 6 вопросов.",
        "> Semantic mode работает без Ollama и реальных embedding-моделей.",
        "",
        "## Aggregate context_recall",
        "",
        "| Режим | chunk_size | overlap | context_recall | context_precision |",
        "| --- | :---: | :---: | :---: | :---: |",
    ]

    for result in [fixed, semantic]:
        aggregate = result["aggregate"]
        lines.append(
            f"| {result['label']} | {result['chunk_size']} | {result['overlap']} | "
            f"{aggregate.get('context_recall', 0):.3f} | "
            f"{aggregate.get('context_precision', 0):.3f} |"
        )

    winner = fixed
    if semantic["aggregate"].get("context_recall", 0) > fixed["aggregate"].get("context_recall", 0):
        winner = semantic

    lines.extend(
        [
            "",
            f"**Победитель по context_recall: {winner['label']}**",
            "",
            "## Per-question context_recall",
            "",
            "| Вопрос | fixed | semantic |",
            "| --- | :---: | :---: |",
        ]
    )

    for fixed_item, semantic_item in zip(fixed["per_question"], semantic["per_question"], strict=True):
        question = fixed_item["question"][:40]
        fixed_score = fixed_item["scores"].get("context_recall", 0)
        semantic_score = semantic_item["scores"].get("context_recall", 0)
        lines.append(f"| {question}... | {fixed_score:.2f} | {semantic_score:.2f} |")

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "Для следующего шага стоит прогнать те же сценарии на реальном корпусе знаний и сравнить aggregate context_recall.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "docs" / "research" / "semantic_chunking_ab.md"),
    )
    args = parser.parse_args()

    print("Running A/B: fixed-size vs semantic chunking...")

    fixed_chunks = _chunk_docs_fixed(SYNTHETIC_DOCS, chunk_size=300, overlap=50)
    semantic_chunks = _chunk_docs_semantic_approx(SYNTHETIC_DOCS)

    fixed = run_mode("fixed-size (default)", fixed_chunks, "300", "50")
    semantic = run_mode("semantic-approx", semantic_chunks, "adaptive", "adaptive")

    print(f"  fixed    context_recall={fixed['aggregate']['context_recall']:.3f}")
    print(f"  semantic context_recall={semantic['aggregate']['context_recall']:.3f}")

    report = render_report(fixed, semantic)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8", newline="\n")
    print(f"Report: {output_path}")


if __name__ == "__main__":
    main()
