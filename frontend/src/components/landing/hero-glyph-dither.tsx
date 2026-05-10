"use client"

import { useRef, useMemo, useCallback, useEffect } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import * as THREE from "three"

const GLYPH_RAMP = " .:;+*#%@"
const GLYPH_COUNT = GLYPH_RAMP.length // 10
const GLYPH_PX = 48

const VERTEX = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

const FRAGMENT = /* glsl */ `
precision highp float;

uniform sampler2D uImage;
uniform sampler2D uAtlas;
uniform float uTime;
uniform vec2 uMouse;
uniform float uOpacity;
uniform vec2 uResolution;
uniform float uCellSize;

varying vec2 vUv;

// Luminance → glyph index (0=space … 9=@)
float glyphIndex(float lum) {
  float n = pow(clamp(lum, 0.0, 1.0), 0.85);
  return min(floor(n * 10.0), 9.0);
}

// Sample glyph atlas: single row, N columns
float sampleGlyph(vec2 localUv, float idx) {
  vec2 atlasUv = vec2(
    (idx + localUv.x) / 10.0,
    1.0 - localUv.y
  );
  return texture2D(uAtlas, atlasUv).r;
}

void main() {
  vec2 uv = vUv;
  vec2 offset = (uMouse - 0.5) * 0.02;

  // --- Layer 1: main glyph grid ---
  vec2 cells = uResolution / uCellSize;
  vec2 pos = uv * cells;
  vec2 id = floor(pos);
  vec2 local = fract(pos);

  vec2 centerUv = (id + 0.5) / cells + offset;
  vec4 tex = texture2D(uImage, centerUv);
  float lum = dot(tex.rgb, vec3(0.299, 0.587, 0.114));

  float idx1 = glyphIndex(lum);
  float g1 = sampleGlyph(local, idx1);

  // --- Layer 2: finer grid, parallax shift ---
  vec2 cells2 = cells * 1.5;
  vec2 pos2 = uv * cells2;
  vec2 id2 = floor(pos2);
  vec2 local2 = fract(pos2);

  vec2 centerUv2 = (id2 + 0.5) / cells2 + offset * 1.3;
  float lum2 = dot(texture2D(uImage, centerUv2).rgb, vec3(0.299, 0.587, 0.114));
  float g2 = sampleGlyph(local2, glyphIndex(lum2 * 0.8));

  // --- Color: midnight blue palette (DESIGN.md tokens) ---
  vec3 base   = vec3(0.086, 0.097, 0.157); // midnight blue
  vec3 accent = vec3(0.34, 0.33, 0.52);     // muted indigo
  vec3 glow   = vec3(0.78, 0.71, 0.98);     // violet soft

  vec3 c1 = mix(base, accent, g1 * 0.75);
  vec3 c2 = mix(base * 0.6, glow * 0.25, g2 * 0.35);
  vec3 color = c1 + c2 * 0.3;

  // Vignette
  float vig = 1.0 - smoothstep(0.4, 1.2, length((uv - 0.5) * 1.4));
  color *= mix(0.5, 1.0, vig);

  // Scanline
  color += sin(uv.y * uResolution.y * 1.5) * 0.015;

  // Shimmer
  color += sin(uTime * 0.3 + uv.x * 8.0) * 0.008;

  gl_FragColor = vec4(color, uOpacity);
}
`

function createGlyphAtlas(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas")
  canvas.width = GLYPH_COUNT * GLYPH_PX
  canvas.height = GLYPH_PX
  const ctx = canvas.getContext("2d")
  if (!ctx) return new THREE.CanvasTexture(canvas)

  ctx.fillStyle = "black"
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  ctx.fillStyle = "white"
  ctx.font = `bold ${GLYPH_PX * 0.8}px "Courier New", monospace`
  ctx.textAlign = "center"
  ctx.textBaseline = "middle"

  for (let i = 0; i < GLYPH_COUNT; i++) {
    ctx.fillText(GLYPH_RAMP[i], i * GLYPH_PX + GLYPH_PX / 2, GLYPH_PX / 2)
  }

  const tex = new THREE.CanvasTexture(canvas)
  tex.minFilter = THREE.LinearFilter
  tex.magFilter = THREE.LinearFilter
  tex.needsUpdate = true
  return tex
}

interface GlyphDitherCanvasProps {
  imageUrl: string
  className?: string
  opacity?: number
}

function DitherPlane({ imageUrl, opacity }: { imageUrl: string; opacity: number }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const mouseRef = useRef({ x: 0.5, y: 0.5 })
  const { viewport } = useThree()

  const imageTexture = useMemo(() => {
    const tex = new THREE.TextureLoader().load(imageUrl)
    tex.minFilter = THREE.LinearFilter
    tex.magFilter = THREE.LinearFilter
    return tex
  }, [imageUrl])

  const glyphAtlas = useMemo(() => createGlyphAtlas(), [])

  const uniforms = useMemo(
    () => ({
      uImage: { value: imageTexture },
      uAtlas: { value: glyphAtlas },
      uTime: { value: 0 },
      uMouse: { value: new THREE.Vector2(0.5, 0.5) },
      uOpacity: { value: opacity },
      uResolution: { value: new THREE.Vector2(800, 1000) },
      uCellSize: { value: 16.0 },
    }),
    [imageTexture, glyphAtlas, opacity],
  )

  const handlePointerMove = useCallback((e: MouseEvent) => {
    mouseRef.current = {
      x: e.clientX / window.innerWidth,
      y: 1.0 - e.clientY / window.innerHeight,
    }
  }, [])

  useFrame(({ clock }) => {
    if (meshRef.current) {
      const mat = meshRef.current.material as THREE.ShaderMaterial
      mat.uniforms.uTime.value = clock.getElapsedTime()
      mat.uniforms.uMouse.value.set(mouseRef.current.x, mouseRef.current.y)
      mat.uniforms.uResolution.value.set(window.innerWidth, window.innerHeight)
    }
  })

  useEffect(() => {
    window.addEventListener("pointermove", handlePointerMove)
    return () => window.removeEventListener("pointermove", handlePointerMove)
  }, [handlePointerMove])

  return (
    <mesh ref={meshRef} scale={[viewport.width, viewport.height, 1]}>
      <planeGeometry args={[1, 1]} />
      <shaderMaterial
        vertexShader={VERTEX}
        fragmentShader={FRAGMENT}
        uniforms={uniforms}
        transparent
      />
    </mesh>
  )
}

export function GlyphDitherCanvas({ imageUrl, className, opacity = 1 }: GlyphDitherCanvasProps) {
  return (
    <div className={className}>
      <Canvas
        gl={{ antialias: false, alpha: true }}
        camera={{ position: [0, 0, 1] }}
        dpr={[1, 1.5]}
        style={{ width: "100%", height: "100%" }}
      >
        <DitherPlane imageUrl={imageUrl} opacity={opacity} />
      </Canvas>
    </div>
  )
}
