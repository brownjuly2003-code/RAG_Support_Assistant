# Task 101 — Normalize line endings with `.gitattributes`

## Context
Каждый git add / git commit на Windows пишет warnings:
```
warning: in the working copy of 'api/app.py', LF will be replaced by CRLF...
```

Шум в логах, плюс риск: разные разработчики (Linux/Mac/Windows) могут
создать merge-конфликты из-за EOL'ов. Сейчас `core.autocrlf` не настроен
единообразно.

## Goal
Добавить `.gitattributes` → зафиксировать LF для текстовых файлов,
игнорировать бинарники. Это **repo-wide** настройка, не зависит от
локальной конфигурации разработчика.

## Files to create
- `.gitattributes` в корне

## Content

```
# Default: нормализовать текст к LF в репозитории
* text=auto eol=lf

# Явные текстовые типы — всегда LF
*.py    text eol=lf
*.md    text eol=lf
*.yml   text eol=lf
*.yaml  text eol=lf
*.json  text eol=lf
*.toml  text eol=lf
*.ini   text eol=lf
*.cfg   text eol=lf
*.sh    text eol=lf
*.sql   text eol=lf
*.html  text eol=lf
*.css   text eol=lf
*.js    text eol=lf

# Windows-специфичные
*.bat   text eol=crlf
*.cmd   text eol=crlf
*.ps1   text eol=crlf

# Бинарники — не трогать
*.png   binary
*.jpg   binary
*.jpeg  binary
*.gif   binary
*.pdf   binary
*.db    binary
*.sqlite binary
*.whl   binary
*.gz    binary
*.zip   binary
```

## После создания — однократная ренормализация

После коммита `.gitattributes` прогнать:
```bash
git add --renormalize .
git status  # покажет все файлы с EOL-изменениями
git commit -m "Apply .gitattributes line ending normalization"
```

Это два коммита:
1. Добавить `.gitattributes`
2. Прогнать renormalize (отдельный коммит, чтобы diff читался)

## CONSTRAINTS
- Никаких изменений в коде, только EOL
- После renormalize warnings должны пропасть на последующих коммитах
- `pytest tests/ -q` → те же **214 passed** (или 220 если task-100
  уже merge'нут) — EOL не влияет на runtime

## DONE WHEN
- [ ] `.gitattributes` в корне с правилами выше
- [ ] `git add --renormalize .` применён отдельным коммитом
- [ ] Повторный `git add` какого-то файла **не** выдаёт CRLF warning
- [ ] pytest не сломался
- [ ] Commits:
  - "Add .gitattributes for consistent line endings (task-101)"
  - "Renormalize line endings to LF across repo"
