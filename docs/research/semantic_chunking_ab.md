# Semantic Chunking A/B Test

> Тест на синтетическом корпусе: 6 документов, 6 вопросов.
> Semantic mode работает без Ollama и реальных embedding-моделей.

## Aggregate context_recall

| Режим | chunk_size | overlap | context_recall | context_precision |
| --- | :---: | :---: | :---: | :---: |
| fixed-size (default) | 300 | 50 | 0.445 | 0.213 |
| semantic-approx | adaptive | adaptive | 0.556 | 0.238 |

**Победитель по context_recall: semantic-approx**

## Per-question context_recall

| Вопрос | fixed | semantic |
| --- | :---: | :---: |
| Что означает ошибка E401?... | 0.67 | 0.67 |
| Почему появляется код 503?... | 1.00 | 1.00 |
| Как сбросить пароль?... | 0.33 | 1.00 |
| Сколько длится гарантия?... | 0.00 | 0.00 |
| Как установить приложение?... | 0.00 | 0.00 |
| Как отменить подписку?... | 0.67 | 0.67 |

## Recommendation

Для следующего шага стоит прогнать те же сценарии на реальном корпусе знаний и сравнить aggregate context_recall.