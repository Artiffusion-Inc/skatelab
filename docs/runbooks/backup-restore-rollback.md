# Backup, restore, and rollback

Status: required pilot operating procedure. The commands below are operator
examples only; they are not run by CI and they do not contain credentials.
Confirm the live container names, database major version, bucket, and retention
policy from the current deployment control plane before use.

## Recovery targets

The pilot needs backups for durable database records and private media. Valkey
contains queue state and is not the source of truth for completed sessions.

| Data | Minimum pilot policy | Recovery check |
| --- | --- | --- |
| PostgreSQL | Daily logical backup, plus one before a release or migration; retain encrypted copies off-host. | Restore into an isolated same-major PostgreSQL instance and run application read checks. |
| S3/RustFS objects | Daily incremental copy or provider snapshot; retain according to the approved privacy policy. | Restore a sample into an isolated bucket/prefix and verify object reads without exposing keys. |
| Valkey | Daily RDB snapshot only when operationally useful; queue contents are disposable. | Verify workers reconnect and reconcile durable task state; do not replay stale jobs by default. |
| Release metadata | Keep commit, image digest, migration result, artifact hashes, and smoke result with the release record. | Select a previously verified immutable release, never an untracked `latest` image. |

The pilot owner must record the actual backup location, last successful backup,
restore-drill date, retention owner, and RPO/RTO decisions in the private
operations record. This repository does not claim that an external schedule or
restore drill is already configured.

## Backup before a release or migration

Run on the approved host with a restricted backup destination. Set non-secret
connection variables through the host's secure environment or secret manager;
do not put values in this command or shell history.

```bash
set -euo pipefail
umask 077

backup_dir="/secure/backup-root/skatelab-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"

: "${POSTGRES_CONTAINER:?set the current Postgres container name out of band}"
: "${POSTGRES_USER:?set the database user out of band}"
: "${S3_ENDPOINT_URL:?set the S3 endpoint out of band}"
: "${S3_BUCKET:?set the S3 bucket out of band}"
: "${VALKEY_CONTAINER:?set the current Valkey container name out of band}"

# Logical dump; keep the uncompressed file only until gzip succeeds.
docker exec "$POSTGRES_CONTAINER" pg_dumpall --no-owner -U "$POSTGRES_USER" \
  > "$backup_dir/postgres.sql"
gzip -n "$backup_dir/postgres.sql"

# Valkey is auxiliary queue state. Wait for BGSAVE to complete before copying.
before="$(docker exec "$VALKEY_CONTAINER" valkey-cli LASTSAVE)"
docker exec "$VALKEY_CONTAINER" valkey-cli BGSAVE >/dev/null
for _ in $(seq 1 60); do
  after="$(docker exec "$VALKEY_CONTAINER" valkey-cli LASTSAVE)"
  if [[ "$after" -gt "$before" ]]; then
    break
  fi
  sleep 1
done
test "$after" -gt "$before"
docker cp "$VALKEY_CONTAINER:/data/dump.rdb" "$backup_dir/valkey.rdb"

# Copy private media while suppressing normal object names.
mkdir "$backup_dir/objects"
aws s3 sync "s3://$S3_BUCKET" "$backup_dir/objects" \
  --endpoint-url "$S3_ENDPOINT_URL" --only-show-errors --no-progress \
  > /dev/null 2> "$backup_dir/object-sync-errors.log"
test ! -s "$backup_dir/object-sync-errors.log"
rm -f "$backup_dir/object-sync-errors.log"

sha256sum "$backup_dir/postgres.sql.gz" "$backup_dir/valkey.rdb" \
  > "$backup_dir/SHA256SUMS"
printf '%s\n' 'backup_created=true'
```

The command deliberately prints only a completion marker. Keep the backup
directory encrypted and access-controlled; it contains private media and
potentially sensitive operational state. If object sync fails, keep the error
file private for troubleshooting and do not paste its contents into a ticket.

Validate the local database/queue backup before copying it off-host:

```bash
set -euo pipefail
backup_dir="${BACKUP_DIR:?set the backup directory through the secure operator environment}"
gzip -t "$backup_dir/postgres.sql.gz"
(cd "$backup_dir" && sha256sum -c SHA256SUMS >/dev/null)
printf '%s\n' 'backup_integrity=ok'
```

## Restore drill

Perform a restore drill in an isolated project or host at least before the pilot
go/no-go and after a major storage change. Never use the live production database
as the first restore target.

1. Confirm the backup checksum and PostgreSQL major version. Keep the original backup immutable.
2. Start an isolated PostgreSQL instance with an empty data directory and the approved test credentials. Do not place those credentials in this repository.
3. Restore the logical dump and stop immediately on SQL errors:

```bash
set -euo pipefail
backup_dir="${BACKUP_DIR:?set backup directory out of band}"
: "${RESTORE_POSTGRES_CONTAINER:?set isolated Postgres container out of band}"
: "${RESTORE_POSTGRES_USER:?set restore database user out of band}"
gzip -cd "$backup_dir/postgres.sql.gz" \
  | docker exec -i "$RESTORE_POSTGRES_CONTAINER" \
      psql --set ON_ERROR_STOP=1 -U "$RESTORE_POSTGRES_USER" -d postgres \
      >/dev/null
printf '%s\n' 'postgres_restore=ok'
```

4. Copy objects to an isolated bucket or prefix using the same S3-compatible endpoint settings. Run a dry run with output redirected to a restricted file, then apply only after the restore owner approves the target:

```bash
set -euo pipefail
backup_dir="${BACKUP_DIR:?set backup directory out of band}"
: "${RESTORE_S3_ENDPOINT_URL:?set isolated endpoint out of band}"
: "${RESTORE_S3_BUCKET:?set isolated bucket out of band}"
aws s3 sync "$backup_dir/objects" "s3://$RESTORE_S3_BUCKET" \
  --endpoint-url "$RESTORE_S3_ENDPOINT_URL" --dryrun \
  >/dev/null 2> "$backup_dir/object-restore-errors.log"
test ! -s "$backup_dir/object-restore-errors.log"
```

5. Verify a representative database read, an application health/read check, and an object read from the isolated target. Do not copy private response bodies into evidence.
6. Treat Valkey as disposable during a normal restore. Start an empty compatible instance and confirm workers reconnect/reconcile durable task state. Restore `valkey.rdb` only for a reviewed incident where preserving queue state is necessary; stop workers first and verify the application version before restoring it.
7. Record restore duration, backup identity, data counts or checksums, and pass/fail without recording emails, object keys, tokens, or media.

A successful restore drill is evidence that the procedure works in isolation; it
is not authorization to overwrite production.

## Production recovery

If production data is damaged or unavailable:

1. Declare the incident, pause pilot writes, and preserve the original volumes and backups.
2. Take a fresh backup of any readable current state before changing the target.
3. Prefer bringing up a replacement target and validating it over restoring in place.
4. Use the approved platform cutover control only after owner and privacy review. Do not run `docker compose down --remove-orphans`, delete volumes, or overwrite the live bucket as an experiment.
5. Run [Production smoke](production-smoke.md) and the affected pilot journey with disposable data.
6. Keep the original target read-only until the incident owner signs off on data completeness and recovery.

## Application rollback

Rollback the application image when the database schema remains compatible:

1. Stop the release pipeline and identify the last smoke-tested commit and immutable image digest from the private release record.
2. Select that exact digest in the approved Dokploy/release control plane. Do not select a moving `latest` tag and do not copy an image from an unverified workstation.
3. Roll back backend, worker, and frontend as one compatible release set. Keep migrations forward-compatible with both versions.
4. Run health, authenticated read, queue/task recovery, and privacy/ownership smoke checks.
5. Record the old and new release identities and the result without recording credentials or response bodies.

A schema migration is not automatically reversible. Do not run `alembic
downgrade` in production as a first response. If the failed release changed the
schema incompatibly, preserve data, restore to an isolated database, and obtain a
separate reviewed recovery plan before any controlled cutover.

## Rollback success criteria

- Health reports `ok`; authenticated reads return expected status codes.
- No duplicate task is created after client restart.
- Existing completed sessions remain readable and ownership checks still hold.
- Private objects are accessible only through the approved authenticated path.
- No P0/P1 data-integrity or privacy issue remains open.
