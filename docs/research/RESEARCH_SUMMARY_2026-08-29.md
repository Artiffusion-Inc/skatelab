---
title: "SkateLab MVP and platform strategy"
date: 2026-08-29
status: active
---

# SkateLab MVP and platform strategy

## Executive decision

Ship Android-first, but keep the product cross-platform: shared KMP domain and
Compose Multiplatform for report/history UI; native Android/iOS capture surfaces
for Camera/BLE/permissions. Do not migrate to Flutter during MVP.

## External evidence

- [Skrida waitlist](https://waitlist.skrida.app/) presents a pre-launch iOS figure-skating
  training app focused on jump tracking and session progress.
- [Carv sensors](https://getcarv.com/sensors) demonstrates the UX benchmark for two
  clip-on IMUs, sensor fusion, turn analysis and audio coaching in skiing.
- [OOFSkate partnership](https://usfigureskating.org/news/2025/12/2/press-releases-us-figure-skating-partners-with-oofskate-to-bring-ai-powered-jump-metrics-to-athletes-nationwide.aspx)
  and [RinkUp](https://apps.apple.com/us/app/athlitix-rinkup/id6751922852) show direct
  competition in video-only figure-skating jump analytics.
- [KMP](https://developer.android.com/kotlin/multiplatform) is supported by Google for
  shared business logic; [Compose Multiplatform](https://kotlinlang.org/multiplatform/)
  is stable for Android/iOS; [SwiftUI interop](https://kotlinlang.org/docs/multiplatform/compose-swiftui-integration.html)
  allows native iOS components where needed.

## Repository evidence

Already implemented: Android camera + two WT901 streams, delimited protobuf,
manifest/per-sensor offsets, GPU decoder, cross-sensor features, confidence,
recommendations, metric registry, web/Android labels and contract tests.

Canonical implementation plan: [competitive response](../plans/2026-08-29-competitive-response.md).

Current critical product gap: real-user validation. Existing README records no
prototype testing and no ground-truth ML benchmark.

## Product wedge

Position SkateLab as an **instrumented figure-skating lab**: video measures body
and phases; IMU measures skate motion; the report gives one coach-actionable
correction. First wedge: one Axel workflow, not a general AI coach.

## Execution plan

### Phase 0 — releaseable Android slice

Capture → upload → process → result must work with one tap path and both sensors.
Finish crash/error states, session retry, and a shareable report.

### Phase 1 — iOS-ready shared product

Move result/history/metrics/report screens to Compose Multiplatform. Keep
CameraX/CoreBluetooth/AVFoundation and permission flows native behind interfaces.
Build an iOS shell that renders a fixture result before implementing iOS capture.

### Phase 2 — evidence

Collect 10–20 Axel attempts from 3–5 skaters, annotate takeoff/landing and coach
quality, then calibrate thresholds. Do not train a model before this set exists.

## Stop conditions

Do not add new elements, replace WT901, or introduce Flutter unless Android slice
fails for a measured reason. The decision gate is coach usefulness and timing
accuracy, not framework preference.
