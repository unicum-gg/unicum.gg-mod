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
 *   { "height": 12, "cell": 6, "margin": 1, "cells": { "0": 6, "%": 9, ... },
 *     "digits": { "0": [[a, ...] x 12 rows] x 8 cols ...},
 *     "left": [[...]], "right": [[...]] }
 * `cells` is each glyph's own width: digits are tabular and share one cell,
 * a full stop and a percent sign are not.
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

// The corner tag the settings window's preview stamps on a badge: the same
// face, small enough to sit inside the badge's own 12px without making it
// any bigger. Capitals and digits only -- a tag is a code, WNX or WR, and a
// code set in mixed case reads as a word that has been cut short.
const CAPTION_HEIGHT = 8
const CAPTION_SIZE = 7
const CAPTION_BASELINE = 6.2
const CAPTION_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

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

async function alpha(svg, width, height = HEIGHT) {
  const { data, info } = await sharp(Buffer.from(svg), { density: 72 })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true })
  if (info.width !== width || info.height !== height) {
    throw new Error(`rendered ${info.width}x${info.height}, expected ${width}x${height}`)
  }
  const rows = []
  for (let y = 0; y < height; y++) {
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
  const digits = {}
  const cells = {}
  // The digits are tabular in this face, so they all sit in one 6px cell and
  // a badge stays a grid. A full stop, a percent sign and the thousands `k`
  // are not: forcing them into the same cell would either crop the percent
  // or leave a hole around the stop, so each carries the width its own
  // advance asks for.
  for (const char of '0123456789.%k') {
    const glyph = font.charToGlyph(char)
    const advance = (glyph.advanceWidth / font.unitsPerEm) * FONT_SIZE
    const cell = '0123456789'.includes(char) ? DIGIT_WIDTH : Math.ceil(advance)
    const width = cell + 2 * MARGIN
    const d = glyph.getPath(MARGIN + (cell - advance) / 2, BASELINE, FONT_SIZE).toPathData(2)
    digits[char] = await alpha(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${HEIGHT}"><path d="${d}" fill="#FFFFFF"/></svg>`,
      width,
    )
    cells[char] = cell
  }
  // The caption's own glyphs, each as wide as its own advance asks: these
  // are letters, and letters forced into one cell look like a ransom note.
  const captionGlyphs = {}
  const captionCells = {}
  for (const char of CAPTION_CHARS) {
    const glyph = font.charToGlyph(char)
    const advance = (glyph.advanceWidth / font.unitsPerEm) * CAPTION_SIZE
    const cell = Math.max(1, Math.ceil(advance))
    const width = cell + 2 * MARGIN
    const d = glyph
      .getPath(MARGIN + (cell - advance) / 2, CAPTION_BASELINE, CAPTION_SIZE)
      .toPathData(2)
    captionGlyphs[char] = await alpha(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${CAPTION_HEIGHT}">` +
      `<path d="${d}" fill="#FFFFFF"/></svg>`,
      width,
      CAPTION_HEIGHT,
    )
    captionCells[char] = cell
  }
  // A space carries a width and no ink, like the one between thousands in a
  // figure: `_lay` walks past a character it holds no mask for, advancing by
  // its cell. Without this line a caption of two words ran into one.
  captionCells[' '] = Math.max(
    1,
    Math.round((font.charToGlyph(' ').advanceWidth / font.unitsPerEm) * CAPTION_SIZE),
  )
  // The corners from a narrow rounded rectangle: its outer columns. Twice,
  // because a captioned badge is a taller rectangle and the same radius on
  // a taller box is not the same mask stretched.
  const probe = 4 * CORNER
  const corners = async (height) => {
    const rect = await alpha(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${probe}" height="${height}">` +
      `<rect width="${probe}" height="${height}" rx="${RADIUS}" fill="#FFFFFF"/></svg>`,
      probe,
      height,
    )
    return [rect.map((row) => row.slice(0, CORNER)), rect.map((row) => row.slice(probe - CORNER))]
  }
  const [left, right] = await corners(HEIGHT)
  await writeFile(output, JSON.stringify({
    height: HEIGHT, cell: DIGIT_WIDTH, margin: MARGIN, cells, digits, left, right,
    caption: { height: CAPTION_HEIGHT, cells: captionCells, glyphs: captionGlyphs },
  }))
  console.log(`wrote ${output}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
