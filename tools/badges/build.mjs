/**
 * Renders the site's rating badge for every whole value, one PNG per number.
 *
 * A player name in the client is a Scaleform text field whose format is
 * re-applied to the whole text after it is set, so a <FONT COLOR> in it is
 * overwritten and a background is impossible. Images survive, so the badge
 * has to be an image.
 *
 * One image per number rather than pieces laid side by side: Scaleform leaves
 * a seam between adjacent inline images, whatever hspace says, and a badge
 * built from a cap, digits and a group space showed every join. So
 *
 *   badges/wnx/3323.png    "3 323" on the band 3323 falls in for WNX
 *
 * for every value from 0 to MAX_VALUE and every metric in METRICS. Colours
 * and band edges come from the site's own scale (GET /api/ratings/scales),
 * so rebuild when they change. Digits are drawn from Roboto Condensed Bold as
 * vector paths, so the output does not depend on the fonts installed here.
 *
 * The badge geometry is mirrored in src/unicum/badges.py (badge_width), which
 * has to state each image's width in its <IMG> tag.
 *
 *   npm install && npm run build -- --api http://localhost:3000
 */
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import opentype from 'opentype.js'
import sharp from 'sharp'

const require = createRequire(import.meta.url)

const METRICS = ['wn7', 'wn8', 'wnx']
const MAX_VALUE = 9999

const HEIGHT = 12
const PADDING = 3
const DIGIT_WIDTH = 6
const GROUP_WIDTH = 2
const RADIUS = 2
const FONT_SIZE = 10
const BASELINE = 9.5
const TEXT = '#FFFFFF'
const CONCURRENCY = 32

function arg(name, fallback) {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? process.argv[index + 1] : fallback
}

const apiBase = arg('api', 'https://unicum.gg').replace(/\/$/, '')
const outputDir = path.resolve(
  arg('out', path.join(import.meta.dirname, '..', '..', 'build', 'badges')),
)

async function loadFont() {
  const file = path.join(
    path.dirname(require.resolve('@fontsource/roboto-condensed/package.json')),
    'files',
    'roboto-condensed-latin-700-normal.woff',
  )
  const data = await readFile(file)
  return opentype.parse(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength))
}

async function loadScales() {
  const response = await fetch(`${apiBase}/api/ratings/scales`)
  if (!response.ok) {
    throw new Error(`GET ${apiBase}/api/ratings/scales answered ${response.status}`)
  }
  const scales = new Map()
  for (const scale of (await response.json()).scales ?? []) {
    scales.set(scale.scale, scale.bands ?? [])
  }
  for (const metric of METRICS) {
    if (!scales.get(metric)?.length) {
      throw new Error(`no ${metric} scale in the rating scales`)
    }
  }
  return scales
}

function bandColor(bands, value) {
  const band = bands.find((b) => (b.from === null || value >= b.from) && (b.to === null || value < b.to))
  return band?.hex ?? null
}

// "3323" -> ['3', ' ', '3', '2', '3'], grouped by thousands like the site.
function layout(value) {
  const digits = String(value)
  const out = []
  for (let i = 0; i < digits.length; i++) {
    if (i && (digits.length - i) % 3 === 0) out.push(' ')
    out.push(digits[i])
  }
  return out
}

function badge(font, value, hex) {
  const chars = layout(value)
  const inner = chars.reduce((w, c) => w + (c === ' ' ? GROUP_WIDTH : DIGIT_WIDTH), 0)
  const width = inner + 2 * PADDING
  let x = PADDING
  let paths = ''
  for (const char of chars) {
    if (char === ' ') {
      x += GROUP_WIDTH
      continue
    }
    const glyph = font.charToGlyph(char)
    const advance = (glyph.advanceWidth / font.unitsPerEm) * FONT_SIZE
    paths += glyph.getPath(x + (DIGIT_WIDTH - advance) / 2, BASELINE, FONT_SIZE).toPathData(2)
    x += DIGIT_WIDTH
  }
  return Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${HEIGHT}">` +
    `<rect width="${width}" height="${HEIGHT}" rx="${RADIUS}" fill="${hex}"/>` +
    `<path d="${paths}" fill="${TEXT}"/></svg>`,
  )
}

async function main() {
  const [font, scales] = await Promise.all([loadFont(), loadScales()])

  // Rebuilt from scratch: nothing from an older layout may ship alongside.
  await rm(outputDir, { recursive: true, force: true })

  for (const metric of METRICS) {
    const dir = path.join(outputDir, metric)
    await mkdir(dir, { recursive: true })
    const bands = scales.get(metric)
    const values = Array.from({ length: MAX_VALUE + 1 }, (_, v) => v)
    for (let i = 0; i < values.length; i += CONCURRENCY) {
      await Promise.all(values.slice(i, i + CONCURRENCY).map(async (value) => {
        const hex = bandColor(bands, value)
        if (!hex) return
        const png = await sharp(badge(font, value, hex), { density: 72 })
          .png({ palette: true, compressionLevel: 9 }).toBuffer()
        await writeFile(path.join(dir, `${value}.png`), png)
      }))
    }
    console.log(`${metric}: ${values.length} badges`)
  }
  console.log(`wrote badges to ${outputDir} from ${apiBase}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
