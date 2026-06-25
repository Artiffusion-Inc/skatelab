/**
 * Repro — `sb_auth` sentinel cookie set/clear DOMAIN MISMATCH → logout cannot
 * delete the SSR auth cookie, so the server-side gate keeps the user "logged in".
 *
 * The frontend `sb_auth=1` cookie gates SSR auth: `(app)/layout.tsx` reads
 * `cookies().get("sb_auth")` and `redirect()`s to /login if absent. The client
 * sets this sentinel on login/register and clears it on logout.
 *
 * Browser cookie semantics (RFC 6265): a cookie is uniquely identified by
 * (name, domain, path). A host-only cookie (no Domain= attribute) and a
 * domain-scoped cookie (Domain=<host>) are DIFFERENT cookies. To DELETE a
 * cookie, the deletion Set-Cookie must match (name, domain, path) of the one to
 * remove — otherwise the original survives.
 *
 * The source set/clear paths use INCONSISTENT `Domain` attributes:
 *
 *   - login   (src/components/auth-provider.tsx:73):
 *       `sb_auth=1; path=/; max-age=31536000; SameSite=Lax`
 *       → NO `Domain=` → host-only cookie.
 *   - register(src/components/auth-provider.tsx:90):  same host-only string.
 *   - clearTokens (src/lib/api-client.ts:38):
 *       `sb_auth=; path=/; max-age=0; Domain=skatelab.ru`
 *       → domain-scoped deletion.
 *   - setTokens   (src/lib/api-client.ts:32) / silentRefresh (src/lib/api-client.ts:52):
 *       `sb_auth=1; ...; Domain=skatelab.ru` → domain-scoped set.
 *
 * So:
 *   login/register create a HOST-ONLY `sb_auth`. logout (clearTokens) issues a
 *   DOMAIN-SCOPED deletion. They do not match → the host-only `sb_auth=1`
 *   SURVIVES logout. The SSR gate still sees `sb_auth` and renders the app as if
 *   authenticated; the client `user` is null → inconsistent logged-out-but-gated
 *   state. On localhost/preview, `Domain=skatelab.ru` is also rejected on SET
 *   (host mismatch), so clearTokens is a no-op and the host-only sentinel from
 *   login persists forever.
 *
 * Repro approach: the test asserts the EXACT cookie strings written by the real
 * source (quoted verbatim from auth-provider.tsx and api-client.ts) agree on the
 * Domain attribute. This is deterministic and independent of any cookie-jar
 * implementation (happy-dom/jsdom do not model host-only vs domain-scoped
 * correctly, so a runtime set/clear test is unreliable; the contract on the
 * literal strings IS the bug). RED now: the set string has no `Domain=`, the
 * clear string has `Domain=skatelab.ru` → they disagree. After the fix (both use
 * the same Domain attribute — or both host-only) → the Domain attributes match.
 *
 * NOTE: `api-client.ts` has a pre-existing zod v4 + vitest/oxc top-level
 * `z.unknown()` init issue that breaks importing the module in vitest, so the
 * cookie strings are quoted verbatim from the source instead of imported.
 */

import { describe, expect, it } from "vitest"

// Verbatim cookie strings from the source. Source citations in each constant.
const LOGIN_SET_COOKIE = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax" // auth-provider.tsx:73 (also :90 register)
const CLEAR_COOKIE = "sb_auth=; path=/; max-age=0; Domain=skatelab.ru" // api-client.ts:38 clearTokens()
const REFRESH_SET_COOKIE = "sb_auth=1; path=/; max-age=31536000; SameSite=Lax; Domain=skatelab.ru" // api-client.ts:32/:52

/** Extract the Domain attribute (lowercased) from a Set-Cookie string, or null if host-only. */
function domainOf(setCookie: string): string | null {
  const match = setCookie.match(/;\s*Domain=([^;]+)/i)
  return match ? match[1].trim().toLowerCase() : null
}

describe("sb_auth cookie set/clear domain mismatch (repro)", () => {
  it("login/register set and clearTokens use the SAME Domain attribute", () => {
    // CONTRACT: the cookie set on login must be deletable by clearTokens on
    // logout, which requires matching (name, domain, path). RED now: set is
    // host-only (null), clear is domain-scoped ("skatelab.ru") → mismatch →
    // logout cannot delete the sentinel. After the fix → both null or both
    // "skatelab.ru".
    expect(domainOf(LOGIN_SET_COOKIE)).toBe(domainOf(CLEAR_COOKIE))
  })

  it("silentRefresh set and clearTokens use the SAME Domain attribute", () => {
    // The refresh path (api-client.ts:32/:52) sets Domain=skatelab.ru, and
    // clearTokens deletes with Domain=skatelab.ru — these agree (contrast).
    // This proves the codebase ALREADY knows the correct pattern; login/register
    // just diverge from it.
    expect(domainOf(REFRESH_SET_COOKIE)).toBe(domainOf(CLEAR_COOKIE))
  })
})
