# R7 LLM-judged baseline — генерация измерена (faithfulness 0.833 / relevancy 0.838)

- Дата: 2026-06-03
- Цель: снять потолок «недоказанного качества» (оба аудита оценивали proven-quality
  6.5/10, т.к. faithfulness / answer_relevancy **никогда не измерялись** — free LLM-API
  гео-блокированы с RU IP). Дополняет `2026-06-03-free-r7-retrieval-baseline.md`,
  который закрыл только retrieval-сторону.
- Разблокировка: добавлен провайдер `mistral` в `scripts/aircargo_ragas_free.py`
  (OpenAI-совместимый endpoint Mistral **доступен с RU IP без VPN**, через проектный
  `MISTRAL_API_KEY`). Это единственный путь к LLM-судье без карты/VPN.
- Судья + генератор: `mistral-small-latest` (один LLM на обе роли, как во free-скрипте).
- Корпус: aircargo, 100 RU curated-кейсов; контексты — те же закэшированные RRF top-k
  (`.tmp/ab_candidates.json`, БЕЗ production-реранка bge-reranker-v2-m3). Переингест не нужен.
- Прогон: 100/100 кейсов, **300 LLM-вызовов** (generate + faithfulness-judge +
  relevancy-judge на кейс), 0 generate-ошибок, 0 пустых ответов. Стоимость sub-dollar.
- Run id: `20260603T031646Z-e437ad07`
  (`reports/ragas/20260603T031646Z-e437ad07-aircargo-ragas.{md,json}`).

## Результат — впервые измеренная генерация

| Метрика | mean | примечание |
|---|---|---|
| **faithfulness** (LLM-judged) | **0.833** | 🆕 ответ опирается только на контекст |
| **answer_relevancy** (LLM-judged) | **0.838** | 🆕 ответ отвечает на вопрос |
| context_precision (keyword) | 0.488 | подтверждает retrieval-baseline |
| context_recall (keyword) | 0.785 | подтверждает retrieval-baseline |

`context_precision`/`recall` совпали с прошлым прогоном до тысячных → сигнал устойчив,
не артефакт одного запуска.

## Главный вывод: бутылочное горло — retrieval, не генерация

Корреляция faithfulness с recall (LLM-judge на 91 кейсе с явным recall):

| Группа кейсов | faithfulness | n |
|---|---|---|
| zero-recall (нужный фрагмент не найден) | **0.624** | 17 |
| full-recall (всё найдено) | **0.893** | 74 |

Когда retrieval попадает, генерация надёжна (0.893). Просадка faithfulness идёт ровно
там, где ретривер мажет. **Качество ответов упирается в retrieval-recall/precision, а
не в LLM.** Дальнейший тюнинг промптов/моделей генерации даст мало — работать надо над
retrieval.

## Actionable: класс запросов `*-required-fields` систематически промахивается

Все 17 zero-recall кейсов концентрированы на запросах «какие поля/реквизиты обязательны»
и escalation-сценариях:

```
dangerous-goods-fields · customs-clearance-fields · waybill-first-mile-fields
waybill-escalation-events · incident-response-required-fields · access-control-review
driver-hours-required-fields · warehouse-3pl-required-fields · perishable-temperature-controls
oversized-permit-route · subject-rights-required-fields · conflict-interest-sanctions
fuel-supply-evidence · gps-monitoring-required-fields · weight-control-required-fields
cross-border-required-fields · breach-notification-required-fields
```

Нужный фрагмент (как правило — список конкретных полей в таблице/структурной секции) не
доходит до RRF top-k. Это recall ретривера: structural-chunking A/B его НЕ закрыл
(recall-neutral 73% vs 74%). Кандидаты на следующий шаг (measure→fix→re-measure):

1. **BGE-M3 native sparse** (R5-продолжение) — lexical-составляющая для точечных
   «обязательные поля X» запросов, где dense-эмбеддинг размывает специфику.
2. **Query-expansion / HyDE** на `*-required-fields`-классе.
3. **Parent-child / section-aware chunking** — чтобы список полей не дробился на чанки,
   теряющие заголовок-якорь.
4. Проверить полноту корпуса по этим темам (нет фрагмента → recall недостижим в принципе).

## Диагностика 17 zero-recall — 10 recoverable реранкером + 7 настоящих промахов

Кэш `.tmp/ab_candidates.json` хранит **полный RRF-пул** (24-40 кандидатов/кейс), а recall в
eval считался по **top-5 БЕЗ production-реранкера** bge-reranker-v2-m3. Разбор 17 промахов по
наличию ключей в (top-5 / полный пул / корпус):

| Категория | n | Что значит |
|---|---:|---|
| **rerank_recoverable** | **10** | ключи ЕСТЬ в RRF-пуле, но ниже top-5 → production-реранкер их, вероятно, поднимает. Кэш-baseline без реранка **занижает recall** |
| **deep_retrieval_miss** | **7** | ключи в корпусе есть, но RRF (dense+BM25) не достал чанк даже в top-40 — настоящая цель |
| content_gap | 0 | весь нужный контент в корпусе присутствует |

⇒ Эффективный recall 0.785 — это **нижняя граница без реранкера**; полный A/B 2026-06-02 уже
дал **80% top-5 С bge-v2-m3** vs 74% без.

**Уточнение по рангу (без overclaim):** «10 recoverable» градуированы по тому, на каком ранге
в пуле ключи впервые сходятся в одном кандидате:

| Ранг в пуле | n | Прогноз |
|---|---:|---|
| ≤10 | 4 | реранкер легко поднимает в top-5 → почти наверняка покрыто в проде (incident-response, subject-rights, conflict-interest, breach-notification) |
| 11-20 | 5 | реранкер *может* поднять, не гарантировано — нужен top-5-с-реранком прогон |
| >20 (rank 32/40) | 1 | `waybill-escalation-events` — фактически deep-miss |

Бьётся с A/B (80% = реранкер вытащил ~6 из 26 non-full, не все 10). **Честная цель:
7 deep-miss + 1 near-deep подтверждённо трудные; 5 mid-rank под вопросом; только 4 явно
покрыты реранкером.** (Корректирует первоначальное «17→7» — оно было оптимистично.)

### Корневая причина 7 deep-miss (одинакова во всех)

Все 7 — запросы класса `*-required-fields`. Ожидаемые ключи — это **ID полей внутри
markdown-таблиц** под заголовком «## 2. Обязательные поля»:

```
Q: «Какие поля нужны для допуска dangerous goods к air cargo рейсу?»
kws: cargo_un_number, cargo_class
корпус: 05_tlog_regulation_dangerous_goods.md → «## 2. Обязательные поля»
        | `cargo_un_number` | Номер груза UN | `{{cargo_un_number}}` |
```

Запрос на естественном русском **не пересекается лексически** со snake_case-идентификаторами.
Dense (BGE-M3) не сближает code-токен `cargo_un_number` с NL-запросом; BM25 тоже мажет (нет
общих слов). Кейсы: `dangerous-goods-fields`, `customs-clearance-fields`, `waybill-first-mile-fields`,
`access-control-review`, `driver-hours-required-fields`, `perishable-temperature-controls`,
`cross-border-required-fields` — все по шаблону `05_tlog_regulation_*` / `06_comp_policy_*`.

### Что это меняет в плане фикса

- **BGE-M3 native sparse / R5 — СЛАБО** для этих 7: общих терминов между запросом и таблицей
  нет, sparse усиливает exact-match там, где совпадать нечему. (Корректирует прежнюю рекомендацию.)
- **Contextual-header / parent-child chunking — СИЛЬНО**: чанк-таблица должна нести якорь из
  заголовка/тайтла («Обязательные поля для опасных грузов / dangerous goods»). Тогда dense
  матчит «какие поля нужны для dangerous goods» ↔ контекстуализированный чанк. Это
  Anthropic-style contextual retrieval, сделанный правильно (сейчас static-header баган, R2).
- **HyDE — умеренно**: гипотетический ответ может дать field-подобные термины, но вряд ли точные
  snake_case ID.

Рекомендуемый следующий remote-A/B (heavy ingest → Colab/iMac): **contextual-header chunking на
`05_tlog_regulation_*`/`06_comp_policy_*`**, замер recall на этих 7 + faithfulness re-run.
Reranker-recoverable 10 — проверить отдельным top-5-С-реранком прогоном (подтвердить, что
production уже их закрывает, и не гоняться за артефактом rerank-less baseline).

## Воспроизведение

```
set -a; . ./.env; set +a        # подгружает MISTRAL_API_KEY, не печатает
python scripts/aircargo_ragas_free.py --provider mistral --min-interval 1.2
```

Heavy-ингест BGE-M3 / production-реранк — по-прежнему только Colab/iMac (на Windows-хосте
запрещён >1 GiB). LLM-judging же — чистые API-вызовы на закэшированных контекстах, локально OK.
