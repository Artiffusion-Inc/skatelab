import Image from "next/image"
import { notFound } from "next/navigation"
import { getTranslations } from "next-intl/server"
import { blog, getBlogPosts } from "@/lib/blog-source"
import { isLocale, LOCALES } from "@/lib/docs-i18n"
import { blogUrl, publicMetadata } from "@/lib/public-site"

type Props = { params: Promise<{ locale: string; slug: string }> }

export async function generateMetadata({ params }: Props) {
  const { locale, slug } = await params
  if (!isLocale(locale)) notFound()
  const post = blog.getPage([slug], locale)
  if (!post) notFound()
  const metadata = publicMetadata(
    post.data.title,
    post.data.description,
    post.url,
    locale,
    post.data.image,
  )
  return {
    ...metadata,
    alternates: {
      canonical: `https://skatelab.ru${post.url}`,
      languages: Object.fromEntries(
        LOCALES.filter(language => blog.getPage([slug], language)).map(language => [
          language,
          `https://skatelab.ru${blogUrl(language, [slug])}`,
        ]),
      ),
    },
    openGraph: { ...metadata.openGraph, type: "article", publishedTime: post.data.date },
  }
}

export default async function BlogArticle({ params }: Props) {
  const { locale, slug } = await params
  if (!isLocale(locale)) notFound()
  const post = blog.getPage([slug], locale)
  if (!post) notFound()
  const t = await getTranslations({ locale, namespace: "publicSite" })
  const l = await getTranslations({ locale, namespace: "landing" })
  const MDX = post.data.body
  const imageAlt =
    post.data.image === "recording-guide"
      ? t("recordingAlt")
      : post.data.image === "training-notes"
        ? t("notesAlt")
        : post.data.image === "blade-macro"
          ? l("bladeAlt")
          : l("coachImageAlt")
  return (
    <main id="main-content" tabIndex={-1} lang={locale}>
      <article>
        <header className="public-page-intro public-article-header">
          <a href={blogUrl(locale)} className="public-text-link">
            ← {t("backBlog")}
          </a>
          <h1>{post.data.title}</h1>
          <p>{post.data.description}</p>
          <p className="public-article-date">
            {t("published")}{" "}
            <time dateTime={post.data.date}>
              {new Intl.DateTimeFormat(locale, {
                day: "numeric",
                month: "long",
                year: "numeric",
                timeZone: "UTC",
              }).format(new Date(`${post.data.date}T00:00:00Z`))}
            </time>
          </p>
        </header>
        <div className="public-article-image">
          <Image
            src={`/images/landing/${post.data.image}.webp`}
            alt={imageAlt}
            fill
            sizes="(max-width: 1100px) 100vw, 1100px"
            className="landing-cover"
            priority
          />
        </div>
        <div className="public-article-layout">
          <div className="public-article-toc">
            <p className="public-eyebrow">{t("blogKicker")}</p>
            <nav aria-label={t("chapterReview")}>
              {post.data.toc.map(item => (
                <a key={item.url} href={item.url}>
                  {item.title}
                </a>
              ))}
            </nav>
          </div>
          <div className="public-prose">
            <MDX />
          </div>
        </div>
      </article>
      <section className="public-section public-related">
        <h2>{t("related")}</h2>
        {getBlogPosts(locale)
          .filter(item => item.url !== post.url && item.slugs[0] !== "2026-07-07-launch")
          .slice(0, 2)
          .map(item => (
            <a key={item.url} className="public-text-link" href={item.url}>
              {item.data.title} ↗
            </a>
          ))}
      </section>
    </main>
  )
}
