import type { Metadata } from "next"
import LegalLayout from "../legal-layout"

export const metadata: Metadata = {
  title: "Cookie Policy — SkateLab",
}

export default function CookiesPage() {
  return (
    <LegalLayout>
      <nav className="mb-6 sh-caption text-ink-mute">
        <a href="/" className="hover:text-ink">
          Главная
        </a>
        {" > "}
        <span>Правовая информация</span>
        {" > "}
        <span>Cookie Policy</span>
      </nav>
      <h1 className="sh-display-lg text-ink mb-8">Cookie Policy</h1>
      <div className="space-y-6 sh-body-md text-ink-mute">
        <h2 className="sh-heading-lg text-ink">Что такое cookies</h2>
        <p>
          Cookies — небольшие текстовые файлы, которые хранятся на вашем устройстве при посещении
          сайта.
        </p>
        <h2 className="sh-heading-lg text-ink">Какие cookies мы используем</h2>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-hairline">
              <th className="py-2 pr-4 sh-button-cap text-ink">Cookie</th>
              <th className="py-2 pr-4 sh-button-cap text-ink">Категория</th>
              <th className="py-2 pr-4 sh-button-cap text-ink">Назначение</th>
              <th className="py-2 sh-button-cap text-ink">Срок</th>
            </tr>
          </thead>
            <tbody>
              {/* Essential */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>sb_auth</code></td>
                <td className="py-2 pr-4">Необходимые</td>
                <td className="py-2 pr-4">Идентификация авторизованного пользователя</td>
                <td className="py-2">Сессия</td>
              </tr>
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>skatelab_consent</code></td>
                <td className="py-2 pr-4">Необходимые</td>
                <td className="py-2 pr-4">Хранение настроек согласия на cookies</td>
                <td className="py-2">1 год</td>
              </tr>
              {/* Analytics */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>ph_*</code></td>
                <td className="py-2 pr-4">Аналитические (opt-in)</td>
                <td className="py-2 pr-4">PostHog — просмотр страниц, события, воронки</td>
                <td className="py-2">13 месяцев</td>
              </tr>
              {/* Feature flags (essential) */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>$ph_feat</code></td>
                <td className="py-2 pr-4">Необходимые</td>
                <td className="py-2 pr-4">PostHog feature flags — определяют функциональность приложения</td>
                <td className="py-2">13 месяцев</td>
              </tr>
              {/* Recordings */}
              <tr className="border-b border-hairline">
                <td className="py-2 pr-4"><code>ph_rec*</code></td>
                <td className="py-2 pr-4">Записи сессий (opt-in)</td>
                <td className="py-2 pr-4">PostHog — записи экрана, тепловые карты</td>
                <td className="py-2">30 дней</td>
              </tr>
            </tbody>
        </table>
        <h2 className="sh-heading-lg text-ink">Аналитические cookies (opt-in)</h2>
        <p>
          Мы используем PostHog (самохостинг, сервер в ЕС) для анализа поведения пользователей.
          Аналитические cookies требуют вашего согласия. Без согласия мы используем только
          анонимизированный daily-salted hash (cookieless режим) — данные ограничены.
          Feature flags работают всегда (это функциональность, не отслеживание).
          Срок хранения аналитических данных — не более 13 месяцев.
        </p>
        <h2 className="sh-heading-lg text-ink">Управление cookies</h2>
        <p>
          Вы можете отключить cookies в настройках браузера. Это может ограничить функциональность
          сервиса.
        </p>
      </div>
    </LegalLayout>
  )
}
