"use client"

import { useTranslations } from "@/i18n"

export function AccuracySection() {
  const t = useTranslations("landing")

  const videoMetrics = [
    { value: t("accuracyVideoValue1"), desc: t("accuracyVideoDesc1") },
    { value: t("accuracyVideoValue2"), desc: t("accuracyVideoDesc2") },
    { value: t("accuracyVideoValue3"), desc: t("accuracyVideoDesc3") },
  ]

  const imuMetrics = [
    { value: t("accuracyImuValue1"), desc: t("accuracyImuDesc1") },
    { value: t("accuracyImuValue2"), desc: t("accuracyImuDesc2") },
    { value: t("accuracyImuValue3"), desc: t("accuracyImuDesc3") },
  ]

  return (
    <section
      id="accuracy"
      tabIndex={-1}
      aria-label={t("accuracyTitle")}
      className="relative mx-auto max-w-5xl px-6 py-20 md:py-28"
    >
      <div className="mb-14 md:mb-20">
        <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
          {t("accuracyTitle")}
        </p>
        <h2 className="sh-display-xl text-ink">{t("accuracyHeadline")}</h2>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_1.4fr]">
        <div className="rounded-lg border border-hairline bg-background p-8">
          <p className="sh-micro uppercase tracking-[0.2em] text-ink-mute mb-6">
            {t("accuracyVideoLabel")}
          </p>
          <ul className="space-y-6">
            {videoMetrics.map((m, i) => (
              <li key={i} className="flex flex-col gap-1">
                <span className="sh-price text-ink-mute">{m.value}</span>
                <span className="sh-caption text-ink-mute">{m.desc}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg border border-primary bg-canvas-soft p-8">
          <p className="sh-micro uppercase tracking-[0.2em] text-primary mb-6">
            {t("accuracyImuLabel")}
          </p>
          <ul className="space-y-6">
            {imuMetrics.map((m, i) => (
              <li key={i} className="flex flex-col gap-1">
                <span className="sh-price text-primary">{m.value}</span>
                <span className="sh-caption text-ink-mute">{m.desc}</span>
              </li>
            ))}
          </ul>
          <p className="mt-8 sh-caption text-ink-mute border-t border-hairline pt-4">
            {t("accuracyBottomLine")}
          </p>
        </div>
      </div>
    </section>
  )
}
