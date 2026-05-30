# Colab Remote Benchmark Runbook

## Purpose

Use Google Colab for any benchmark that may need more than 1 GB RAM. The local
Windows machine and the iMac at `julia@192.168.1.133` must stay thin clients:
do not start Ollama, GraceKelly, Docker, Lima, or model downloads for this
benchmark path.

## Files

- Notebook: `notebooks/rag_support_colab_remote_benchmark.ipynb`
- Reports produced in Colab: `reports/regression/<timestamp>-*.json` and
  `reports/regression/<timestamp>-*.md`

## Safe Flow

1. Open Google Colab interactively.
2. Upload `notebooks/rag_support_colab_remote_benchmark.ipynb`, or open it from
   GitHub on `master`.
3. Run the runtime probe cell and confirm memory/GPU are Colab resources.
4. Run the clone and dependency cells.
5. Run the mock provider benchmark cell first. This must not call providers and
   uses `--no-persist`.
6. For a paid live signal, set `RUN_LIVE = True` in the live cell, enter
   `MISTRAL_API_KEY` through `getpass`, and keep `--max-cases 3` for the first
   run.
7. Download the generated report files from the Colab file browser.

## Boundaries

- Do not use `ollama-small`, `gk-fast`, `gk-strong`, or
  `gracekelly-mixed` from this notebook. Those targets imply local services,
  browser-backed orchestration, or local model RAM.
- Do not persist results to a database from Colab; keep `--no-persist`.
- Do not print or commit `MISTRAL_API_KEY`.
- Do not use the iMac as compute. Its documented role is only SSH/browser
  access, and it already hosts the DV2 Lima VM when that demo is active.

## iMac Thin-Client Check

The known SSH endpoint from `D:/DE_project` is:

```bash
ssh julia@192.168.1.133
```

The iMac is an 8 GB Intel i5 host. It is not suitable for local LLM inference.
If using it to open Colab manually, close the browser after downloading reports
and do not start Lima/Docker unless continuing `DE_project` work.

## Windows Laptop Thin-Client Check

On 2026-05-30, the current Windows laptop was visible as `JULIADEV25` at
`192.168.1.134`, with an Intel Core Ultra 5 125H, 16 GB physical RAM, and about
6 GB free RAM during the check. WSL and Docker Desktop were already running,
with `vmmemWSL` observed at about 1.07 GB RSS.

Conclusion: do not use this laptop for local model or Docker-backed benchmark
work under the 1 GB process limit. It is suitable only as a thin browser or SSH
client for the Colab path.
