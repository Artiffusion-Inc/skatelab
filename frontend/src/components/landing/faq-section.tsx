"use client"

import { useTranslations } from "@/i18n"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"

const FAQ_KEYS = [1, 2, 3, 4, 5, 6, 7] as const

export function FAQSection() {
  const t = useTranslations("landing")

  return (
    <section
      id="faq"
      tabIndex={-1}
      className="border-t border-hairline mx-auto max-w-5xl px-6 py-16 md:py-24"
      aria-labelledby="faq-heading"
    >
      <div className="lg:grid lg:grid-cols-[1fr_2fr] lg:gap-16">
        <div className="faq-header mb-10 md:mb-14 lg:mb-0">
          <p className="mb-4 sh-caption text-ink-mute">{t("faqEyebrow")}</p>
          <h2 id="faq-heading" className="sh-display-xl text-ink max-w-md">
            {t("faqTitle")}
          </h2>
        </div>

        <Accordion type="single" collapsible>
        {FAQ_KEYS.map(n => (
          <AccordionItem key={n} value={`faq-${n}`}>
            <AccordionTrigger className="min-h-[44px] py-3 text-left max-w-[65ch]">
              {t(`faqQ${n}`)}
            </AccordionTrigger>
            <AccordionContent className="sh-body-md text-ink-mute max-w-[65ch]">
              {t(`faqA${n}`)}
            </AccordionContent>
          </AccordionItem>
        ))}
        </Accordion>
      </div>
    </section>
  )
}
