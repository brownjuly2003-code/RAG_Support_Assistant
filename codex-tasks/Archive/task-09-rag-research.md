# Task 09 — Research: RAG relevance and top methods in 2025-2026

## Goal
Write a research report on the current state of RAG: is classic RAG still relevant,
what approaches are replacing or extending it, what's actually used in production.

## Output
Create file `docs/research/rag-landscape-2026.md`.
Fill in the template below. Replace every `[...]` with findings from web search.
Search recent sources: arxiv.org, Eugene Yan blog, Chip Huyen blog, LangChain blog,
Simon Willison, HuggingFace blog, a16z AI, industry reports (2025-2026 only).

---

```markdown
# RAG Landscape 2026: What's Still Relevant

*Researched: [date]*
*Sources: [list 5-8 URLs used]*

---

## Verdict: Is Classic RAG Still Relevant?

[2-3 sentences: yes/no/partially, and why. Is it being replaced by long-context LLMs?
What does the data say about adoption in production?]

**Short answer:** [one sentence]

---

## Why Classic RAG Is Being Challenged

| Challenge | What replaces it | Maturity |
|-----------|-----------------|---------|
| [e.g. chunking loses context] | [e.g. long-context models] | [prod/early/research] |
| [...] | [...] | [...] |
| [...] | [...] | [...] |

---

## Top 5 Methods in Production (2025-2026)

### 1. [Method name]
**What it is:** [1 sentence]
**Why it's hot:** [1 sentence]
**Who uses it:** [companies or products]
**Our project relevance:** [does it apply to RAG Support Assistant? yes/no/partial]

### 2. [Method name]
[same structure]

### 3. [Method name]
[same structure]

### 4. [Method name]
[same structure]

### 5. [Method name]
[same structure]

---

## Methods to Watch (Not Production Yet)

| Method | Status | Why interesting |
|--------|--------|----------------|
| [...] | research/early | [...] |
| [...] | research/early | [...] |
| [...] | research/early | [...] |

---

## What RAG Support Assistant Should Adopt Next

Based on research, these 3 improvements are most impactful for a support-ticket RAG system:

1. **[Method]** — [why, expected impact]
2. **[Method]** — [why, expected impact]
3. **[Method]** — [why, expected impact]

---

## Sources

1. [Title] — [URL] — [date]
2. [Title] — [URL] — [date]
3. [Title] — [URL] — [date]
4. [Title] — [URL] — [date]
5. [Title] — [URL] — [date]
```

---

## CONSTRAINTS
- Create ONLY `docs/research/rag-landscape-2026.md`
- Do NOT modify any code files
- Sources must be from 2025 or 2026 — no older
- No `[...]` placeholders left in final file
- Max 120 lines

## DONE WHEN
- [ ] File exists at `docs/research/rag-landscape-2026.md`
- [ ] No `[...]` remaining in the file
- [ ] At least 5 sources with real URLs listed
- [ ] "Our project relevance" filled in for each of the 5 methods
