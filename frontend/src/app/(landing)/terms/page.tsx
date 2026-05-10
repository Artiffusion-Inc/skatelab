import type { Metadata } from "next"
import Link from "next/link"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Пользовательское соглашение — SkateLab",
}

export default function TermsPage() {
  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">
          Главная
        </a>
        {" > "}
        <span>Правовая информация</span>
        {" > "}
        <span>Пользовательское соглашение</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">Пользовательское соглашение</h1>
      <p className="sh-body-lg text-ink-mute">Документ готовится.</p>
      <p className="mt-4">
        <Link href="/" className="sh-button-cap text-link hover:underline">
          На главную →
        </Link>
      </p>
    </LegalLayout>
  )
}
