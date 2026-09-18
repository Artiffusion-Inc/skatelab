"use client"

import { useId, useState } from "react"
import { useSearchParams } from "next/navigation"
import { useTranslations } from "@/i18n"

// Four schematic poses share a coordinate system so selection changes both pose and trace.
const POSES = [
  {
    head: [5, -91],
    body: "M5 -76 L-10 -44 L12 -22 L-8 0 M-10 -44 L-35 -22 L-48 -4 M0 -67 L-30 -54 L-48 -69 M0 -67 L27 -55 L44 -66",
  },
  {
    head: [0, -116],
    body: "M0 -101 L-5 -61 L2 -29 L4 0 M-5 -61 L-29 -38 L-42 -27 M0 -94 L-22 -113 L-17 -134 M0 -94 L24 -115 L19 -138",
  },
  {
    head: [0, -142],
    body: "M0 -127 L0 -87 L-9 -52 L2 -24 M0 -87 L13 -53 L2 -24 M0 -121 L-19 -104 L9 -100 M0 -121 L19 -104 L-9 -100",
  },
  {
    head: [-9, -93],
    body: "M-9 -78 L2 -43 L-13 -22 L2 0 M2 -43 L38 -35 L59 -16 M-6 -71 L-38 -69 L-57 -79 M-6 -71 L26 -68 L48 -84",
  },
]

export function SkaterTrace({
  active = 0,
  compact = false,
}: {
  active?: number
  compact?: boolean
}) {
  return (
    <svg
      viewBox="0 0 720 310"
      className={`public-trace ${compact ? "public-trace-compact" : ""}`}
      aria-hidden="true"
    >
      <defs>
        <pattern
          id={compact ? "review-grid" : "phase-grid"}
          width="36"
          height="36"
          patternUnits="userSpaceOnUse"
        >
          <path d="M36 0H0V36" fill="none" stroke="currentColor" strokeOpacity=".08" />
        </pattern>
      </defs>
      <rect width="720" height="310" fill={`url(#${compact ? "review-grid" : "phase-grid"})`} />
      <ellipse
        cx="360"
        cy="246"
        rx="319"
        ry="40"
        fill="none"
        stroke="currentColor"
        strokeOpacity=".12"
      />
      <path
        d="M40 248 C150 268 212 231 276 212 S414 180 477 214 S585 263 681 229"
        fill="none"
        stroke="currentColor"
        strokeOpacity=".28"
        strokeDasharray="5 8"
      />
      {POSES.map((pose, index) => (
        <g
          key={pose.body}
          transform={`translate(${95 + index * 175} 234)`}
          className="public-pose"
          data-selected={active === index}
        >
          <ellipse cy="13" rx="41" ry="5" className="public-pose-shadow" />
          <g className="public-pose-body">
            <circle cx={pose.head[0]} cy={pose.head[1]} r="11" fill="currentColor" />
            <path
              d={pose.body}
              fill="none"
              stroke="currentColor"
              strokeWidth="9"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path d="M-16 6H12" stroke="currentColor" strokeWidth="3" />
          </g>
          <text y="56" textAnchor="middle" fontSize="12" fill="currentColor">
            0{index + 1}
          </text>
        </g>
      ))}
    </svg>
  )
}

export function PhaseExplorer() {
  const t = useTranslations("publicSite")
  const phase = useSearchParams().get("phase")
  const active = phase && /^[1-4]$/.test(phase) ? Number(phase) - 1 : 0
  const descriptionId = useId()
  return (
    <div className="phase-workspace">
      <div className="phase-visual">
        <div className="public-scene-label">
          <span>SkateLab / {t("chapterPhases")}</span>
          <span aria-hidden="true">0{active + 1} / 04</span>
        </div>
        <fieldset className="phase-selector" aria-label={t("phaseLabel")}>
          <SkaterTrace active={active} />
          <div className="phase-controls">
            {POSES.map((pose, index) => (
              <button
                key={pose.body}
                type="button"
                aria-label={`0${index + 1} ${t(`phase${index}`)}`}
                aria-pressed={active === index}
                aria-controls={descriptionId}
                onClick={() => {
                  const url = new URL(window.location.href)
                  url.searchParams.set("phase", String(index + 1))
                  window.history.replaceState(null, "", url)
                }}
              >
                <span className="phase-hit-area" aria-hidden="true" />
                <span className="phase-choice-label">{t(`phase${index}`)}</span>
              </button>
            ))}
          </div>
        </fieldset>
        <p className="public-caption">{t("phaseCaption")}</p>
      </div>
      <div id={descriptionId} className="phase-description" aria-live="polite">
        <p className="public-eyebrow">{t(`phase${active}`)}</p>
        <h3>{t(`phaseCheck${active}`)}</h3>
        <p>{t(`phaseBody${active}`)}</p>
      </div>
      <noscript>
        <ol className="public-static-explanations">
          {POSES.map((pose, index) => (
            <li key={pose.body}>
              <strong>{t(`phase${index}`)}</strong>
              <p>{t(`phaseBody${index}`)}</p>
            </li>
          ))}
        </ol>
      </noscript>
    </div>
  )
}

export function ReviewWorkspace() {
  const t = useTranslations("publicSite")
  const [active, setActive] = useState(0)
  return (
    <figure className="public-review-workspace">
      <div className="public-review-toolbar">
        <span>{t("reviewWorkspace")}</span>
        <span>{t("reviewSelect")}</span>
      </div>
      <div className="public-review-layout">
        <div className="public-review-frame" data-mode={active}>
          <div className="public-scene-label">
            <span>{t("reviewFrame")}</span>
            <span aria-hidden="true">↗</span>
          </div>
          <SkaterTrace active={active === 0 ? 3 : active === 1 ? 1 : 0} compact />
          <div className="public-frame-annotation" key={active}>
            <span>0{active + 1}</span>
            {t(`reviewNote${active}`)}
          </div>
          <div className="public-filmstrip" aria-hidden="true">
            {[0, 1, 2, 3].map(index => (
              <span key={index} data-selected={index === (active === 0 ? 3 : active === 1 ? 1 : 0)}>
                {t(`phase${index}`)}
              </span>
            ))}
          </div>
        </div>
        <div className="public-review-note" aria-live="polite">
          <p className="public-eyebrow">{t(`reviewField${active}`)}</p>
          <h3>{t(`reviewPrompt${active}`)}</h3>
          <p>{t(`reviewBody${active}`)}</p>
          <div className="public-note-lines" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>
      <fieldset className="public-review-controls" aria-label={t("reviewLabel")}>
        {[0, 1, 2].map(index => (
          <button
            key={index}
            type="button"
            aria-pressed={active === index}
            onClick={() => setActive(index)}
          >
            <span>0{index + 1}</span>
            {t(`review${index}`)}
          </button>
        ))}
      </fieldset>
      <figcaption className="public-caption">{t("reviewCaption")}</figcaption>
      <noscript>
        <ol className="public-static-explanations">
          {[1, 2].map(index => (
            <li key={index}>
              <strong>{t(`reviewPrompt${index}`)}</strong>
              <p>{t(`reviewBody${index}`)}</p>
            </li>
          ))}
        </ol>
      </noscript>
    </figure>
  )
}

export function EquipmentDiagram() {
  const t = useTranslations("publicSite")
  const [active, setActive] = useState(0)
  return (
    <div className="equipment-diagram">
      <div className="public-scene-label">
        <span>{t("syncLabel")}</span>
        <span aria-hidden="true">↙ ↗</span>
      </div>
      <svg viewBox="0 0 600 400" aria-hidden="true" className="equipment-svg" data-source={active}>
        <ellipse
          cx="320"
          cy="302"
          rx="200"
          ry="54"
          fill="none"
          stroke="currentColor"
          strokeOpacity=".2"
        />
        <path d="M134 112L420 66L420 309L134 223Z" className="equipment-sightline" />
        <g
          transform="translate(310 286) scale(1.55)"
          fill="none"
          stroke="currentColor"
          strokeWidth="7"
          strokeLinecap="round"
        >
          <circle cy="-110" r="11" fill="currentColor" />
          <path d="M0 -95L-5 -51L9 -23L-5 0M-5 -51L32 -28L48 -20M0 -86L-33 -67L-48 -73M0 -86L29 -68L46 -76" />
        </g>
        <g
          className="equipment-camera"
          transform="translate(80 144)"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        >
          <rect width="66" height="40" rx="5" />
          <circle cx="33" cy="20" r="10" />
          <path d="M33 40V119M33 70L10 119M33 70L56 119" />
        </g>
        <g
          className="equipment-sensor"
          transform="translate(464 115)"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle r="39" />
          <path d="M-24 0H24M0 -24V24M-19 19L19 -19M18 -5L24 0L18 5M-5 -18L0 -24L5 -18" />
          <path d="M0 50V132H-110" strokeDasharray="5 6" />
        </g>
        <path
          className="equipment-signal"
          d="M410 348h15l6 -11 8 20 9 -28 8 19h70"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
      </svg>
      <div className="equipment-diagram-labels">
        <span data-selected={active === 0}>{t("cameraLabel")}</span>
        <span data-selected={active === 1}>{t("sensorLabel")}</span>
      </div>
      <fieldset className="public-review-controls" aria-label={t("sourceLabel")}>
        {[0, 1].map(index => (
          <button
            type="button"
            key={index}
            aria-pressed={active === index}
            onClick={() => setActive(index)}
          >
            {t(`source${index}`)}
          </button>
        ))}
      </fieldset>
      <p className="equipment-source-copy" aria-live="polite">
        {t(`sourceBody${active}`)}
      </p>
      <p className="public-caption">{t("equipmentCaption")}</p>
      <noscript>
        <p className="equipment-source-copy">{t("sourceBody1")}</p>
      </noscript>
    </div>
  )
}
