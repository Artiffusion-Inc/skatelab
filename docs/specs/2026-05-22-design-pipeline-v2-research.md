# Design Pipeline v2 — Research Report

> 5 специализированных агентов исследовали параллелизм, асинхронность, стоимость, существующие решения и инструменты. Результаты ниже.

---

## 1. Существующие LLM→Code пайплайны

### Прямых аналогов нет

Не найдено проектов с паттерном "YAML+prose source → LLM CLI → structured JSON → multi-platform files". Ближайшие аналоги:

- **Style Dictionary** (Amazon) — детерминистичные шаблоны, не LLM. Заменяем.
- **Terrazzo/Cobalt** (бывший Cobalt UI 2.0) — наследник Style Dictionary с нативной DTCG поддержкой. MIT, плагины для CSS/Swift/Tailwind. [GitHub](https://github.com/terrazzoapp/terrazzo), [Docs](https://cobalt-ui.pages.dev)
- **Tokens Studio** — Figma-плагин, всё ещё использует Style Dictionary как бэкенд.
- **Figma Make + AI** — AI-генерация внутри Figma, не CLI.

### "Compiled AI" — академическое обоснование

Paper arXiv:2604.05150 описывает нашу архитектуру точно: LLM работает один раз при генерации, затем код выполняется детерминистично без дальнейших вызовов модели.

- 96% task completion, 57x сокращение токенов при 1000 транзакций
- Точка окупаемости: ~17 транзакций
- Четыре этапа: constrained generation → security analysis → syntactic verification → execution testing

**Наш пайплайн — это Compiled AI система.** LLM — компилятор, не интерпретатор.

### G-Research LLM Code Review

Ключевые паттерны из продакшн LLM-пайплайна:
- LLM — ненадежный компонент с самого начала
- Standards document — единственный источник правил
- LLM-based repair: отправить malformed output обратно с ошибками валидации (1 попытка достаточна)
- Provider abstraction для fallback на другие модели

---

## 2. `claude -p` — лучшие практики

### Критичные флаги для CI

| Флаг | Назначение | Важность |
|------|-----------|----------|
| `-p` / `--print` | Неинтерактивный режим | Обязательный |
| `--output-format json` | Структурированный JSON на stdout | Обязательный |
| `--json-schema` | Constrained decoding по JSON Schema | **Критичный** — <0.3% ошибок |
| `--bare` | Пропускает hooks, skills, MCP, CLAUDE.md | Воспроизводимость в CI |
| `--max-budget-usd` | Лимит стоимости на вызов | Безопасность |
| `--model` | Выбор модели | Cost/performance |
| `--allowedTools` | Ограничение инструментов | Безопасность |

### `--json-schema` — главный вывод исследования

Constrained decoding гарантирует валидный JSON. Уровни надёжности:

| Подход | Частота ошибок |
|--------|---------------|
| Prompt-only ("output JSON") | 5-20% |
| JSON mode (OpenAI `json_object`) | 2-5% |
| **Constrained decoding + JSON Schema** | **<0.3%** |

**Вывод:** Спек должен использовать `--json-schema` с полной схемой выхода. Это устраняет необходимость retry на malformed JSON. Валидация `design-build.js` остаётся для семантических проверок (counts, hex values, OKLCH format).

### `--bare` для воспроизводимости

Пропускает `~/.claude` конфиги, `.mcp.json`, auto-discovered hooks. Только явно переданные флаги действуют. Обязательно для CI.

---

## 3. Параллелизм и асинхронность

### Стратегия A: Fan-out по платформам (3 параллельных вызова)

CSS, Kotlin, Swift генерируются параллельно. Каждый вызов получает DESIGN.md + платформенные инструкции.

| Метрика | Single call | Fan-out (3 parallel) |
|---------|-------------|---------------------|
| Wall time | 30-60s | 15-25s (самый долгий из 3) |
| Кроссплатформенная консистентность | Гарантирована | Риск расхождения имён |
| Стоимость | Ниже (один prompt) | Выше (3x prompt overhead) |

### Стратегия B: Hybrid (Рекомендация)

```
DESIGN.md → [architect call: shared vocab JSON, ~5s] → ┬─ CSS call (vocab + CSS rules, ~15-25s)
                                                        ├─ Kotlin call (vocab + Kotlin rules)
                                                        └─ Swift call (vocab + Swift rules)
```

Architect-вызов (~5с) создаёт общий словарь (имена цветов, semantic aliases, type scale), затем 3 платформенных вызова идут параллельно. Total: ~20-30с вместо 30-60с.

Паттерн из SpecGen (danielkliewer.com/blog/2026-01-07-specgen): SpecInterpreter → structured spec → generator fan-out.

### Node.js async паттерны

| Паттерн | Для чего | Сложность |
|---------|----------|-----------|
| `p-queue` + `Promise.all` | I/O-bound параллельные LLM вызовы | Низкая |
| Worker threads | CPU-bound работа (парсинг, валидация) | Высокая |
| `execa` | Субпроцесс-менеджмент с timeout/kill | Низкая |

**Рекомендация:** `p-queue` (concurrency=3) + `execa` для управления `claude -p` субпроцессами. Worker threads не нужны — работа I/O-bound.

### Taskfile параллелизм

Taskfile уже поддерживает `deps` (параллельное выполнение) и `parallel: true`. Проект уже использует это в `dev` таске. Не нужно добавлять `npm-run-all` или `concurrently`.

---

## 4. Стоимость

### Цены Anthropic (апрель 2026)

| Модель | Input $/MTok | Output $/MTok | Cache Hit $/MTok |
|--------|-------------|---------------|-------------------|
| Haiku 4.5 | $1.00 | $5.00 | $0.10 |
| Sonnet 4.6 | $3.00 | $15.00 | $0.30 |

### Стоимость на запуск пайплайна

| Сценарий | Sonnet 4.6 | Haiku 4.5 |
|----------|-----------|-----------|
| Без кеширования | $0.32 | $0.11 |
| С prompt caching | $0.39 | $0.11 |
| Batch API (50% скидка) | $0.16 | $0.053 |
| 3 retries worst case | $0.96 | $0.33 |

**Месячная оценка (10 запусков):** Sonnet ~$4-8/мес, Haiku ~$1-2/мес. Стоимость не проблема.

### Ключевые оптимизации

1. **Conditional trigger**: только при изменении DESIGN.md → $0 для большинства PR
2. **Prompt caching**: 90% скидка на cached input после первого запуска
3. **Batch API**: 50% скидка для ночных `design:audit`
4. **`--max-budget-usd 1.00`**: хардкап на каждый вызов

---

## 5. Надёжность и Fallback

### Улучшенная стратегия retry

Текущий спек: max 3 retries + git checkout fallback. Улучшения:

```
1. Validation failure → augment prompt with error, retry (max 3)
2. API error (429, 5xx) → exponential backoff + jitter, retry (max 3)
3. Non-retryable (4xx not 429) → immediate fallback
4. All retries exhausted → model fallback (sonnet → haiku if applicable)
5. All fallbacks exhausted → git checkout HEAD
6. Track failures in tokens/build.log, circuit-break after 5 consecutive total failures
```

### `--fallback-model`

Claude CLI имеет встроенный флаг fallback на другую модель. Если Sonnet не отвечает — fallback на Haiku.

### Circuit breaker

После 5 последовательных полных сбоев — пропустить генерацию, использовать `git checkout HEAD`, требовать ручной обзор.

---

## 6. Impeccable + Hallmark

### Impeccable — production-ready для CI

- npm пакет `impeccable` v2.1.9, 29.2k stars
- `npx impeccable detect --json` → exit code 2 при обнаружении
- `--fast` для pre-commit (regex-only)
- Полный режим с jsdom для PR
- 25+ паттернов в 6 категориях
- **Детерминистичный, без LLM, без API key**

### Hallmark — НЕ CLI инструмент

- Это **skill** для Claude Code/Cursor/Codex (инструкции в `SKILL.md`)
- Нет standalone CLI, нет npm binary, нет exit codes
- Audit работает через `claude -p "hallmark audit..."` — LLM-вызов
- 65 slop-test gates — вопросы где каждый ответ должен быть "no"
- **Уникальная ценность:** macrostructure diversification, brand fit, holistic design quality judgment
- **Для CI:** слишком медленный, дорогой, недетерминистичный

### Перекрытие impeccable ↔ hallmark

Оба ловят: purple gradients, Inter/Roboto fonts, 3-column cards, card-in-card, gradient text, centered heroes, `transition-all`, pure black/white.

**Уникальное от hallmark:** структурное разнообразие (макроструктуры), философия дизайна, brand-specific judgment — требует LLM.

### ast-grep потенциал

Текущие 5 design rules → можно расширить до 10-15:

| Новое правило | Паттерн |
|---------------|---------|
| No `transition-all` | `transition: "all"` / Tailwind `transition-all` |
| No `hover:scale-105` | uniform scale effects |
| No gradient text | `bg-gradient-to-r` + `bg-clip-text` |
| No raw `#000`/`#fff` | hex patterns in style attrs |
| No banned easing curves | `cubic-bezier(0.34, 1.56` |
| No Inter/Roboto imports | font references |

ast-grep покрывает ~30-40% design system enforcement. Остальное — impeccable (runtime/DOM) и hallmark (semantic judgment).

### Рекомендуемая CI-архитектура

```
Pre-commit (lefthook):
  1. sg scan (ast-grep) — fast, structural
  2. impeccable detect --fast — regex-only, exit 2

PR (GitHub Actions):
  1. sg scan — full structural scan
  2. impeccable detect --json — full scan with jsdom
  3. design-wcag.js — contrast validation
  4. (Manual trigger) claude -p "hallmark audit..." — scheduled deep review
```

---

## 7. WCAG Contrast Validation

### npm библиотеки

| Библиотека | OKLCH | WCAG | Особенности |
|-----------|-------|------|------------|
| `wcag-contrast` | Нет (нужна конвертация) | 2.0/2.1 | Минимальная, `contrast(hex1, hex2)` |
| `@incluud/color-contrast-checker` | **Да** | 2.2 | OKLCH нативно, TypeScript, CSS export |

**Рекомендация:** `@incluud/color-contrast-checker` — нативная OKLCH поддержка, WCAG 2.2, TypeScript. Либо `wcag-contrast` с OKLCH→linear-sRGB конвертацией.

---

## 8. Drift Detection

### Улучшение lock.json

Текущий формат хеширует только выходные файлы. Рекомендуется добавить:

```json
{
  "version": 2,
  "designMdHash": "sha256:abc...",
  "sectionHashes": {
    "colors": "sha256:def...",
    "typography": "sha256:ghi...",
    "shadows": "sha256:jkl...",
    "components": "sha256:mno..."
  },
  "platformHashes": {
    "css": "sha256:pqr...",
    "kotlin": "sha256:stu...",
    "swift": "sha256:vwx..."
  },
  "metadata": {
    "model": "claude-sonnet-4-6-20250514",
    "promptVersion": "sha256:..."
  }
}
```

Это позволяет:
1. Skip генерацию если DESIGN.md не изменился (0ms, $0)
2. Инкрементальная генерация по секциям
3. Отслеживание какой промпт/модель сгенерировала файл

### Determinism caveat

Temperature 0 НЕ гарантирует bit-identical output (GPU floating-point, MoE routing). Но для design token генерации "approximately deterministic" достаточно — семантическое содержание верно, небольшие вариации форматирования допустимы.

**Пин модели:** Использовать `--model claude-sonnet-4-6-20250514` (pinned date), не просто `sonnet`.

---

## 9. Hybrid / Fallback подходы

### LLM → Deterministic Templates

Альтернатива: LLM генерирует промежуточный IR (`tokens.json`), детерминистичные шаблоны создают платформенные файлы.

```
DESIGN.md → LLM → tokens.json (IR) → deterministic templates → 11 platform files
```

**Pros:** Меньше токенов на LLM-вызов, шаблоны тестируемые, fallback без LLM.
**Cons:** Maintenance 11 шаблонов, потеря кроссплатформенной consistency.

**Вердикт:** Текущий подход (LLM генерирует полные файлы) проще и лучше при стоимости <$8/мес. Но IR + templates — хороший **zero-LLM fallback**: если все LLM-вызовы не удаются, использовать детерминистичные шаблоны от последнего известного `tokens.json`.

### Compiled AI pattern

Наш пайплайн уже является Compiled AI. LLM работает как компилятор. Runtime — детерминистичный (static code). Это оптимальная архитектура для нашей задачи.

---

## 10. Итоговые рекомендации по улучшению спека

### Критичные (блокеры)

| # | Изменение | Обоснование |
|---|-----------|-------------|
| 1 | **Добавить `--json-schema`** в `claude -p` вызов | Снижает ошибки JSON с 5-20% до <0.3% |
| 2 | **Добавить `--bare`** для CI вызовов | Воспроизводимость без локальных конфигов |
| 3 | **Пин модели:** `claude-sonnet-4-6-20250514` | Детерминизм между запусками |
| 4 | **Добавить `designMdHash`** в `lock.json` | Skip генерации при неизменном DESIGN.md ($0) |
| 5 | **Разделять retryable/non-retryable ошибки** | 429/5xx → retry; 4xx → immediate fallback |

### Важные (улучшения)

| # | Изменение | Обоснование |
|---|-----------|-------------|
| 6 | **Hybrid fan-out:** architect call + 3 parallel platform calls | Wall time 20-30с вместо 30-60с |
| 7 | **`execa` вместо `child_process`** | Timeout, graceful kill, process tree cleanup |
| 8 | **`p-queue` для concurrency control** | Rate limiting, timeout, retry per task |
| 9 | **Circuit breaker** после 5 сбоев | Не тратить API кредиты на сломанный промпт |
| 10 | **Расширить ast-grep rules** до 10-15 | Покрыть `transition-all`, `hover:scale-105`, gradient text |
| 11 | **Hallmark: scheduled only, не CI gate** | Слишком медленный/дорогой для CI |
| 12 | **Batch API для `design:audit`** | 50% скидка, 24ч latency приемлема для аудита |

### Опциональные (nice-to-have)

| # | Изменение | Обоснование |
|---|-----------|-------------|
| 13 | `tokens.json` IR как zero-LLM fallback | Детерминистичный fallback без git checkout |
| 14 | `@incluud/color-contrast-checker` вместо своего WCAG скрипта | OKLCH нативно, WCAG 2.2 |
| 15 | `sectionHashes` в lock.json для инкрементальной генерации | Регенерировать только изменившиеся секции |
| 16 | `metadata.model` + `metadata.promptVersion` в lock.json | Audit trail для поколения |
| 17 | `--max-budget-usd 1.00` хардкап | Защита от runaway costs |

---

## Источники

- Compiled AI: https://arxiv.org/html/2604.05150v1
- G-Research LLM patterns: https://www.gresearch.com/news/building-a-code-review-tool-the-llm-patterns-that-actually-work
- Structured output failure modes: https://tianpan.co/blog/2026-04-18-structured-output-json-mode-failure-modes
- Claude Code headless: https://code.claude.com/docs/en/headless
- Claude CLI flags: https://www.mager.co/blog/2026-04-20-claude-code-cli-flags
- Anthropic structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic batch API: https://platform.claude.com/docs/en/build-with-claude/batch-processing
- Anthropic prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Terrazzo/Cobalt: https://cobalt-ui.pages.dev, https://github.com/terrazzoapp/terrazzo
- W3C DTCG spec 2025.10: https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version
- Impeccable: https://github.com/pbakaus/impeccable, https://impeccable.style
- Hallmark: https://github.com/Nutlope/hallmark, https://www.usehallmark.com
- BAML comparison: https://boundaryml.com/blog/structured-output-from-llms
- Temperature 0 determinism: https://www.vincentschmalbach.com/does-temperature-0-guarantee-deterministic-llm-outputs
- SpecGen pattern: https://www.danielkliewer.com/blog/2026-01-07-specgen-deterministic-ai-powered-code-generation-from-naturals-language
- Portkey retries: https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps
- Martin Fowler tokens: https://martinfowler.com/articles/design-token-based-ui-architecture.html
- LLM-readable design systems: https://hardik.substack.com/p/expose-your-design-system-to-llms
- Material Design 3 tokens: https://m3.material.io/foundations/design-tokens
- eBay tokens: https://playbook.ebay.com/design-system/tokens
- Atlassian tokens: https://atlassian.design/tokens/design-tokens
