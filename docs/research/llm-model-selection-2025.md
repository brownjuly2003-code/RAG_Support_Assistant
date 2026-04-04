# Research: выбор LLM для русскоязычного support-ассистента (2025)

## Goal
Проект сейчас использует `mistral` в `OLLAMA_MODEL_NAME`.
Нужно понять, стоит ли оставаться на Mistral для русскоязычных support-тикетов, или лучше перейти на другую локальную Ollama-модель.

## Q1: Сравнение моделей по качеству на русском

Ниже я использую два типа русскоязычных сигналов:

- `MERA Text` как общий русский текстовый бенчмарк.
- `MERA Industrial` как более практичный proxy для support/knowledge QA на русском.

Для `gemma3` и `phi4` в доступных официальных источниках я не нашёл сопоставимого `MERA Text` submit для text-board, поэтому у них опора в основном на `MERA Industrial` и официальные model cards. Это слабее, чем иметь оба сигнала.

| Модель | Размер | Русский score/rank | RAM | Скорость на CPU, tok/s |
|---|---:|---|---|---|
| `mistral:7b` | 7.2B | MERA Text: `0.311` ; MERA Industrial medicine: `0.213` | ~8-10 GB practical RAM | ~6-11 |
| `llama3.1:8b` | 8.0B | MERA Text: `0.401` ; MERA Industrial medicine: `0.437` | ~8-10 GB practical RAM | ~6-11 |
| `qwen2.5:7b` | 7.6B | MERA Text: `0.482` ; MERA Industrial medicine: `0.555` | ~8-10 GB practical RAM | ~6-12 |
| `gemma3:4b` | 4.3B | MERA Industrial medicine: `0.477`; прямого `MERA Text` submit в найденных official sources нет | ~6-8 GB practical RAM | ~10-18 |
| `phi4:14b` | 14B | MERA Industrial medicine: `0.262`; прямого `MERA Text` submit в найденных official sources нет | ~13-16 GB practical RAM | ~3-6 |

Источник по русскому качеству:

- `Mistral-7B-Instruct-v0.3`: MERA Text `0.311`, MERA Industrial medicine `0.213`
- `Meta-Llama-3.1-8B-Instruct`: MERA Text `0.401`, MERA Industrial medicine `0.437`
- `Qwen2.5-7B-Instruct`: MERA Text `0.482`, MERA Industrial medicine `0.555`
- `gemma-3-4b-it`: MERA Industrial medicine `0.477`
- `phi-4`: MERA Industrial medicine `0.262`

Ключевой вывод:

- По русскому general-text и по более прикладному industrial/support-like сигналу лучший баланс у `qwen2.5:7b`.
- `llama3.1:8b` заметно лучше текущего `mistral:7b`, но уступает `qwen2.5:7b` на русском.
- `gemma3` интересна как очень лёгкая альтернатива, но в Ollama на 2026-04-04 нет `gemma3:9b`: доступны `270m`, `1b`, `4b`, `12b`, `27b`.
- `phi4:14b` силён в reasoning, но для этого проекта его русскоязычный сигнал слабее, а official card прямо говорит, что primary use cases у него "primarily in English".

## Q2: Какая модель лучше следует инструкциям на русском?

Для evaluate-узла нужен частный режим: вернуть только число `0-100`.
Прямого public benchmark именно на "верни только число" я не нашёл, поэтому ниже использую официальные instruction-following proxies и отдельно отмечаю выводы-интерпретации.

Рейтинг по instruction-following:

1. `gemma3` — strongest published proxy в найденных official sources: `IFEval 90.2` для `Gemma 3 IT 4B`, `88.9` для `12B`, `90.4` для `27B`.
2. `llama3.1:8b` — официальный `IFEval 80.4`.
3. `qwen2.5:7b` — в найденном official model card нет числа IFEval, но сам Qwen пишет про "significant improvements in instruction following" и "structured outputs especially JSON". Для задачи "верни только число" это сильный косвенный сигнал.
4. `phi4:14b` — Microsoft пишет про "precise instruction adherence", но одновременно ограничивает primary use cases английским.
5. `mistral:7b` — поддерживает function calling, но по русским бенчмаркам уже заметно проигрывает более новым small models.

Практический вывод для evaluate-узла:

- Если выбирать только по published instruction-following proxy, сильнее всех выглядит `gemma3`.
- Если выбирать модель для всего проекта, а не только для judge-step, лучшая инженерная ставка — `qwen2.5:7b`: у неё лучший русский/support сигнал и официальный акцент на structured outputs.
- Для стабильного `ONLY number` всё равно нельзя полагаться только на obedience модели. Нужен жёсткий prompt + `temperature=0` + парсер, который берёт первое число и считает остальное ошибкой. Это вывод по практике эксплуатации, а не прямой benchmark.

## Q3: Специализированные русскоязычные модели

Доступны ли через Ollama:

- `bambucha/saiga-llama3`
- `akdengi/saiga-llama3-8b`
- `cyberlis/saiga-mistral:7b-lora-custom-q4_K`
- `wavecut/vikhr`

Качество vs `Qwen2.5` / `Llama3.1`:

- Эти модели доступны в Ollama, но в community namespaces, а не как first-party library models уровня `qwen2.5`, `llama3.1`, `gemma3`, `phi4`.
- В найденных свежих official sources у меня нет сопоставимого набора benchmark-данных, который бы убедительно показывал их превосходство над `qwen2.5:7b`.
- По состоянию найденных Ollama pages это в основном более старые community-сборки на базе старых backbone-моделей, опубликованные 1-2 года назад.

Вывод:

- `saiga` / `vikhr` имеет смысл держать как A/B-кандидатов, если важнее локальный русский стиль ответа.
- Делать их default production choice вместо `qwen2.5:7b` я не рекомендую: evidence хуже, поддержка менее стандартная, бенчмарк-сигнал слабее.

## Q4: Практическая рекомендация для support RAG

Для задачи "понять вопрос на русском -> найти ответ в базе знаний -> коротко и точно ответить на русском" оптимальный выбор:

- RAM 8GB: `gemma3:4b`, если машина реально ограничена и на ней одновременно живут приложение, embeddings, vectordb и Ollama.
- RAM 16GB: `qwen2.5:7b`.
- GPU 4-8GB VRAM: `qwen2.5:7b` на 8GB VRAM; `gemma3:4b` на 4-6GB VRAM.

Рекомендация:

- `8GB RAM`: `gemma3:4b`
- `16GB RAM`: `qwen2.5:7b`
- `GPU 4-8GB VRAM`: `qwen2.5:7b` (или `gemma3:4b`, если VRAM ближе к 4GB и нужен запас)

Обоснование:

- `qwen2.5:7b` лучше всех из сравниваемых small models показывает себя на русском и на industrial/support-like русском benchmark.
- `llama3.1:8b` — хороший backup choice, но не лидер.
- `mistral:7b` уже не выглядит лучшим default choice: его русские результаты заметно слабее.
- `phi4:14b` не оправдывает свой больший RAM budget именно для русскоязычного support-RAG.

## Q5: Ollama pull commands

Топ-3 практических кандидата:

```bash
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
ollama pull gemma3:4b
```

Нужно ли менять `OLLAMA_MODEL_NAME` в `.env`?

- Да.
- Если цель — лучший общий default для русскоязычного support-RAG, то:

```dotenv
OLLAMA_MODEL_NAME=qwen2.5:7b
```

## Output: Recommendation

```text
ТЕКУЩИЙ ВЫБОР: mistral:7b
РЕКОМЕНДУЮ ЗАМЕНИТЬ НА: qwen2.5:7b
ПРИЧИНА: это лучший баланс русского качества и support-подобного industrial качества среди сравниваемых локальных моделей; он заметно сильнее текущего Mistral на MERA Text и MERA Industrial, а официальный model card отдельно подчёркивает instruction following и structured outputs.
КОМАНДА: ollama pull qwen2.5:7b
ENV: OLLAMA_MODEL_NAME=qwen2.5:7b
```

## Notes

- `gemma3:9b` в task-файле выглядит устаревшей/неточной ссылкой. По официальной Ollama library, актуальные размеры Gemma 3 на 2026-04-04: `270m`, `1b`, `4b`, `12b`, `27b`.
- Скорости `tok/s` в таблице выше — инженерная оценка для типичного современного CPU и Q4-уровня квантования. В primary sources для точного apples-to-apples CPU benchmark по всем пяти моделям я такого набора не нашёл, поэтому эти числа нужно воспринимать как planning estimate, а не как строгий benchmark.

## Sources

- MERA Text:
  - https://mera.a-ai.ru/en/submits/12064
  - https://mera.a-ai.ru/en/submits/11421
  - https://mera.a-ai.ru/en/submits/11426
- MERA Industrial:
  - https://mera.a-ai.ru/en/industrial/submits/66
  - https://mera.a-ai.ru/en/industrial/submits/46
  - https://mera.a-ai.ru/en/industrial/submits/34
  - https://mera.a-ai.ru/en/industrial/submits/58
  - https://mera.a-ai.ru/en/industrial/submits/51
- Official model cards and library pages:
  - https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
  - https://huggingface.co/meta-llama/Meta-Llama-3.1-8B-Instruct
  - https://ai.google.dev/gemma/docs/core/model_card_3
  - https://huggingface.co/microsoft/phi-4
  - https://ollama.com/library/qwen2.5
  - https://ollama.com/library/llama3.1
  - https://ollama.com/library/gemma3
  - https://ollama.com/library/phi4
  - https://ollama.com/cyberlis/saiga-mistral%3A7b-lora-q4_K
