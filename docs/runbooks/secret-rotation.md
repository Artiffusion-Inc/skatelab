# Secret rotation checklist

Status: external-secret procedure for the pilot. Values are never stored in this
repository, printed by a command, or written to CI summaries and artifacts. This
document lists names and ownership only.

## Rotation triggers

- Rotate immediately after suspected disclosure, accidental logging, staff/access change, or provider compromise.
- Rotate before pilot go/no-go when a secret's owner or last-rotated date is unknown.
- Keep the actual value, owner, creation date, expiry date, and revocation record in the approved secret manager.
- Use separate credentials for local, staging, production, and CI. Do not copy a production value into a local `.env` or test fixture.

## Inventory

Confirm each name against the current environment and workflow before changing it.
The list below intentionally contains no values.

| Surface | Secret names or classes | Rotation note |
| --- | --- | --- |
| Application auth | `JWT_SECRET_KEY` | Plan for active access tokens to become invalid. Verify refresh/session recovery before revoking the old value. |
| PostgreSQL | `POSTGRES_PASSWORD`, the password embedded in `DATABASE_URL` | Changing the container environment alone does not change an existing database role. Change the role and connection setting as one controlled operation. |
| S3/RustFS | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and any provider-side root/admin credential | Use an overlapping key window; update all readers/writers before revoking the old key. |
| GPU and email providers | `VASTAI_API_KEY`, `RESEND_API_KEY` | Create and test the replacement at the provider, then update runtime configuration. |
| TLS/DNS and AI gateways | Cloudflare DNS credential, `NINEROUTER_API_KEY`, and other provider tokens in the deployment environment | Scope each token to the required zones/service and remove unused permissions. |
| Dokploy and host access | `DOKPLOY_API_KEY`, `VPS_SSH_KEY`, `VPS_USER`, and any control-plane credential | Maintain a second verified access path before revoking the old key. `DOKPLOY_COMPOSE_ID` is an identifier, not a secret, but keep it in the environment configuration. |
| GitHub Actions | `GITGUARDIAN_API_KEY`, `CODECOV_TOKEN`, `GRADLE_CACHE_ENCRYPTION_KEY`, and provider credentials used by workflows | Rotate in the repository/environment secret store only; never use a command that puts a value in shell history. |
| Android release | `SKATELAB_RELEASE_KEYSTORE_BASE64`, `SKATELAB_KEYSTORE_PASSWORD`, `SKATELAB_KEY_ALIAS`, `SKATELAB_KEY_PASSWORD` | The keystore is the app signing identity. Do not replace it casually: a new key can prevent updates to an installed pilot app. |
| Mobile E2E | The dedicated test account values used by `MAESTRO_TEST_EMAIL`, `MAESTRO_TEST_PASSWORD`, and `MAESTRO_TEST_DISPLAY_NAME` | Keep these in the appropriate protected environment and use disposable data only. |

Also review any provider or host secret not represented in `.env.example`,
Dokploy's environment, or `.github/workflows/`. The inventory is complete only
when every consumer and owner is recorded privately.

## Planned rotation

1. Announce a maintenance window and identify the affected consumer, owner, rollback value, and expected token/session impact.
2. Take the required database/object backup and confirm the last successful backup before changing a data-plane credential.
3. Create a replacement credential with least privilege and a short overlap window. Do not print it or save it in a repository file.
4. Store it in the approved secret manager/GitHub environment. Use protected CI input or the platform UI; never pass it as a literal `--body`, command argument, or log value.
5. Update all consumers atomically where possible. For database credentials, change the database role password and the application connection setting together; verify existing connections drain/reconnect.
6. Have the authorized release owner apply the runtime configuration change. This checklist does not perform or authorize a deployment.
7. Run [Production smoke](production-smoke.md) and a disposable pilot check. Inspect logs and CI summaries for redaction without opening secret values.
8. Revoke the old credential after the smoke passes. Confirm old access fails from a controlled check that does not expose the credential.
9. Record secret class, owner, rotation timestamp, consumer checks, and revocation result. Never record the value, a password hash, a token prefix, or a signed URL.

## Special cases

### JWT signing key

Rotate only with an explicit session-impact decision. Existing access tokens
should be treated as invalid after the key change; verify the documented refresh
and logout behavior and be ready to ask users to authenticate again through the
normal flow. Do not invalidate or delete user data as part of key rotation.

### PostgreSQL password

A `POSTGRES_PASSWORD` environment update is commonly used only when the database
is initialized; it does not necessarily change the password of an existing role.
Use the approved database administration path to change the role password, update
the application's `DATABASE_URL`, restart/reconnect consumers in a controlled
window, and run the smoke before revoking the prior credential. Keep the old
connection setting available only in the secure rollback record, not in source.

### S3/RustFS credentials

Create a second access key with only the required bucket permissions. Update the
backend, worker, CI model/build job, and any backup job that uses the old key.
Test a private object health/read operation without printing object keys or signed
URLs, then revoke the old key. If a key may have been used to read private media,
treat the event as a P0 privacy incident and preserve audit evidence.

### Android signing key

The release keystore is not an ordinary API token. Preserve an encrypted,
access-controlled backup and verify the SHA-256 certificate fingerprint privately
before release. If the key is exposed, stop distribution and follow the Android
publishing/key-upgrade process; do not generate a replacement locally and assume
installed pilot builds can update.

### CI and host credentials

Rotate GitHub environment secrets and host/control-plane credentials through their
native interfaces. After rotation, run a non-deploying workflow validation where
available, then have the release owner run the relevant smoke. Do not echo values,
use shell tracing, include environment dumps, or upload temporary key files.

## Suspected exposure

1. Stop use of the exposed credential and restrict affected reads/writes.
2. Revoke or disable it at the provider first when possible.
3. Rotate every consumer and related credential that could have been derived from it.
4. Invalidate affected sessions or signed URLs according to the service policy.
5. Search CI logs, artifacts, issues, temporary files, and operator history for exposure, without copying the value into a ticket.
6. Run smoke and ownership/privacy checks, then record the incident without the value or a reversible representation.
