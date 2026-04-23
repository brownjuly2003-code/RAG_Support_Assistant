# Task 175 — Backup encryption at rest

## Goal
Snapshot-файлы (`postgres.dump`, `uploads.tar.gz`, `chroma.tar.gz`), которые пишет `scripts/backup_snapshot.py`, должны лежать на диске зашифрованными. Сейчас они plaintext: украденный backup-tarball полностью восстанавливается через `pg_restore` без знания `DB_ENCRYPTION_KEY` (pgcrypto шифрует только отдельные колонки — email/token из миграции 008; traces/messages/feedback/KB-drafts/chunks в dump лежат открыто). DR scenario E (`DB_ENCRYPTION_KEY lost`) это отражает, но не автоматизирует защиту от утечки самих snapshot-файлов.

## Context
- `scripts/backup_snapshot.py`:
  - делает `pg_dump -Fc` → `<snapshot>/postgres.dump`.
  - SQLite backup API → `<snapshot>/traces.sqlite`.
  - `tarfile.open(..., "w:gz")` для `data/uploads` и ChromaDB.
  - пишет `snapshot_manifest.json` с SHA256/size per-component + `encryption_key_fingerprint` (только SHA256 от `DB_ENCRYPTION_KEY`, сам ключ не сохраняется).
  - **нигде не шифрует полученные файлы**.
- `scripts/restore_verify.py` читает tarballs и postgres.dump **напрямую** — если перейти на encrypted-on-disk, этот путь тоже надо обновить.
- `scripts/backup_integrity.py` считает SHA256 по написанным файлам для retention/integrity audit.
- DR checklist (`docs/disaster-recovery.md`) рекомендует offsite копии и offline vault для `DB_ENCRYPTION_KEY`, но никак не про symmetric/asymmetric encryption самих snapshot-файлов.
- Helm cronjob `cronjob-backup-snapshot.yaml` ничего не знает о новых secrets, только монтирует `BACKUP_DIR`.
- Окружения: Linux (CI/k8s) + Windows (dev). Решение должно работать без GPG-специфики и без зависимости от системного keyring.

## Deliverables
- Выбор primitive: **`age`** (https://github.com/FiloSottile/age) — modern, single binary, Windows/Linux/Mac, symmetric passphrase или X25519 recipient key. Обоснование в `docs/operations/backup-encryption.md`. Альтернатива `openssl enc -aes-256-gcm` приемлема, но она не MAC'ит файл и не имеет header'а — не брать.
- `scripts/backup_snapshot.py` расширить:
  - новый env `BACKUP_ENCRYPTION_ENABLED=false` (default off, fail-safe).
  - `BACKUP_ENCRYPTION_RECIPIENT` (X25519 public key, `age1...`) **или** `BACKUP_ENCRYPTION_PASSPHRASE_FILE` (путь к файлу с passphrase; файл имеет mode 0600).
  - при `BACKUP_ENCRYPTION_ENABLED=true` ровно один из recipient/passphrase должен быть задан, иначе fail-fast.
  - поток: для каждого компонента (`postgres.dump`, `traces.sqlite`, `uploads.tar.gz`, `chroma.tar.gz`) после записи plaintext → `age --encrypt -r <recipient>` (или `-p -i <passphrase-file>`) → записать `<name>.age` → удалить plaintext.
  - `snapshot_manifest.json` получает два новых поля на компонент: `"encrypted": true`, `"algorithm": "age"`. Также top-level `"encryption": {"enabled": true, "recipient_fingerprint": "<sha256 of recipient public key>"}`. Fingerprint — не сам ключ.
  - Backward-compat: при `BACKUP_ENCRYPTION_ENABLED=false` поведение неизменно, `encrypted: false` в манифесте.
- `scripts/restore_verify.py` (и downstream `restore_verify_integration.py`):
  - новый arg `--age-identity-file <path>` (приватный X25519 key для recipient-mode) или `--age-passphrase-file <path>`.
  - при компоненте с `"encrypted": true` в manifest — сначала `age --decrypt` в `tmp_path`, потом существующий restore path.
  - exit code `EXIT_DECRYPT_FAILED=5` (новый).
  - backward-compat: старые un-encrypted snapshots читаются без identity.
- `scripts/backup_integrity.py`:
  - в `"encrypted": true` случае SHA256 считается по encrypted файлу (это то, что лежит на диске).
  - в report добавить колонку/поле `encrypted`.
- `deploy/helm/templates/cronjob-backup-snapshot.yaml`:
  - дополнительный `volumeMount` на secret `backup-encryption-key` (файл `/secrets/recipient.pub`), gated по `.Values.backup.encryption.enabled`.
  - env var `BACKUP_ENCRYPTION_ENABLED={{ .Values.backup.encryption.enabled }}`, `BACKUP_ENCRYPTION_RECIPIENT_FILE=/secrets/recipient.pub`.
  - `deploy/helm/values.yaml`: `backup.encryption.enabled: false` (default off).
- Документация:
  - `docs/operations/backup-encryption.md` — полное покрытие: как сгенерировать `age-keygen` identity (private + public), где хранить private key (offline vault, **не** в cluster), пример `.env`, пример `helm upgrade --set backup.encryption.enabled=true --set-file backup.encryption.recipientPub=./recipient.pub`, rotation story (re-encrypt старые снапшоты при смене ключа), recovery runbook (чем расшифровать если k8s secret потерян).
  - `docs/disaster-recovery.md` — новый scenario F "backup tarball leaked" с mitigation = age encryption gate.
  - `docs/CHANGELOG.md` запись.
- Тесты:
  - `tests/test_backup_snapshot_encryption.py` — end-to-end: tmp dir → snapshot с `BACKUP_ENCRYPTION_ENABLED=true` и тестовым recipient → файлы `*.age` существуют, plaintext отсутствует, manifest отражает encrypted.
  - `tests/test_restore_verify_encryption.py` — encrypted snapshot → restore с identity → exit 0; wrong identity → exit 5.
  - `tests/test_backup_snapshot_encryption.py` и restore-тест skipped если `shutil.which("age")` is None (не падать, а skip).

## Acceptance criteria
- [ ] `BACKUP_ENCRYPTION_ENABLED=true BACKUP_ENCRYPTION_RECIPIENT=age1... python scripts/backup_snapshot.py --output-dir <tmp>` создаёт `<ts>/postgres.dump.age`, `<ts>/traces.sqlite.age`, `<ts>/uploads.tar.gz.age`, `<ts>/chroma.tar.gz.age`; никаких plaintext-файлов в snapshot; `snapshot_manifest.json` содержит `"encryption.enabled": true` и per-component `"encrypted": true`.
- [ ] `python scripts/restore_verify.py --snapshot <tmp>/<ts>/ --age-identity-file ./identity.key` → exit 0. Без `--age-identity-file` при encrypted snapshot → exit 5 с понятным stderr.
- [ ] `BACKUP_ENCRYPTION_ENABLED=false` (default) — behaviour без регрессий: все существующие тесты `test_backup_snapshot*.py`, `test_restore_verify*.py` зелёные.
- [ ] `scripts/backup_integrity.py` на encrypted snapshot возвращает Valid; SHA считается по `.age` файлу.
- [ ] `ruff check scripts/ tests/` clean.
- [ ] `helm lint deploy/helm/ --strict` clean, `helm template` с `backup.encryption.enabled=true` рендерит CronJob с mount'ом `/secrets/recipient.pub`; с `enabled=false` mount отсутствует (clean diff).
- [ ] `docs/operations/backup-encryption.md` и обновлённый DR checklist landed; `docs/CHANGELOG.md` entry есть.

## Notes
- Не требовать `age` в runtime-зависимостях Python (нет хорошего pure-python аналога с identical cli compat). Вызов через `subprocess.run(["age", ...])`; в CI image install `age` через `apt-get install -y age` (Ubuntu 23.04+) или precompiled release tarball.
- Fingerprint от recipient-ключа — `sha256(age_public_key_bytes)` hex, не сам ключ. Это защита от человеческой ошибки «забыл каким ключом шифровал», при этом не раскрывает ничего.
- НЕ коммитить фиктивные identity/recipient keys в репо. Тесты должны генерировать пары на лету (`age-keygen -o <tmp>/id.key`).
- Streaming encryption: `age` работает поточно (`age --encrypt -r ... < in > out`). Для больших tarballs это важно — не load'ить весь файл в память.
- Passphrase-mode добавлен как fallback для dev/single-box; в production-runbook main path — recipient-mode (public key deploy'ится в cluster, private хранится offline).
- Key rotation: out-of-scope для этой таски (отдельная отсылка в docs). Re-encrypt старых снапшотов — ручной cookbook, не автоматизация.
- Ни в коем случае НЕ логировать ключи/passphrase — только fingerprints.
- Не ломать DR scenario E: если `DB_ENCRYPTION_KEY` потерян, snapshot всё ещё `pg_restore`-абельный (pgcrypto колонки останутся unreadable, это known). Новый age-ключ — отдельная ось: scenario F = "age private key lost" → snapshot irrecoverable. Это надо явно задокументировать.
