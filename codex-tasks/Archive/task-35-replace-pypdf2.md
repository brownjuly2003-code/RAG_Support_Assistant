# Task 35 — Заменить PyPDF2 на pypdf

## Goal
`PyPDF2` устарел и выдаёт DeprecationWarning при каждом запуске pytest.
Заменить на `pypdf` — форк того же пакета, полностью совместимый API, активно поддерживается.

## API совместимость
`pypdf` — переименованный `PyPDF2 >= 3.0`. API идентичен:
```python
# PyPDF2
import PyPDF2
reader = PyPDF2.PdfReader(fh)

# pypdf — то же самое
import pypdf
reader = pypdf.PdfReader(fh)
```

## Files to change
- `requirements.txt` — строка 24: `PyPDF2>=3.0.0` → `pypdf>=3.0.0`
- `ingestion/loader.py` — 3 изменения

---

## requirements.txt

Строка 24, заменить:
```
PyPDF2>=3.0.0
```
на:
```
pypdf>=3.0.0
```

---

## ingestion/loader.py

**Изменение 1** — строка 7 docstring (комментарий):
```python
# было:
.txt, .md, .pdf (PyPDF2), .docx (python-docx), .json, .csv
# стало:
.txt, .md, .pdf (pypdf), .docx (python-docx), .json, .csv
```

**Изменение 2** — строки 44-47, импорт:
```python
# было:
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None  # type: ignore[assignment]

# стало:
try:
    import pypdf
except ImportError:
    pypdf = None  # type: ignore[assignment]
```

**Изменение 3** — строки 182-191, метод `_read_pdf`:
```python
# было:
def _read_pdf(self, path: Path) -> List[Document]:
    if PyPDF2 is None:
        raise ImportError("PyPDF2 is required for PDF files: pip install PyPDF2")
    docs: List[Document] = []
    with path.open("rb") as fh:
        reader = PyPDF2.PdfReader(fh)

# стало:
def _read_pdf(self, path: Path) -> List[Document]:
    if pypdf is None:
        raise ImportError("pypdf is required for PDF files: pip install pypdf")
    docs: List[Document] = []
    with path.open("rb") as fh:
        reader = pypdf.PdfReader(fh)
```

---

## CONSTRAINTS
- Изменить только `requirements.txt` и `ingestion/loader.py`
- Не менять никакую другую логику
- `pytest tests/ -v` — проходит без DeprecationWarning про PyPDF2
- После замены: `python -c "import pypdf; print(pypdf.__version__)"` — работает

## DONE WHEN
- [ ] `requirements.txt`: `pypdf>=3.0.0` вместо `PyPDF2>=3.0.0`
- [ ] `ingestion/loader.py`: все три вхождения `PyPDF2` заменены на `pypdf`
- [ ] `pytest tests/ -v` — 44 passed, нет PyPDF2 DeprecationWarning
