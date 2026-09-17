import { PUBLIC_ROUTES } from "@/lib/public-site"

const PUBLIC_PREFIXES = [
  ...PUBLIC_ROUTES,
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
    prefix => pathname === prefix || (prefix !== "/" && pathname.startsWith(`${prefix}/`)),
  )
}
