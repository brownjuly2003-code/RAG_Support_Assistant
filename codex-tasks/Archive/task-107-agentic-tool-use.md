# Task 107 — Agentic tool-use framework (multi-step + confirmation)

## Context
AGENT-1/2/3 из commercial-plan объединены в одну задачу, так как все три
— про одну архитектурную перестройку: добавить LangGraph tool-use поверх
текущего linear retrieve→grade→generate пайплайна. Без tools бот
отвечает **только** на "что X?" вопросы; не может "покажи статус заказа
#123", "смени email", "создай тикет" — а это 30-40% support-трафика в
реальных продуктах.

Текущий код: `graph.py` — linear nodes без tool-calling. `agent/` папка
пустая (кроме `__init__.py`) — там и будем строить агентный слой.

## Goal
Добавить tool-use через LangGraph `ToolNode` + router. Три built-in tools:
- `search_kb(query)` — обёртка над текущим retrieve pipeline (по дефолту)
- `check_order_status(order_id)` — мок, читает из `tenant_settings.orders_api`
  (если не настроен — возвращает "Проверка заказов недоступна")
- `create_ticket(summary, priority)` — создаёт `EscalatedTicket` (task-106)

Поддержка **multi-step** цепочки tool-calls и **confirmation** для
необратимых действий.

## Files to change
- `agent/tools.py` — новый: `@tool` декораторы для 3 функций, type hints,
  docstrings (LangChain читает их как tool description)
- `agent/graph.py` — новый: построить граф с router node (LLM решает
  какой tool / сразу ответить) + ToolNode + confirmation_gate node
- `graph.py` (root) — оставить как обратную совместимость: экспортировать
  новый `agent_graph` если feature flag ON, иначе старый linear
- `config/settings.py` — `RAG_AGENTIC_MODE: bool = False` (безопасный default)
- `api/app.py` — если `settings.agentic_mode` включён — использовать
  `agent_graph` в `/api/ask`
- `tests/test_agent_tools.py` — unit-test каждого tool + integration test
  multi-step flow + confirmation flow

## Implementation sketch

### agent/tools.py
```python
from langchain_core.tools import tool

@tool
def search_kb(query: str, tenant_id: str) -> str:
    """Search the knowledge base for documents matching the query.
    Returns top-3 document excerpts. Use this as the default for
    informational questions ("what is X?", "how do I Y?")."""
    from graph import retrieve_documents  # existing function
    docs = retrieve_documents(query, tenant_id=tenant_id, k=3)
    return "\n\n".join(f"[{i+1}] {d.page_content[:500]}" for i, d in enumerate(docs))

@tool
def check_order_status(order_id: str, tenant_id: str) -> str:
    """Check the status of a customer order by ID. Use when user asks
    about their order, delivery status, shipment."""
    # read tenant_settings.orders_api_url; if not configured → fallback message
    ...

@tool
def create_ticket(summary: str, priority: str, tenant_id: str, user_id: str) -> str:
    """Create an escalation ticket for the operator. Use ONLY when the
    user explicitly requests operator help, or when other tools cannot
    answer. This is an IRREVERSIBLE ACTION — requires confirmation."""
    ...
```

### agent/graph.py
```python
from langgraph.prebuilt import ToolNode, create_react_agent
# или вручную: StateGraph с conditional routing

# State: messages + pending_action (для confirmation)
# Router node: LLM видит messages → возвращает AIMessage с tool_calls или plain answer
# ToolNode: выполняет tool_calls
# Confirmation gate: если tool = create_ticket / любой с flag require_confirmation → pause, вернуть в UI "подтверждаете?" → на next turn пользователь confirms/denies
```

### Confirmation flow
1. LLM решает вызвать `create_ticket(...)`
2. Граф попадает в `confirmation_gate` → сохраняет pending_action в
   `state.pending_action`, выходит с specialspeciallegedly route `await_confirmation`
3. API возвращает ответ с `requires_confirmation: true, action_summary: "..."`
4. Frontend показывает "Подтвердите: создать тикет с темой X?"
5. User confirms → следующий `/api/ask` шлёт `confirm=true` →
   граф продолжает с ToolNode, иначе отменяет

## CONSTRAINTS
- Feature-flagged: с `RAG_AGENTIC_MODE=false` (default) — никаких
  изменений в existing pipeline, все 222 теста проходят
- Tool use требует LLM с tool-calling capability — проверь что модель
  (Qwen/Llama) поддерживает. Fallback: ReAct-style prompting если native
  не работает
- `check_order_status` — **mock** по умолчанию. Реальная интеграция
  outside of this task
- Cost monitoring: каждый tool-call = лишний LLM round-trip. Жёсткий
  лимит max 5 tool-calls per user turn (иначе break + escalate)

## DONE WHEN
- [ ] 3 tools определены, docstrings читаются агентом
- [ ] Multi-step: "сколько стоит доставка в Москву для заказа #42" →
      search_kb(доставка Москва) + check_order_status(42) → integrated answer
- [ ] Confirmation: "создай тикет о проблеме X" → UI спрашивает → confirm → ticket
- [ ] Feature flag: OFF → старый pipeline, ON → агентный
- [ ] 235+ passed (~10 новых тестов для tools + graph)
- [ ] Langfuse trace показывает tool_calls
- [ ] Commit: "Agentic tool-use framework with multi-step + confirmation (task-107)"
