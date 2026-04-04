# Simulated Model Benchmark - RAG Support Assistant

> Benchmark is simulated from MERA-derived model profiles in `docs/research/llm-model-selection-2025.md`.
> Answers are synthetic and deterministic; ranking reflects relative answer quality, not live Ollama inference.

## Aggregate scores

| Model | MERA Industrial | answer_relevancy | faithfulness | context_recall | Recommendation |
|-------|:---------------:|:----------------:|:------------:|:--------------:|----------------|
| `qwen2.5:7b` | 0.555 | 1.000 | 0.500 | 1.000 | Recommended |
| `gemma3:4b` | 0.477 | 0.708 | 0.500 | 1.000 | Alternative |
| `llama3.1:8b` | 0.437 | 0.681 | 0.333 | 1.000 |  |
| `mistral:7b` | 0.213 | 0.361 | 0.250 | 1.000 |  |

## Notes per model

- `qwen2.5:7b` - RAM: 8-10 GB. Best overall Russian quality. Recommended default.
- `gemma3:4b` - RAM: 6-8 GB. Best instruction following (IFEval 90.2). Lightest option.
- `llama3.1:8b` - RAM: 8-10 GB. Decent Russian. Good English. Solid backup choice.
- `mistral:7b` - RAM: 8-10 GB. Current default. Weakest Russian per MERA benchmarks.

## Recommendation

Winner of the simulated benchmark: **`qwen2.5:7b`**.

```bash
ollama pull qwen2.5:7b
```

```dotenv
OLLAMA_MODEL_NAME=qwen2.5:7b
```

## Per-category breakdown

| Category | avg answer_relevancy (winner) |
|----------|:-----------------------------:|
| billing | 1.000 |
| error_codes | 1.000 |
| general | 1.000 |
| installation | 1.000 |
| reset_password | 1.000 |
| warranty | 1.000 |