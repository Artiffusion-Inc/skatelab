const PUBLIC_PREFIXES = [
  "/",
  "/login",
  "/register",
  "/privacy",
  "/terms",
  "/cookies",
  "/offer",
  "/verify-email",
  "/resend-verification",
]

export function isPublicPage(pathname: string): boolean {
  return PUBLIC_PREFIXES.some(
    prefix => pathname === prefix || (prefix !== "/" && pathname.startsWith(prefix)),
  )
}
