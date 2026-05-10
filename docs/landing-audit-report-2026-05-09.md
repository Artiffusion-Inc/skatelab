# SkateLab Landing: Deep Audit Report

Дата: 2026-05-09
Метод: 5 специализированных агентов (типографика, цвет, layout, копирайт, моушн)
Цель: выявить нарушения DESIGN.md и предложить приоритизированные улучшения

---

## Сводка нарушений

| Приоритет | Кол-во | Суть |
|-----------|--------|------|
| P0 | 6 | WCAG провал, нарушенные правила системы, critical UX |
| P1 | 8 | Токенные нарушения, структурные слабости |
| P2 | 10 | Улучшения качества, недочёты |
| P3 | 6 | Полировка, "signature moments" |

---

## P0 — Критические

### 1. WCAG AA провал: on-dark-faint на badge labels
**Контраст 2.4:1** (минимум 4.5:1). Используется в Hero overlay badge, Demo metric badges (десктоп + мобильный).

**Файлы:** hero-section.tsx:84, demo-section.tsx:115,121,126,185,192,199

**Фикс:** Заменить `text-on-dark-faint` на `text-on-dark-mute` во всех badge label'ах. Контраст поднимется до ~5.5:1.

### 2. Hero: два CTA одного визуального веса
Нарушение правила "single CTA per section". Ghost button "Смотреть демо" конкурирует с primary.

**Файл:** hero-section.tsx:44-63

**Фикс:** Убрать Button wrapper для secondary CTA. Сделать текстовой ссылкой в subtitle или отдельной строкой под основным CTA:
```tsx
<a href="#demo" className="sh-caption text-on-dark-mute underline hover:text-primary-foreground transition-colors">
  {t("ctaSecondary")}
</a>
```

### 3. StickyHeader: backdrop-blur = frosted glass
DESIGN.md прямо запрещает: "No-Winter-Cliche: No frosted borders, frozen glass effects."

**Файл:** sticky-header.tsx:55

**Фикс:** Убрать `style={{ backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)" }}`. Header-bg opacity 0→1 через GSAP уже обеспечивает переход. Непрозрачный фон при скролле = Flat-By-Default.

### 4. AccordionTrigger: font-medium (w500) — не из системы
Вес 500 не существует в токенах (460/540/600/700).

**Файл:** accordion.tsx (shadcn компонент)

**Фикс:** Заменить `text-sm font-medium` на `sh-heading-lg text-ink`. FAQ-вопросы = заголовки раскрывающихся секций.

### 5. Pricing badge: font-semibold без токена
`text-xs text-primary font-semibold` — сырой Tailwind-вес вместо токена.

**Файл:** pricing-section.tsx:68

**Фикс:** Заменить на `sh-button-cap text-primary`. Убрать `text-xs font-semibold`.

### 6. Easings: power2.out вместо power3.out/power4.out
DESIGN.md: "Ease out with exponential curves (ease-out-quart/quint/expo). No bounce, no elastic." Текущий power2.out — слишком мягкий, не Superhuman-стиль.

**Файл:** landing-client.tsx (все gsap.fromTo вызовы)

**Фикс:** Заменить все `ease: "power2.out"` на `ease: "power3.out"`. Унифицировать y-сдвиги на 24px, длительности на 0.4s (секции) / 0.6s (hero).

---

## P1 — Важные

### 7. Demo: bg-canvas-soft нарушает правило трёх холстов
Четвёртый "холст" между hero (indigo) и CTA (teal). Body должен быть bg-background.

**Файл:** demo-section.tsx:86

**Фикс:** `bg-canvas-soft` → `bg-background`

### 8. 75ch правило: hero subtitle, FAQ ответы, HowItWorks descriptions
Строки превышают 75ch. FAQ: max-w-3xl = 768px → ~95ch при body-md.

**Фикс:** Заменить `max-w-lg` на `max-w-[75ch]` в hero subtitle. Добавить `max-w-[75ch]` на FAQ AccordionContent и HowItWorks step descriptions.

### 9. StickyHeader mobile menu: text-lg без токена
`text-lg` (18px) без указания веса. Должно быть `sh-body-lg`.

**Файл:** sticky-header.tsx:129

**Фикс:** `text-lg` → `sh-body-lg`

### 10. Step-watermark: font-weight 600 + захардкоженный цвет
w600 на декоративном элементе нарушает Sub-Default. Цвет `oklch(0.7 0.006 80 / 0.25)` не из палитры.

**Файл:** globals.css:150-160

**Фикс:** `font-weight: 600` → `540`. Цвет → `oklch(0.678 0.008 106 / 0.25)` (ink-faint с opacity).

### 11. CTA section: max-w-lg слишком узкий
Текст CTA занимает менее половины доступной ширины. Superhuman финальный CTA — центрированный, широкий.

**Файл:** cta-section.tsx:13

**Фикс:** `max-w-lg` → `max-w-2xl text-center`. Eyebrow/headline/subtitle/button по центру.

### 12. Hero image: резкий скачок аспект-соотношения на 1024px
Мобильный 16:9 → десктоп 4:5 без промежуточного. Планшетный разрыв.

**Файл:** hero-section.tsx:68

**Фикс:** Добавить `md:aspect-[4/3]` между `aspect-[16/9]` и `lg:aspect-[4/5]`.

### 13. Button active state: translate-y-px вместо scale(0.98)
DESIGN.md: "Active: Scale 0.98 transform, no shadow." Текущий сдвиг вниз = "проваливание", scale = "нажатие".

**Файл:** button.tsx

**Фикс:** `active:translate-y-px` → `active:scale-[0.98]`. Добавить `hover:-translate-y-px` для hover-подъёма.

### 14. Reduced-motion дыры
1. Demo mobile fallback анимирует при `prefers-reduced-motion: reduce`
2. SkeletonPose setInterval работает без проверки
3. `animation-duration: 0.01ms` хак вместо `animation: none !important`

**Фикс:** Demo: мгновенный `gsap.set`. Skeleton: проверка `matchMedia`. CSS: `animation: none !important`.

---

## P2 — Качество

### 15. CookieBanner: shadow-lg нарушает Flat-By-Default
**Фикс:** Убрать `shadow-lg shadow-primary/5`. Border-t + bg-canvas-soft достаточно.

### 16. Featured pricing card: border-primary невидимая рамка
Индиго на индиго. Либо убрать border, либо `border-surface-violet-soft/30`.

### 17. Featured pricing CTA: variant="on-teal" диссонирует с indigo-карточкой
Белая кнопка с teal-текстом на индиго фоне. Заменить на `variant="on-dark-pill"` (violet-soft).

### 18. FAQ AccordionTrigger без text-ink
Наследует `text-foreground` вместо `text-ink`. Разница минимальна, но нарушает токенную дисциплину.

### 19. Demo: py-16 md:py-24 — заниженный паддинг
Все остальные секции py-20 md:py-28. Demo "проваливается" визуально.

**Фикс:** `py-20 md:py-28`

### 20. Trust: text-center — Superhuman не центрирует статистику
Левая ось = редакционная точность.

**Фикс:** Убрать `text-center`. Каждый счётчик выровнять по левому краю.

### 21. Hero gradient bridge: h-20 md:h-28 перегружает нижнюю часть
Вместе с py-24 = 152px нижнего отступа vs py-28 у следующей секции.

**Фикс:** `h-16 md:h-20`

### 22. Pricing: симметричная grid-cols-3 не выделяет Pro
Pro доминирует цветом, но не структурой.

**Фикс:** `lg:grid-cols-[1fr_1.15fr_1fr]`

### 23. Footer: py-12 md:py-16 — резкий обрыв после CTA py-32
**Фикс:** `py-16 md:py-20`

### 24. Hero CTA buttons: text-base без токена
Кнопки используют `text-base` (сырой Tailwind). Должны быть через Button variant или токен.

---

## P3 — Полировка

### 25. Footer grid: первая колонка (logo+tagline) не шире остальных
**Фикс:** `lg:grid-cols-[1.4fr_1fr_1fr_1fr]`

### 26. CTA "Уже есть аккаунт" — стилизована как pseudo-button
Ссылка не должна имитировать кнопку.

**Фикс:** Убрать `min-h-[44px] flex items-center`, заменить на обычный `<a>` с underline.

### 27. Hero scroll indicator: статичная SVG без анимации
Мягкая y-осцилляция (8px, yoyo, 1.5s) сделает её "живой".

### 28. Nav underline slide-in на sticky header
`after:` pseudo-element с `scale-x-0 → hover:scale-x-100` — дешёвый, эффектный паттерн.

### 29. FAQ: одна chevron + rotate-180 вместо двух иконок
Текущий подход: скрытие DownIcon/UpIcon через `group-aria-expanded:hidden`.

### 30. Missing tokens: sh-body-strong, sh-button-md
Спецификация требует, но CSS не определяет.

---

## Копирайт: 5 высокоимпактных рекомендаций

### K1. Переписать Hero headline
**Сейчас:** "Запишите прыжок. Увидьте миллиметры."
**Предложение:** "То, что видит глаз, измеряет машина."
**Почему:** "Миллиметры" — никто так не говорит в фигурном катании. Контраст глаз/машина создаёт напряжение и апеллирует к боли тренера (субъективность).

### K2. Добавить Problem section между Hero и HowItWorks
B2B-аудитория покупает решение проблемы. Проблема сейчас не сформулирована. Три блока: недокрут выглядит одинаково, три тренера три ошибки, родители спрашивают прогресс по памяти.

### K3. HowItWorks: "зачем" вместо "как"
Eyebrow: "От видео до выводов". Headline: "Не гадай. Измеряй." Шаг 2 включить конкретные цифры точности (2 см, 5 градусов), а не абстрактные "12+ параметров".

### K4. Унифицировать обращение на "вы"
Страница мечется между "ты" (CTA), "вы" (subtitle), безличными формами. B2B-продукт → "вы" = спортивное уважение.

### K5. Trust: переместить после Demo + добавить цитаты/логотипы
1200 сессий и 15 клубов без имён не работают для B2B. После Demo (когда ценность показана) + минимум 2 цитаты тренеров с именами и клубами.

---

## Моушн: приоритеты

| # | Изменение | Приоритет | Effort |
|---|-----------|-----------|--------|
| 1 | Easing: power2 → power3.out, y-сдвиг: 24px token | P0 | 10 мин |
| 2 | Button: active scale(0.98) + hover lift | P0 | 5 мин |
| 3 | Reduced-motion дыры (demo, skeleton, CSS) | P0 | 15 мин |
| 4 | Hero stagger 0.12→0.08, duration 0.8→0.6 | P1 | 5 мин |
| 5 | Hero scroll indicator oscillation | P1 | 10 мин |
| 6 | FAQ chevron rotate-180 | P1 | 10 мин |
| 7 | SkeletonPose: setInterval → rAF + direct DOM | P2 | 30 мин |
| 8 | Trust counters: start from 0.9*target | P2 | 5 мин |
| 9 | Hero parallax (backdrop/image scrub) | P2 | 30 мин |
| 10 | Pricing card hover: scale(1.01) | P2 | 10 мин |
| 11 | CTA section wipe reveal | P3 | 1-2 часа |
| 12 | Hero split-text word stagger | P3 | 1-2 часа |

---

## Порядок реализации (предлагаемый)

### Волна 1: P0 (30-40 мин)
1. on-dark-faint → on-dark-mute (WCAG)
2. Hero: убрать ghost CTA button
3. StickyHeader: убрать backdrop-blur
4. AccordionTrigger: sh-heading-lg
5. Pricing badge: sh-button-cap
6. Easings: power3.out + y-сдвиг 24px

### Волна 2: P1 (45-60 мин)
7. Demo bg → bg-background
8. 75ch: max-w-[75ch] в hero/FAQ/HowItWorks
9. Mobile menu: sh-body-lg
10. Watermark: w540 + токенный цвет
11. CTA: max-w-2xl text-center
12. Hero image: md:aspect-[4/3]
13. Button: scale(0.98) active + hover lift
14. Reduced-motion: demo + skeleton + CSS

### Волна 3: P2 (60-90 мин)
15-24. Все P2 элементы

### Волна 4: Копирайт (отдельная задача)
K1-K5. Требует обновления i18n JSON + возможно новых компонентов

### Волна 5: P3 + Signature moments
25-30 + CTA wipe reveal / split-text