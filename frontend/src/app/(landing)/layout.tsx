import { ThemeProvider } from "next-themes"
import type { ReactNode } from "react"

export default function LandingLayout({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" forcedTheme="light" disableTransitionOnChange>
      {children}
    </ThemeProvider>
  )
}
