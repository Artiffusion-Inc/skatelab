import Image from "next/image"
import { notFound } from "next/navigation"
import { getTranslations } from "next-intl/server"
import { isLocale } from "@/lib/docs-i18n"
import { getBlogPosts } from "@/lib/blog-source"
import { blogUrl, publicMetadata } from "@/lib/public-site"
import { ContactClose } from "@/components/landing/public-shell"

type Props = { params: Promise<{ locale: string }> }
export async function generateMetadata({ params }: Props) {
  const { locale } = await params
  if (!isLocale(locale)) notFound()
  const t = await getTranslations({ locale, namespace: "publicSite" })
  return {
    ...publicMetadata(t("blogTitle"), t("blogIntro"), blogUrl(locale), locale, "recording-guide"),
    alternates: {
      canonical: `https://skatelab.ru${blogUrl(locale)}`,
      languages: { ru: "https://skatelab.ru/blog/ru", en: "https://skatelab.ru/blog/en" },
    },
  }
}

export default async function BlogIndex({ params }: Props) {
  const { locale } = await params
  if (!isLocale(locale)) notFound()
  const t = await getTranslations({ locale, namespace: "publicSite" })
  const posts = getBlogPosts(locale)
  const lead = posts.find(post => post.slugs[0] === "recording-guide") ?? posts[0]
  return (
    <main id="main-content" tabIndex={-1}>
      <section className="public-page-intro">
        <p className="public-eyebrow">{t("blogKicker")}</p>
        <h1>{t("blogTitle")}</h1>
        <p>{t("blogIntro")}</p>
      </section>
      <section className="public-section public-blog-lead">
        <a href={lead.url} className="public-editorial-image">
          <Image
            src={`/images/landing/${lead.data.image}.webp`}
            alt={t("recordingAlt")}
            fill
            sizes="(max-width: 800px) 100vw, 60vw"
            className="landing-cover"
            priority
          />
        </a>
        <div>
          <p className="public-eyebrow">01 / {t("chapterCapture")}</p>
          <h2>
            <a href={lead.url}>{lead.data.title}</a>
          </h2>
          <p>{lead.data.description}</p>
          <a href={lead.url} className="public-text-link">
            {t("readMore")} ↗
          </a>
        </div>
      </section>
      <section className="public-section public-blog-list" aria-label={t("allArticles")}>
        {posts
          .filter(post => post !== lead)
          .map((post, index) => (
            <article key={post.url}>
              <span className="public-eyebrow">0{index + 2}</span>
              <div>
                <h2>
                  <a href={post.url}>{post.data.title}</a>
                </h2>
                <p>{post.data.description}</p>
              </div>
              <a
                href={post.url}
                className="public-text-link"
                aria-label={`${t("readMore")}: ${post.data.title}`}
              >
                ↗
              </a>
            </article>
          ))}
      </section>
      <ContactClose />
    </main>
  )
}
