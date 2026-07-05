#!/usr/bin/env bash
# Incremental sync old RustFS bucket → new Dokploy RustFS bucket.
# Runs nightly via cron until Phase 3 cutover. BLOCKER #3 fix.
#
# Env required:
#   OLD_S3_ENDPOINT_URL, OLD_S3_BUCKET, OLD_S3_ACCESS_KEY_ID, OLD_S3_SECRET_ACCESS_KEY
#   NEW_S3_ENDPOINT_URL, NEW_S3_BUCKET, NEW_S3_ACCESS_KEY_ID, NEW_S3_SECRET_ACCESS_KEY
set -euo pipefail

: "${OLD_S3_ENDPOINT_URL:?required}"
: "${OLD_S3_BUCKET:?required}"
: "${OLD_S3_ACCESS_KEY_ID:?required}"
: "${OLD_S3_SECRET_ACCESS_KEY:?required}"
: "${NEW_S3_ENDPOINT_URL:?required}"
: "${NEW_S3_BUCKET:?required}"
: "${NEW_S3_ACCESS_KEY_ID:?required}"
: "${NEW_S3_SECRET_ACCESS_KEY:?required}"

LOG="/var/log/rustfs-sync.log"

echo "[$(date)] Starting RustFS sync: $OLD_S3_BUCKET → $NEW_S3_BUCKET" | tee -a "$LOG"

OLD_FLAGS=(--endpoint-url "$OLD_S3_ENDPOINT_URL" --region us-east-1)
NEW_FLAGS=(--endpoint-url "$NEW_S3_ENDPOINT_URL" --region us-east-1)

export AWS_ACCESS_KEY_ID="$OLD_S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$OLD_S3_SECRET_ACCESS_KEY"
aws s3 sync "s3://$OLD_S3_BUCKET" "/tmp/rustfs-sync-stage" \
  --no-sign-request "${OLD_FLAGS[@]}" --quiet 2>&1 | tee -a "$LOG" || true

export AWS_ACCESS_KEY_ID="$NEW_S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$NEW_S3_SECRET_ACCESS_KEY"
aws s3 sync "/tmp/rustfs-sync-stage" "s3://$NEW_S3_BUCKET" \
  --no-sign-request "${NEW_FLAGS[@]}" --quiet 2>&1 | tee -a "$LOG" || true

rm -rf /tmp/rustfs-sync-stage

# Verify counts
export AWS_ACCESS_KEY_ID="$OLD_S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$OLD_S3_SECRET_ACCESS_KEY"
OLD_COUNT=$(aws s3 ls "s3://$OLD_S3_BUCKET" "${OLD_FLAGS[@]}" --recursive 2>/dev/null | wc -l)
export AWS_ACCESS_KEY_ID="$NEW_S3_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$NEW_S3_SECRET_ACCESS_KEY"
NEW_COUNT=$(aws s3 ls "s3://$NEW_S3_BUCKET" "${NEW_FLAGS[@]}" --recursive 2>/dev/null | wc -l)

echo "[$(date)] Sync done: $OLD_COUNT old, $NEW_COUNT new objects" | tee -a "$LOG"
[[ $OLD_COUNT -ne $NEW_COUNT ]] && echo "WARN: count mismatch" | tee -a "$LOG"