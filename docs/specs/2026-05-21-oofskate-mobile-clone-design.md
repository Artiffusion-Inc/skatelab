# OOFSkate Mobile Clone — Design Spec

> Дата: 2026-05-21
> Статус: Draft

## Цель

Создать мобильное приложение (Android → iOS), функционально эквивалентное OOFSkate: запись видео прыжков/спинов → серверный ML-анализ → метрики на устройстве. Ключевое отличие от OOFSkate — опциональная IMU-поддержка (BLE WitMotion WT901) для повышенной точности.

## Архитектура

### KMP + нативный UI

```
mobile/
├── shared/                    # KMP shared module (Kotlin)
│   ├── src/commonMain/
│   │   ├── api/               # Ktor HTTP client, endpoints
│   │   ├── models/            # DTO, domain models
│   │   ├── auth/              # JWT auth, token refresh
│   │   ├── state/             # State management (ObservableViewModel)
│   │   ├── util/              # Serialization, dates
│   │   └── platform/          # Expect declarations
│   ├── src/androidMain/       # Android actual
│   └── src/iosMain/           # iOS actual (Kotlin/Native)
├── androidApp/                # Android application
│   ├── ui/                    # Compose screens
│   │   ├── auth/              # Login, Register
│   │   ├── camera/            # CameraX recording
│   │   ├── session/           # Session list, detail, metrics
│   │   ├── profile/           # Profile, settings
│   │   └── comparison/        # Comparison views (v2)
│   ├── ble/                   # BLE IMU service
│   ├── service/               # Upload service, video processing
│   └── di/                    # Hilt modules
└── iosApp/                    # iOS application (later)
    ├── Views/                 # SwiftUI views
    └── Services/              # AVFoundation, CoreBluetooth
```

### Поток данных

```
CameraX → Video file → Chunked upload to R2 (/uploads)
  → POST /process → SSE stream (progress)
  → Results (metrics, skeleton, GOE) → UI render
```

### Технологии

| Компонент | Технология |
|-----------|------------|
| Shared logic | Kotlin Multiplatform |
| HTTP client | Ktor (OkHttp engine на Android) |
| Serialization | kotlinx.serialization |
| Android UI | Jetpack Compose |
| iOS UI | SwiftUI (позже) |
| Camera | CameraX (Android), AVFoundation (iOS) |
| Video player | Media3/ExoPlayer |
| Charts | Vico Charts |
| DI | Hilt (Android) |
| Auth | JWT + refresh, EncryptedStorage / Keychain |
| BLE | Android BLE / iOS CoreBluetooth |

## Экраны и навигация

### TabBar (4 таба)

| Таб | Экран | Описание |
|-----|-------|----------|
| Запись | CameraScreen | CameraX + кнопка записи. Опционально BLE-индикатор. |
| Анализ | ResultsScreen | Список сессий с превью + метриками. Тап → детали. |
| Профиль | ProfileScreen | Имя, аватар, настройки, подписка. |
| Ещё | MoreScreen | BLE-настройки, о приложении, выход. |

### Auth flow

```
SplashScreen → (no token) → LoginScreen / RegisterScreen
  → (token) → MainTabs
```

### Запись

```
CameraScreen → [Record] → ProcessingScreen (SSE progress)
  → ResultsDetailScreen (метрики + видео + скелет)
```

### ResultsDetailScreen

| Секция | Контент |
|--------|---------|
| Видео | ExoPlayer + скелетный оверлей (toggle) |
| Тип элемента | Автоклассификация (Axel, Lutz, Spin...) |
| Метрики-карточки | Высота, Airtime, Угловая скорость (пик/средняя), Вращения, Under-rotation, Качество приземления |
| GOE proxy | Оценка от бэкенда |
| Графики | Угловая скорость по времени (Vico Charts) |
| IMU | (если подключены) графики акселерометра |

## Метрики

Полный набор OOFSkate + дополнения:

| Метрика | Источник | Единицы |
|---------|----------|---------|
| Jump Height | ML пайплайн | см |
| Airtime | ML пайплайн | сек |
| Angular Velocity (средняя) | ML пайплайн | °/с, об/с, RPM (переключаемо) |
| Peak Angular Velocity | ML пайплайн | °/с |
| Time to Peak | ML пайплайн | сек |
| Rotation Count | ML пайплайн | кол-во |
| Under-rotation | ML пайплайн | ° (четвертьоборота) |
| Landing Quality | ML пайплайн | 0-100 |
| Jump Type (авто) | ML классификатор | Axel/Lutz/Flip/Loop/Salchow/ToeLoop |
| Spin Type (авто) | ML классификатор | Upright/OneFoot/Scratch |
| GOE Proxy | ML пайплайн (DTW vs ref) | -5..+5 |
| Knee Angles | ML пайплайн | ° |

### Единицы — переключатель

Угловая скорость: °/с ↔ об/с ↔ RPM. Настройка сохраняется в профиль.

## IMU (опционально)

- BLE-сканирование + подключение к WitMotion WT901
- Запись IMU-потока параллельно с видео
- Файл IMU (.binpb) загружается вместе с видео
- Бэкенд мержит IMU + видео-метрики
- Визуализация IMU-данных в ResultsDetailScreen (если есть)

**Видео работает без IMU. IMU — для точности.**

## Бэкенд-адаптация

### Существующее (готово)

- `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh` — JWT
- `POST /uploads` — chunked upload to R2
- `POST /sessions` — создание сессии
- `POST /process` — ML обработка с SSE streaming
- `GET /sessions/{id}/metrics` — метрики сессии
- `GET /sessions/{id}` — детали сессии

### Нужно добавить

- `GET /sessions` — список сессий пользователя (пагинация, для мобильного feed)
- `GET /users/me` — профиль
- `PUT /users/me` — обновление профиля
- Jump type classification — автоклассификация типа прыжка в ML pipeline
- Spin detection/classification — спины в ML pipeline
- Under-rotation точное определение (четвертьоборота)

## Фазы реализации

| Фаза | Контент | Срок |
|------|---------|------|
| 1. KMP + Auth | KMP-структура, shared-модуль, Ktor API клиент, auth flow, профиль | ~1 нед |
| 2. Камера + Upload | CameraX запись, chunked upload to R2, SSE streaming прогресс | ~1 нед |
| 3. Результаты | Session list, Session detail, метрики-карточки, видео-плеер, скелетный оверлей | ~1 нед |
| 4. ML-метрики | Подключение к /process, рендер всех метрик, графики угловой скорости, GOE proxy | ~1 нед |
| 5. IMU + BLE | BLE сканирование, запись параллельно с видео, upload IMU, IMU-графики | ~3 дня |
| 6. Классификация | Jump type + spin type classification (ML pipeline + UI) | ~3 дня |
| 7. Polish | Pull-to-refresh, error handling, оффлайн-кеш, анимации, lint | ~3 дня |

### Вне scope первой итерации

- Сравнение с собой / с про (v2)
- Instagram Stories sharing (v2)
- Push-уведомления (v2)
- iOS-приложение (после стабилизации Android)
