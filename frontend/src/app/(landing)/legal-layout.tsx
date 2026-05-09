import Link from "next/link"

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-hairline px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <Link href="/" className="sh-display-md text-ink">
            SkateLab
          </Link>
          <Link href="/" className="sh-caption text-link hover:underline">
            На главную
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-8">
        {children}
      </main>
    </div>
  )
}
