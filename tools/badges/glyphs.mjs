/**
 * The pieces a rating badge is drawn from in the client (src/unicum/badge_png.py):
 * each digit's coverage in its cell, and the rounded corners' coverage, as
 * alpha masks rendered here once with the same font, sizes and rasteriser the
 * whole set of badges used to be rendered with. A badge is a fixed grid (digits in 6px
 * cells, a 2px gap between thousands, 3px padding, 12px high), so the client
 * lays the masks side by side and gets the same pixels, without the 30 000
 * images the whole set took.
 *
 *   npm install && node glyphs.mjs
 *
 * writes src/unicum/badge_glyphs.json:
 *   { "height": 12, "cell": 6, "margin": 1, "digits": { "0": [[a, ...] x 12 rows] x 8 cols ...},
 *     "left": [[...]], "right": [[...]] }
 * Each mask is a list of rows of alpha values 0-255. A digit's mask is its cell
 * plus a 1px margin each side, since a glyph can reach past its cell.
 */
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import opentype from 'opentype.js'
import sharp from 'sharp'

const require = createRequire(import.meta.url)

// The badge grid, as src/unicum/badge_png.py lays it out.
const HEIGHT = 12
const DIGIT_WIDTH = 6
const RADIUS = 2
const FONT_SIZE = 10
const BASELINE = 9.5
const MARGIN = 1
const CORNER = 3

const output = path.resolve(import.meta.dirname, '..', '..', 'src', 'unicum', 'badge_glyphs.json')

async function loadFont() {
  const file = path.join(
    path.dirname(require.resolve('@fontsource/roboto-condensed/package.json')),
    'files',
    'roboto-condensed-latin-700-normal.woff',
  )
  const data = await readFile(file)
  return opentype.parse(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength))
}

async function alpha(svg, width) {
  const { data, info } = await sharp(Buffer.from(svg), { density: 72 })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true })
  if (info.width !== width || info.height !== HEIGHT) {
    throw new Error(`rendered ${info.width}x${info.height}, expected ${width}x${HEIGHT}`)
  }
  const rows = []
  for (let y = 0; y < HEIGHT; y++) {
    const row = []
    for (let x = 0; x < width; x++) {
      row.push(data[(y * width + x) * info.channels + 3])
    }
    rows.push(row)
  }
  return rows
}

async function main() {
  const font = await loadFont()
  const width = DIGIT_WIDTH + 2 * MARGIN
  const digits = {}
  for (const char of '0123456789') {
    const glyph = font.charToGlyph(char)
    const advance = (glyph.advanceWidth / font.unitsPerEm) * FONT_SIZE
    const d = glyph.getPath(MARGIN + (DIGIT_WIDTH - advance) / 2, BASELINE, FONT_SIZE).toPathData(2)
    digits[char] = await alpha(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${HEIGHT}"><path d="${d}" fill="#FFFFFF"/></svg>`,
      width,
    )
  }
  // The corners from a narrow rounded rectangle: its outer columns.
  const probe = 4 * CORNER
  const rect = await alpha(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${probe}" height="${HEIGHT}">` +
    `<rect width="${probe}" height="${HEIGHT}" rx="${RADIUS}" fill="#FFFFFF"/></svg>`,
    probe,
  )
  const left = rect.map((row) => row.slice(0, CORNER))
  const right = rect.map((row) => row.slice(probe - CORNER))
  await writeFile(output, JSON.stringify({ height: HEIGHT, cell: DIGIT_WIDTH, margin: MARGIN, digits, left, right }))
  console.log(`wrote ${output}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
