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
      className="border-t border-hairline mx-auto max-w-3xl px-6 py-20 md:py-28"
      aria-labelledby="faq-heading"
    >
      <div className="faq-header mb-10">
        <p className="mb-4 sh-micro uppercase tracking-[0.3em] text-ink-mute">
          {t("faqTitle")}
        </p>
        <h2 id="faq-heading" className="sh-display-xl text-ink">
          {t("faqTitle")}
        </h2>
      </div>

      <Accordion type="single" collapsible>
        {FAQ_KEYS.map((n) => (
          <AccordionItem key={n} value={`faq-${n}`}>
            <AccordionTrigger className="min-h-[44px] py-3 text-left">
              {t(`faqQ${n}`)}
            </AccordionTrigger>
            <AccordionContent className="sh-body-md text-ink-mute">
              {t(`faqA${n}`)}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </section>
  )
}
