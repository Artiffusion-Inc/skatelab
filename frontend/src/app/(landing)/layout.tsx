import { ThemeProvider } from "next-themes"
import { headers } from "next/headers"
import type { ReactNode } from "react"

export default async function LandingLayout({ children }: { children: ReactNode }) {
  const nonce = (await headers()).get("x-nonce") ?? ""

  return (
    <ThemeProvider attribute="class" forcedTheme="light" disableTransitionOnChange nonce={nonce}>
      {children}
    </ThemeProvider>
  )
}
