#!/usr/bin/env bash
# Test SSE streaming parity with Caddy flush_interval -1.
# Usage: ./test-sse-streaming.sh <url>
set -euo pipefail

URL="${1:?usage: test-sse-streaming.sh <url>}"
echo "Testing SSE streaming: $URL"

# Stream 5s, count lines. Real SSE emits >5 lines in 5s; buffered proxy returns 0-1.
CHUNKS=$(timeout 5 curl -N -s "$URL" 2>/dev/null | wc -l || echo 0)

if [[ "$CHUNKS" -gt 5 ]]; then
  echo "PASS: received $CHUNKS lines in 5s (streaming works)"
  exit 0
else
  echo "FAIL: only $CHUNKS lines (buffered, expected >5)"
  exit 1
fi