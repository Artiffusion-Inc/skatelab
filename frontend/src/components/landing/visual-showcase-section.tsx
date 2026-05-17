"use client"

import { useTranslations } from "@/i18n"
import Image from "next/image"
import { Film, LayoutDashboard, Box } from "lucide-react"

const icons = [Film, LayoutDashboard, Box]

const VISUAL_IMAGES = [
  { src: "/images/moodboard/visual-video.webp", alt: "" },
  { src: "/images/moodboard/visual-dashboard.webp", alt: "" },
  { src: "/images/moodboard/arena-empty.webp", alt: "" },
]

export function VisualShowcaseSection() {
  const t = useTranslations("landing")

  const visuals = [
    { label: t("visualVideoLabel"), desc: t("visualVideoDesc") },
    { label: t("visualDashboardLabel"), desc: t("visualDashboardDesc") },
    { label: t("visual3dLabel"), desc: t("visual3dDesc") },
  ]

  return (
    <section
      id="visual"
      tabIndex={-1}
      aria-label={t("visualTitle")}
      className="relative mx-auto max-w-5xl px-6 py-16 md:py-24"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-caption text-ink-mute">{t("visualTitle")}</p>
        <h2 className="sh-display-xl text-ink max-w-[65ch]">{t("visualHeadline")}</h2>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {visuals.map((v, i) => {
          const Icon = icons[i]
          const img = VISUAL_IMAGES[i]
          const isWide = i === 0
          return (
            <div
              key={v.label}
              className={`visual-card group relative overflow-hidden rounded-lg border border-hairline bg-background ${
                isWide ? "md:col-span-2" : ""
              }`}
            >
              <div className={`relative ${isWide ? "aspect-[21/9]" : "aspect-video"}`}>
                <Image
                  src={img.src}
                  alt={img.alt}
                  fill
                  sizes="(max-width: 768px) 100vw, 50vw"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              </div>
              <div className="p-6">
                <h3 className="sh-heading-lg text-ink mb-1 flex items-center gap-2">
                  <Icon className="h-5 w-5 text-primary" />
                  {v.label}
                </h3>
                <p className="sh-caption text-ink-mute max-w-[65ch]">{v.desc}</p>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
