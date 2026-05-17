"use client"

import Link from "next/link"
import { Camera } from "lucide-react"
import { useTranslations } from "@/i18n"

export function CenterFAB() {
  const t = useTranslations("nav")
  return (
    <Link
      href="/upload"
      aria-label={t("upload")}
      className="absolute left-1/2 -translate-x-1/2 -top-5 z-10 flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <Camera className="h-6 w-6" />
    </Link>
  )
}
