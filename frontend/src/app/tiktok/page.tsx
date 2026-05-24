import Link from "next/link"

const LINKS = [
  { href: "/register?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link", label: "Start free analysis" },
  { href: "/login?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link", label: "Login" },
  { href: "/?utm_source=tiktok&utm_medium=organic&utm_campaign=bio_link", label: "Learn more" },
]

export default function TikTokPage() {
  return (
    <div className="min-h-[dvh] bg-background flex flex-col items-center justify-center p-6">
      <h1 className="sh-display-lg text-ink mb-2">SkateLab</h1>
      <p className="sh-body-md text-ink-mute mb-8">AI coach for figure skating</p>
      <div className="w-full max-w-sm space-y-3">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="block w-full rounded-lg border border-hairline bg-canvas-soft px-6 py-4 text-center sh-body-md text-ink hover:bg-canvas transition-colors"
          >
            {link.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
