# SkateLab — Business Knowledge Base

> Единая точка входа в бизнес-документацию. NLM/LLM-ready.
> **Hardware:** WitMotion WT901 BLE CL, 1 441 ₽/шт на [Озоне](https://www.ozon.ru/product/witmotion-akselerometr-datchik-dvizheniya-chernyy-matovyy-goluboy-1906602111/) (включая Type-C зарядку). Два датчика = 2 882 ₽.

## Structure

```
docs/business/
├── CLAUDE.md                     ← Вы здесь
├── 01-product/
│   └── vision.md                 # Продуктовое видение, mission, ценность
├── 02-market/
│   ├── segmentation.md           # Сегментация клиентов (demographics)
│   ├── abcd-segmentation.md      # ABCDX-сегментация
│   ├── tam-calculation.md        # TAM/SAM/SOM расчёты
│   └── custdev-results.md        # Результаты интервью
├── 03-competitive/
│   └── landscape.md              # Конкурентный анализ
├── 04-financial/
│   └── unit-economics.md         # Юнит-экономика, LTV/CAC, break-even, прогноз
├── 05-ip-legal/
│   └── ip-assets.md              # IP, лицензии, риски
├── 06-gtm/
│   ├── strategy.md               # Go-to-market: каналы, воронка, метрики
│   └── positioning.md           # Позиционирование, JTBD, pricing
├── 07-technology/
│   └── risks-and-rd.md           # Техриски, GPU cost, IMU experiments
├── 08-team/
│   └── team-structure.md         # Команда, найм
├── 09-roadmap/
│   └── business-roadmap.md       # Роадмап по кварталам
└── appendix/
    ├── hardware-concept.md       # IMU hardware: основной продукт
    └── experts-and-events.md     # Эксперты, Startup Night
```

## Quick Links by Topic

### Для инвесторов
- [TAM/SAM/SOM](02-market/tam-calculation.md)
- [Юнит-экономика](04-financial/unit-economics.md)
- [Конкурентный анализ](03-competitive/landscape.md)
- [Бизнес-роадмап](09-roadmap/business-roadmap.md)

### Для product/marketing
- [Продуктовое видение](01-product/vision.md)
- [ABCD-сегментация](02-market/abcd-segmentation.md)
- [CustDev результаты](02-market/custdev-results.md)
- [Позиционирование + JTBD](06-gtm/positioning.md)
- [Go-to-market](06-gtm/strategy.md)

### Для tech/инженеров
- [Технические риски + IMU](07-technology/risks-and-rd.md)
- [IP и лицензии](05-ip-legal/ip-assets.md)

### Архив
- [Эксперты и мероприятия](appendix/experts-and-events.md) — Startup Night (2026-05-07, завершён)
- [IMU hardware](appendix/hardware-concept.md)

## Key Numbers

| Метрика                             | Значение                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------ |
| **Цена комплекта**                  | **TBD** (не валидировано)                                                |
| **BOM (2× WitMotion WT901 BLE CL)** | 2 882 ₽ ([Озон](https://www.ozon.ru/product/witmotion-akselerometr-datchik-dvizheniya-chernyy-matovyy-goluboy-1906602111/)) |
| **Крепление + упаковка**            | ~650 ₽ *(грубая оценка; корпус 3D-печать ~копейки, упаковка не проработана)* |
| **Variable Cost**                   | ~3 530 ₽ *(BOM + крепление — прямые затраты на единицу)*                |
| **Налог УСН 15%**                   | ~2 325 ₽                                                                 |
| **Итого VC с налогом**              | **~5 860 ₽**                                                             |
| **Маржинальность**                  | **~62%**                                                                 |
| **LTV**                             | TBD *(требуются данные retention)*                                      |
| **CAC (контент-маркетинг)**         | 2 500 ₽                                                                  |
| **CAC (warm intros Алисы)**[^cac]  | ~0 ₽                                                                     |
| **LTV / CAC**                       | TBD                                                                       |
| **Break-even (математический)**     | 1.6 комплекта                                                            |
| **Break-even (реалистичный)**       | ~15 комплектов/мес (с учётом зарплат основателей)                        |
| **Окупаемость разработки**          | TBD                                                                       |
| **Y1 (MVP)**                        | TBD                                                                       |
| **Y2**                              | TBD                                                                       |
| **Y3**                              | TBD                                                                       |
| TAM (bottom-up)                     | TBD                                                                       |
| SAM (русскоязычные)                 | 85K–115K фигуристов (факт-чек: 283K завышено в 2.5–3x)                   |
| CustDev interviews                  | 3 (тренеры + спортсмен)                                                  |
| MVP hardware                        | WitMotion WT901 BLE CL (подтверждено Озон)                               |
| MVP software                        | Функционал реализован (~279 тест-кейсов). ⚠️ 1 ошибка при сборке тестов. |

## Hardware Roadmap

| Этап                     | BOM            | Источник                 |
| ------------------------ | -------------- | ------------------------ |
| **MVP (сейчас)**         | ~2 900 ₽       | Озон WitMotion WT901     |
| **Pilot (Y1)**           | ~2 500 ₽       | Озон bulk-закуп (скидка за объём) |
| **Scale (Y2)**           | ~1 500–2 000 ₽ | Прямые поставщики / bulk |
| **Own production (Y3+)** | ~1 000–1 500 ₽ | Своё производство        |

## Team

| Роль                  | Кто                                                          |
| --------------------- | ------------------------------------------------------------ |
| Founder / ML          | Бодарев Михаил Артёмович (ФТМИ ИТМО, @xpos587)              |
| Co-Founder / Business | Абдуллина Алиса Рустемовна (ФТМИ ИТМО, МС по фигурному катанию, @alyssaabdullina) |

## Contact

- Бодарев Михаил: @xpos587 (Telegram)
- Абдуллина Алиса: @alyssaabdullina (Telegram)

[^cac]: **CAC (warm intros):** Продажи через личный нетворк Алисы (тренеры, федерации, DUSSH). Прямые затраты ≈ 0, но вкладывается время основателей.
