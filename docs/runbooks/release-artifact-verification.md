# Release artifact verification

Status: required check for a distributable Android pilot release. The GitHub
workflow is `.github/workflows/android-release.yml`; it builds a signed APK and
AAB, verifies both, writes SHA-256 checksums, and uploads a small artifact bundle.
No signing values belong in this document or in workflow logs.

## Workflow gate

Before starting a release, confirm the protected `android-release` environment has
these names configured externally:

- `SKATELAB_RELEASE_KEYSTORE_BASE64`
- `SKATELAB_KEYSTORE_PASSWORD`
- `SKATELAB_KEY_ALIAS`
- `SKATELAB_KEY_PASSWORD`

The workflow must fail closed if any value is absent. Never add a fallback key,
print environment variables, enable shell tracing, or download a keystore into a
repository path. The workflow's checksum/verification manifest contains release
metadata only, not credentials.

## Download a completed bundle

Use a clean operator directory and the exact successful workflow run. Set
`RELEASE_RUN_ID`, `RELEASE_REF`, and `GITHUB_REPOSITORY` through normal non-secret
shell variables; do not set a token on the command line. Run the download and
verification snippets in the same shell session; the temporary directory is
removed when that session exits.

```bash
set -euo pipefail

: "${RELEASE_RUN_ID:?set the successful Android Release run ID}"
: "${RELEASE_REF:?set the release tag or ref name}"
: "${GITHUB_REPOSITORY:?set owner/repository, or use gh's current repository}"
artifact_dir="$(mktemp -d)"
trap 'rm -rf "$artifact_dir"' EXIT
chmod 700 "$artifact_dir"

gh run download "$RELEASE_RUN_ID" \
  --repo "$GITHUB_REPOSITORY" \
  --name "skatelab-android-$RELEASE_REF" \
  --dir "$artifact_dir"

for file in androidApp-release.apk androidApp-release.aab release-sha256.txt release-verification.txt; do
  test -s "$artifact_dir/$file"
done
test "$(find "$artifact_dir" -maxdepth 1 -type f | wc -l)" -eq 4
printf '%s\n' 'artifact_bundle=complete'
```

Download before the workflow's configured retention period expires. Treat the
bundle as distributable software; keep it in an approved access-controlled
location and remove temporary copies after verification.

## Verify checksums and signatures

Run these commands from the clean directory. They print pass markers and do not
print artifact contents or signing credentials.

```bash
set -euo pipefail

: "${artifact_dir:?set artifact_dir from the previous step}"
(
  cd "$artifact_dir"
  sha256sum -c release-sha256.txt >/dev/null
  unzip -tq androidApp-release.apk >/dev/null
  unzip -tq androidApp-release.aab >/dev/null
)

apksigner="$(find "${ANDROID_HOME:?}/build-tools" -type f -name apksigner | sort -V | tail -n 1)"
test -x "$apksigner"
"$apksigner" verify "$artifact_dir/androidApp-release.apk" >/dev/null
jarsigner -verify "$artifact_dir/androidApp-release.aab" >/dev/null 2>&1

printf '%s\n' 'checksums=ok' 'apk_signature=ok' 'aab_signature=ok' 'archives=ok'
```

If `sha256sum -c`, `apksigner`, `jarsigner`, or archive verification fails, do
not distribute the bundle. Download the exact run again before investigating;
never replace one file with a local build. The APK package ID must remain
`ru.skatelab.capture`; use the Android SDK's `apkanalyzer` or `aapt2` locally to
check it without uploading the output:

```bash
apkanalyzer manifest application-id "$artifact_dir/androidApp-release.apk"
```

The expected output is `ru.skatelab.capture`. If `apkanalyzer` is not on `PATH`,
locate the SDK tool without printing environment contents and run the equivalent
read-only command.

## Release identity record

Compare `release-verification.txt` with the GitHub run and tag. Record the commit,
ref, APK/AAB SHA-256 values, signature result, verifier date, and reviewer in the
private release record. Do not record the keystore alias, password, token, local
absolute paths, signed URLs, or response bodies.

```text
Release ref:
Release commit:
GitHub run ID:
APK SHA-256:
AAB SHA-256:
APK signature: PASS / FAIL
AAB signature: PASS / FAIL
APK package ID: PASS / FAIL
Reviewer/date (UTC):
```

## Device smoke and update safety

After artifact verification, install only on an approved test device or the
containerized emulator. Follow [Android release smoke](android-release-smoke.md)
and record the device/API image and build version. Do not use host ADB while the
containerized emulator is active.

For an update test, install the previous pilot release first and then install the
new APK with explicit operator approval. If Android reports a signing mismatch,
stop; do not uninstall a user build or generate a replacement key as a workaround.
An uninstall destroys the update-path evidence and may remove local queued data.

## Failure and rollback

- A missing artifact, hash mismatch, unsigned file, package mismatch, or failed archive test is a release blocker.
- A successful build is not a successful release until signatures, hashes, package identity, and approved device smoke pass.
- If a released build is unhealthy, stop distribution and select the last verified immutable release identity from the private release record. Do not roll back by selecting a moving `latest` tag.
- Run [Production smoke](production-smoke.md) after the application rollback and use [Backup, restore, and rollback](backup-restore-rollback.md) for data recovery. Do not downgrade the production database as an artifact rollback step.
