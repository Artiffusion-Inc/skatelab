"use client"

import { useState, useCallback } from "react"
import {
  Video,
  BarChart3,
  TrendingUp,
  Users,
  MessageSquare,
  Music,
  Timer,
  Copy,
  Check,
  Activity,
  RotateCcw,
  ArrowUpRight,
  ChevronRight,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useTranslations } from "@/i18n"
import type { UserRole } from "./onboarding-flow"

interface TourSliderProps {
  role: UserRole
  onComplete: () => void
  onSkip: () => void
}

/* ─── Previews ─── */

function UploadPreview() {
  const t = useTranslations("onboarding")
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-3 shadow-sm">
      <div className="relative aspect-[4/5] rounded-lg bg-muted overflow-hidden">
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Video className="h-5 w-5 text-primary" />
          </div>
          <p className="text-xs text-ink-mute">{t("uploadPreview")}</p>
        </div>
        <div className="absolute bottom-2 right-2 flex gap-1">
          <div className="h-6 w-6 rounded-full bg-primary flex items-center justify-center">
            <Activity className="h-3 w-3 text-primary-foreground" />
          </div>
        </div>
        {/* Skeleton overlay hint */}
        <svg className="absolute inset-0 opacity-20" viewBox="0 0 100 125" aria-hidden="true">
          <title>Figure skater skeleton</title>
          <circle cx="50" cy="30" r="4" fill="currentColor" className="text-primary" />
          <line
            x1="50"
            y1="34"
            x2="50"
            y2="60"
            stroke="currentColor"
            strokeWidth="1"
            className="text-primary"
          />
          <line
            x1="50"
            y1="45"
            x2="35"
            y2="55"
            stroke="currentColor"
            strokeWidth="1"
            className="text-primary"
          />
          <line
            x1="50"
            y1="45"
            x2="65"
            y2="55"
            stroke="currentColor"
            strokeWidth="1"
            className="text-primary"
          />
          <line
            x1="50"
            y1="60"
            x2="40"
            y2="90"
            stroke="currentColor"
            strokeWidth="1"
            className="text-primary"
          />
          <line
            x1="50"
            y1="60"
            x2="60"
            y2="90"
            stroke="currentColor"
            strokeWidth="1"
            className="text-primary"
          />
        </svg>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <div className="h-2 w-20 rounded bg-muted" />
        <div className="h-2 w-12 rounded bg-primary/20" />
      </div>
    </div>
  )
}

function MetricsPreview() {
  const t = useTranslations("onboarding")
  const metrics = [
    { label: t("metricsAirtime"), value: "0.42 с", icon: Timer, good: true },
    { label: t("metricsHeight"), value: "32 см", icon: ArrowUpRight, good: true },
    { label: t("metricsRotation"), value: "2.5 об", icon: RotateCcw, good: false },
  ]
  return (
    <div className="mx-auto w-full max-w-[280px] space-y-2">
      {metrics.map(m => (
        <div
          key={m.label}
          className="flex items-center justify-between rounded-xl border border-hairline bg-card px-4 py-3 shadow-sm"
        >
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg",
                m.good ? "bg-primary/10" : "bg-amber-500/10",
              )}
            >
              <m.icon className={cn("h-4 w-4", m.good ? "text-primary" : "text-amber-500")} />
            </div>
            <span className="text-sm text-ink-mute">{m.label}</span>
          </div>
          <span className="text-sm font-medium text-foreground">{m.value}</span>
        </div>
      ))}
    </div>
  )
}

function ProgressPreview() {
  const t = useTranslations("onboarding")
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-medium text-ink-mute">{t("progressLabel")}</span>
        <span className="text-xs text-primary font-medium">+12%</span>
      </div>
      <div className="flex items-end gap-1 h-16">
        {[40, 55, 45, 60, 50, 70, 65, 80, 75, 90].map((h, i) => (
          <div
            key={i}
            className={cn("flex-1 rounded-t-sm", i === 9 ? "bg-primary" : "bg-primary/20")}
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 rounded-lg bg-primary/5 px-3 py-2">
        <TrendingUp className="h-4 w-4 text-primary" />
        <span className="text-xs text-foreground">{t("newRecord")}</span>
      </div>
    </div>
  )
}

function InvitePreview() {
  const [copied, setCopied] = useState(false)
  const t = useTranslations("onboarding")
  const handleCopy = useCallback(() => {
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [])

  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-4 shadow-sm space-y-3">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
          <Users className="h-5 w-5 text-primary" />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">{t("inviteStudent")}</p>
          <p className="text-xs text-ink-mute">{t("inviteHint")}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 rounded-lg border border-hairline bg-background px-3 py-2">
        <span className="flex-1 truncate text-xs text-ink-mute">icelab.app/invite/a7x9k2</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground transition-colors hover:bg-primary-deep"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
    </div>
  )
}

function CoachDashboardPreview() {
  const t = useTranslations("onboarding")
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-3 shadow-sm space-y-2">
      <div className="flex items-center gap-3 rounded-lg bg-background px-3 py-2.5">
        <div className="h-8 w-8 rounded-full bg-muted" />
        <div className="flex-1">
          <p className="text-sm font-medium text-foreground">Анна К.</p>
          <p className="text-xs text-ink-mute">{t("sessionsThisWeek")}</p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-primary">+5 см</p>
          <p className="text-[10px] text-ink-mute">{t("metricHeight")}</p>
        </div>
      </div>
      <div className="flex items-center gap-3 rounded-lg bg-background px-3 py-2.5">
        <div className="h-8 w-8 rounded-full bg-muted" />
        <div className="flex-1">
          <p className="text-sm font-medium text-foreground">Максим П.</p>
          <p className="text-xs text-ink-mute">{t("lastSession")}</p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-primary">+0.1с</p>
          <p className="text-[10px] text-ink-mute">{t("metricAirtime")}</p>
        </div>
      </div>
    </div>
  )
}

function FeedbackPreview() {
  const t = useTranslations("onboarding")
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-3 shadow-sm">
      <div className="relative aspect-video rounded-lg bg-muted overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          <Video className="h-6 w-6 text-ink-mute/40" />
        </div>
        {/* Timeline */}
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-border">
          <div className="h-full w-1/3 bg-primary" />
        </div>
        {/* Comment pin */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2">
          <div className="flex items-center gap-1.5 rounded-lg bg-primary px-2.5 py-1.5 shadow-lg">
            <MessageSquare className="h-3 w-3 text-primary-foreground" />
            <span className="text-[10px] font-medium text-primary-foreground">
              {t("feedbackComment")}
            </span>
          </div>
          <div className="mx-auto h-2 w-2 rotate-45 bg-primary -mt-1" />
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center">
          <MessageSquare className="h-3 w-3 text-primary" />
        </div>
        <span className="text-xs text-ink-mute">{t("feedbackToday")}</span>
      </div>
    </div>
  )
}

function MusicPreview() {
  const t = useTranslations("onboarding")
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-4 shadow-sm space-y-3">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
          <Music className="h-5 w-5 text-primary" />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">program_music.mp3</p>
          <p className="text-xs text-ink-mute">{t("musicAnalyzed")}</p>
        </div>
      </div>
      {/* Waveform */}
      <div className="flex items-center gap-[2px] h-10">
        {Array.from({ length: 40 }).map((_, i) => {
          const h = 30 + Math.sin(i * 0.5) * 20 + Math.random() * 20
          return (
            <div
              key={i}
              className={cn(
                "flex-1 rounded-full",
                i > 25 && i < 32 ? "bg-primary" : "bg-primary/20",
              )}
              style={{ height: `${h}%` }}
            />
          )
        })}
      </div>
      <div className="flex gap-2">
        <div className="rounded-lg bg-primary/10 px-2.5 py-1">
          <span className="text-xs font-medium text-primary">124 BPM</span>
        </div>
        <div className="rounded-lg bg-muted px-2.5 py-1">
          <span className="text-xs text-ink-mute">Fm</span>
        </div>
        <div className="rounded-lg bg-muted px-2.5 py-1">
          <span className="text-xs text-ink-mute">4/4</span>
        </div>
      </div>
    </div>
  )
}

function TimelinePreview() {
  const t = useTranslations("onboarding")
  const elements = [
    { name: "2A", time: "0:12", color: "bg-primary" },
    { name: "StSq", time: "0:34", color: "bg-primary/40" },
    { name: "3F", time: "1:05", color: "bg-primary" },
    { name: "ChSq", time: "1:28", color: "bg-primary/40" },
  ]
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-4 shadow-sm space-y-3">
      <p className="text-xs font-medium text-ink-mute">{t("timelineLabel")}</p>
      <div className="relative">
        <div className="absolute left-3 top-0 bottom-0 w-px bg-border" />
        <div className="space-y-2">
          {elements.map(el => (
            <div key={el.name} className="flex items-center gap-3 pl-1">
              <div className={cn("h-2 w-2 rounded-full shrink-0 z-10", el.color)} />
              <div className="flex-1 flex items-center justify-between rounded-lg bg-background px-3 py-2">
                <span className="text-sm font-medium text-foreground">{el.name}</span>
                <span className="text-xs text-ink-mute">{el.time}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      <button
        type="button"
        className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-hairline py-2 text-xs text-ink-mute hover:bg-accent transition-colors"
      >
        <ChevronRight className="h-3 w-3" />
        {t("addElement")}
      </button>
    </div>
  )
}

function RinkPreview() {
  const t = useTranslations("onboarding")
  return (
    <div className="mx-auto w-full max-w-[280px] rounded-xl border border-hairline bg-card p-4 shadow-sm space-y-3">
      <p className="text-xs font-medium text-ink-mute">{t("rinkLabel")}</p>
      <div className="relative aspect-[2/1] rounded-lg bg-canvas-soft/30 border border-hairline overflow-hidden">
        {/* Rink rectangle */}
        <svg
          className="absolute inset-2 w-[calc(100%-16px)] h-[calc(100%-16px)]"
          viewBox="0 0 200 100"
          aria-hidden="true"
        >
          <title>Rink diagram</title>
          <rect
            x="0"
            y="0"
            width="200"
            height="100"
            rx="30"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            className="text-border"
          />
          <line
            x1="100"
            y1="0"
            x2="100"
            y2="100"
            stroke="currentColor"
            strokeWidth="0.5"
            strokeDasharray="4 2"
            className="text-border"
          />
          <circle
            cx="100"
            cy="50"
            r="8"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            className="text-border"
          />
          {/* Trajectory */}
          <path
            d="M 30 70 Q 60 30, 100 50 T 170 40"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            className="text-primary"
          />
          {/* Entry/exit markers */}
          <circle cx="30" cy="70" r="3" className="fill-primary" />
          <circle cx="170" cy="40" r="3" className="fill-primary" />
        </svg>
        <div className="absolute bottom-2 left-2 flex gap-1.5">
          <div className="flex items-center gap-1 rounded bg-background/80 px-1.5 py-0.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
            <span className="text-[9px] text-ink-mute">{t("rinkEntry")}</span>
          </div>
          <div className="flex items-center gap-1 rounded bg-background/80 px-1.5 py-0.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
            <span className="text-[9px] text-ink-mute">{t("rinkExit")}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Tour config ─── */

interface Slide {
  title: string
  subtitle: string
  preview: React.FC
}

function getSlides(role: UserRole, t: (key: string) => string): Slide[] {
  return [
    {
      title: t(`slides.${role}.0.title`),
      subtitle: t(`slides.${role}.0.subtitle`),
      preview: role === "skater" ? UploadPreview : role === "coach" ? InvitePreview : MusicPreview,
    },
    {
      title: t(`slides.${role}.1.title`),
      subtitle: t(`slides.${role}.1.subtitle`),
      preview:
        role === "skater"
          ? MetricsPreview
          : role === "coach"
            ? CoachDashboardPreview
            : TimelinePreview,
    },
    {
      title: t(`slides.${role}.2.title`),
      subtitle: t(`slides.${role}.2.subtitle`),
      preview:
        role === "skater" ? ProgressPreview : role === "coach" ? FeedbackPreview : RinkPreview,
    },
  ]
}

const SLIDE_ICONS = [Video, BarChart3, TrendingUp]

export function TourSlider({ role, onComplete, onSkip }: TourSliderProps) {
  const [current, setCurrent] = useState(0)
  const t = useTranslations("onboarding")
  const slides = getSlides(role, t)
  const CurrentIcon = SLIDE_ICONS[current]
  const CurrentPreview = slides[current].preview

  const next = () => {
    if (current < slides.length - 1) {
      setCurrent((c: number) => c + 1)
    } else {
      onComplete()
    }
  }

  return (
    <div className="flex min-h-[dvh] flex-col items-center justify-center px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-md sm:max-w-lg">
        {/* Header */}
        <div className="mb-4 flex items-center justify-end sm:mb-6">
          <button
            type="button"
            onClick={onSkip}
            className="text-sm text-ink-mute hover:text-foreground transition-colors"
          >
            {t("skip")}
          </button>
        </div>

        {/* Progress dots */}
        <div className="mb-6 flex items-center justify-center gap-2 sm:mb-8">
          {slides.map((_, i) => (
            <div
              key={i}
              className={cn(
                "h-2 rounded-full transition-all duration-300",
                i === current ? "w-6 bg-primary" : "w-2 bg-border",
              )}
            />
          ))}
        </div>

        {/* Slide content */}
        <div className="mb-6 sm:mb-8">
          <div className="mb-5 text-center sm:mb-6">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-[1rem] bg-primary/5 sm:mb-5 sm:h-16 sm:w-16">
              <CurrentIcon className="h-6 w-6 text-primary sm:h-7 sm:w-7" />
            </div>
            <h2 className="mb-2 text-xl font-medium tracking-tight text-foreground sm:text-2xl">
              {slides[current].title}
            </h2>
            <p className="text-sm text-ink-mute leading-relaxed sm:text-base">
              {slides[current].subtitle}
            </p>
          </div>

          {/* Interactive preview */}
          <div className="px-2 sm:px-0">
            <CurrentPreview />
          </div>
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between px-2 sm:px-0">
          <button
            type="button"
            onClick={() => setCurrent((c: number) => Math.max(0, c - 1))}
            disabled={current === 0}
            className="text-sm font-medium text-ink-mute hover:text-foreground transition-colors disabled:opacity-30"
          >
            {t("back")}
          </button>
          <button
            type="button"
            onClick={next}
            className="h-11 rounded-full bg-primary px-8 text-sm font-medium text-primary-foreground transition-all duration-200 hover:scale-[0.98] hover:bg-primary-deep active:scale-[0.96]"
          >
            {current < slides.length - 1 ? t("next") : t("start")}
          </button>
        </div>
      </div>
    </div>
  )
}
