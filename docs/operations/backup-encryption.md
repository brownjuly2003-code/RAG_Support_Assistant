# Backup encryption at rest

Audience: operators / SREs maintaining `scripts/backup_snapshot.py`,
`scripts/restore_verify.py`, and the backup CronJob in `deploy/helm/`.

This document covers how snapshot components are encrypted on disk with `age`,
how to provision keys, and how to restore encrypted snapshots safely.

## Why `age`

The project uses [`age`](https://github.com/FiloSottile/age) for backup
encryption at rest.

Reasons:

- Single cross-platform binary for Linux, macOS, and Windows.
- Authenticated file format by default. Snapshot files are protected against
  both disclosure and silent tampering.
- Clean recipient mode: only the public key is deployed to the cluster, while
  the private key stays offline.
- Streaming CLI: large `pg_dump` and tarball artifacts do not need to be loaded
  into memory.

`openssl enc -aes-256-gcm` was rejected for this workflow. It can encrypt the
payload, but it does not give us the same operator-friendly file format or the
same simple recipient-based distribution model.

## What gets encrypted

When `BACKUP_ENCRYPTION_ENABLED=true`, `scripts/backup_snapshot.py` writes the
plaintext artifact first, then immediately re-encrypts it with `age`, writes
the encrypted file back into the snapshot directory, and deletes the plaintext.

Encrypted components:

- `postgres.dump.age`
- `traces.sqlite.age`
- `uploads.tar.gz.age`
- `chroma.tar.gz.age`

`snapshot_manifest.json` records:

- per-component `encrypted: true` and `algorithm: "age"`
- top-level `encryption.enabled`
- recipient or passphrase fingerprint, never the raw key material

The legacy `DB_ENCRYPTION_KEY` fingerprint file is still written separately.
That key protects selected Postgres columns. It is independent from the `age`
key used for snapshot files.

## Recommended mode: recipient key

Recipient mode is the production path.

Generate a key pair:

```bash
age-keygen -o age-backup-identity.txt
age-keygen -y age-backup-identity.txt > recipient.pub
```

Storage model:

- Keep `age-backup-identity.txt` offline in a vault or sealed recovery medium.
- Do not commit the private key to Git.
- Do not store the private key in the cluster.
- Only the public key (`recipient.pub`) is allowed in the cluster.

Local `.env` example:

```dotenv
BACKUP_ENCRYPTION_ENABLED=true
BACKUP_ENCRYPTION_RECIPIENT=age1...
```

File-based example:

```dotenv
BACKUP_ENCRYPTION_ENABLED=true
BACKUP_ENCRYPTION_RECIPIENT_FILE=/secrets/recipient.pub
```

Restore with the private key:

```bash
python scripts/restore_verify.py \
  --snapshot backups/20260423T010000Z/ \
  --age-identity-file ./age-backup-identity.txt
```

## Passphrase fallback

Passphrase mode exists only for dev / single-box recovery. Production should
prefer recipient mode.

Create a passphrase file:

```bash
mkdir -p .secrets
printf '%s\n' 'replace-with-a-long-random-passphrase' > .secrets/backup-passphrase.txt
chmod 600 .secrets/backup-passphrase.txt
```

Enable it:

```dotenv
BACKUP_ENCRYPTION_ENABLED=true
BACKUP_ENCRYPTION_PASSPHRASE_FILE=.secrets/backup-passphrase.txt
```

Restore:

```bash
python scripts/restore_verify.py \
  --snapshot backups/20260423T010000Z/ \
  --age-passphrase-file ./.secrets/backup-passphrase.txt
```

Notes:

- Non-interactive passphrase mode requires the bundled `age-plugin-batchpass`
  plugin. The official release archive includes it.
- If your distro package omits that plugin, use recipient mode instead.

## Kubernetes / Helm

The chart expects a Secret named `backup-encryption-key` with one file:
`recipient.pub`.

Create the Secret:

```bash
kubectl -n rag-support create secret generic backup-encryption-key \
  --from-file=recipient.pub=./recipient.pub
```

Enable encryption in the backup CronJob:

```bash
helm upgrade --install rag-support-assistant ./deploy/helm \
  --namespace rag-support \
  --set backup.encryption.enabled=true
```

The CronJob will then:

- mount `/secrets/recipient.pub`
- export `BACKUP_ENCRYPTION_ENABLED=true`
- export `BACKUP_ENCRYPTION_RECIPIENT_FILE=/secrets/recipient.pub`

If the Secret is not present while encryption is enabled, the backup job will
fail fast instead of writing plaintext artifacts.

## Rotation

Key rotation for existing snapshots is manual.

Rotation flow:

1. Generate a new `age` identity + recipient pair.
2. Update the cluster Secret with the new `recipient.pub`.
3. New snapshots will use the new public key.
4. Old snapshots remain decryptable only with the old private key until they
   are manually re-encrypted.

Manual re-encrypt cookbook for a single file:

```bash
age --decrypt -i ./old-identity.txt -o ./postgres.dump ./postgres.dump.age
age --encrypt -r "$(cat ./new-recipient.pub)" -o ./postgres.dump.age.new ./postgres.dump
mv ./postgres.dump.age.new ./postgres.dump.age
rm ./postgres.dump
```

Repeat per encrypted component. Verify with `scripts/backup_integrity.py` after
the replacement.

## Recovery runbook

### Snapshot leaked, private key safe

The tarball is still protected at rest. Treat this as an incident, but the
backup contents remain unreadable without the `age` private key or passphrase.

Recommended actions:

1. Confirm the leaked media did not include the private key or passphrase.
2. Rotate the public key for future snapshots.
3. Re-encrypt retained high-value snapshots if policy requires it.

### Cluster Secret lost, offline private key still available

This is recoverable.

1. Re-derive or recover `recipient.pub` from the offline identity:

```bash
age-keygen -y ./age-backup-identity.txt > recipient.pub
```

2. Recreate the Kubernetes Secret.
3. Re-run the backup CronJob.

### `age` private key or passphrase lost

This is a hard recovery blocker for encrypted snapshots.

- Existing `.age` files encrypted under that key cannot be restored.
- `DB_ENCRYPTION_KEY` does not help here; it is a separate control plane.
- Treat the loss as a disaster-recovery incident and document which snapshots
  became unrecoverable.

## Operational checklist

- Keep the `age` private key offline, outside the cluster and outside the
  backup storage location.
- Keep at least two recovery paths for the private key or passphrase.
- Never log the recipient, private key, or passphrase. Log only fingerprints.
- Test `scripts/restore_verify.py --age-identity-file ...` regularly against
  the newest encrypted snapshot.
- Prefer recipient mode in all shared or production environments.
