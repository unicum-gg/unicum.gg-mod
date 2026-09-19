/**
 * Renders the mod's icons from unicum.gg's own, assets/icon.svg (the site
 * serves it as /icon.svg), each centred on a transparent square:
 *
 *   build/icon/unicum.png                 50x50, the modsListApi menu, which
 *                                         draws every icon at that size
 *   build/icon/tankButton/small.png       56x56  \
 *   build/icon/tankButton/large.png       64x64   } the hangar button, in the
 *   build/icon/tankButton/upscale.png    128x128 /  sizes the hangar's own use,
 *                                         in its glyphs' silver (metalMark)
 *   build/icon/twitch.png                 14x14, before Twitch messages in the
 *                                         battle chat (assets/brands/twitch.svg)
 *
 *   node icon.mjs
 *
 * tools/install_dev.py copies them into the client.
 */
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import sharp from 'sharp'

const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const SOURCE = join(REPO, 'assets', 'icon.svg')
const OUTPUT = join(REPO, 'build', 'icon')

const ICONS = [
  ['unicum.png', 50, SOURCE],
  ['tankButton/small.png', 56, metalMark()],
  ['tankButton/large.png', 64, metalMark()],
  ['tankButton/upscale.png', 128, metalMark()],
]

for (const [name, size, source] of ICONS) {
  const file = join(OUTPUT, name)
  mkdirSync(dirname(file), { recursive: true })
  const image = await sharp(source, { density: 600 })
    .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer()
  await sharp(source === SOURCE ? image : await brushed(image, size)).toFile(file)
  console.log(`wrote ${file}`)
}

/** The grain of the hangar's metal glyphs: faint noise, kept within the glyph. */
async function brushed(image, size) {
  const noise = await sharp({
    create: { width: size, height: size, channels: 3, noise: { type: 'gaussian', mean: 128, sigma: 40 } },
  }).blur(0.4).ensureAlpha(0.35).png().toBuffer()
  return sharp(image)
    .composite([{ input: noise, blend: 'soft-light' }, { input: image, blend: 'dest-in' }])
    .png()
    .toBuffer()
}

/**
 * The mark as the hangar's vehicle menu draws its own glyphs
 * (gui/maps/icons/hangar/vehicleMenu/<size>/*.png): brushed silver, lighter
 * at the top (about #D2D2D4) than at the bottom (#A1A3A6), with a thin dark
 * rim and its details cut in dark. Its colours are measured on the crew,
 * vehicle and customization icons. The outline is the mark's own outer edge;
 * the rim between it and the face, and the face's details, are drawn dark.
 */
function metalMark() {
  const svg = readFileSync(SOURCE, 'utf8')
  const outer = svg.match(/<path d="M316\.11[^"]*?z(M8\.304[^"]*?z)"/)[1]
  const face = svg.match(/<path d="(M316 56[^"]*)" fill="#fff"\/>/)[1]
  const details = svg.match(/<g fill="#f25322">([\s\S]*?)<\/g>/)[1]
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="-40 -40 1184.586 1591.305">
  <defs>
    <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#DCDCDE"/>
      <stop offset="0.45" stop-color="#C6C6C7"/>
      <stop offset="0.7" stop-color="#BBBBBC"/>
      <stop offset="1" stop-color="#9FA1A4"/>
    </linearGradient>
  </defs>
  <path d="${outer}" fill="url(#metal)" stroke="#141517" stroke-opacity="0.85" stroke-width="44" stroke-linejoin="round" paint-order="stroke"/>
  <path d="${face}" fill="none" stroke="#1B1C1E" stroke-opacity="0.9" stroke-width="22" stroke-linejoin="round"/>
  <g fill="#1B1C1E" fill-opacity="0.92">${details}</g>
</svg>`)
}

// The garage Twitch panel's own icons, drawn edge to edge in the hangar's own off-white (#EEEDE9, the colour of its text and icons)
// and shown at 16px; inlined in its script like the menu's
// (src/unicum/web/hangar/panel_icons).
const PANEL_ICONS = join(REPO, 'src', 'unicum', 'web', 'hangar', 'panel_icons')
const PHOSPHOR_BOLD = join(dirname(fileURLToPath(import.meta.url)), 'node_modules', '@phosphor-icons', 'core', 'assets', 'bold')
mkdirSync(PANEL_ICONS, { recursive: true })
for (const [name, source] of Object.entries({
  reset: 'arrow-counter-clockwise-bold.svg',
  collapse: 'minus-bold.svg',
  expand: 'plus-bold.svg',
  close: 'x-bold.svg',
  settings: 'gear-six-bold.svg',
})) {
  const svg = readFileSync(join(PHOSPHOR_BOLD, source), 'utf8').replace(/currentColor/g, '#EEEDE9')
  const file = join(PANEL_ICONS, `${name}.png`)
  await sharp(Buffer.from(svg), { density: 600 })
    .resize(32, 32, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(file)
  console.log(`wrote ${file}`)
}

// The garage's unicum.gg account card shows the site's own mark, in its colours.
{
  const file = join(PANEL_ICONS, 'unicum.png')
  await sharp(SOURCE, { density: 600 })
    .resize(32, 32, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(file)
  console.log(`wrote ${file}`)
}

{
  const file = join(OUTPUT, 'twitch.png')
  await sharp(join(REPO, 'assets', 'brands', 'twitch.svg'), { density: 600 })
    .resize(14, 14, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(file)
  console.log(`wrote ${file}`)
}

// The hangar menu's own icons, drawn like the hangar's menu icons: a white
// glyph of about 26px centred on a 64px square. The AI entries use the brand
// marks unicum.gg's "Open in" menu uses (assets/brands); the tabs the game
// has no icon for use Phosphor, the site's icon set. Kept in
// src/unicum/web/hangar/icons, next to the menu code that inlines them, so
// they reload with it.
const MENU_ICONS = join(REPO, 'src', 'unicum', 'web', 'hangar', 'icons')
const PHOSPHOR = join(dirname(fileURLToPath(import.meta.url)), 'node_modules', '@phosphor-icons', 'core', 'assets', 'fill')
const GLYPHS = {
  chatgpt: join(REPO, 'assets', 'brands', 'chatgpt.svg'),
  claude: join(REPO, 'assets', 'brands', 'claude.svg'),
  scira: join(REPO, 'assets', 'brands', 'scira.svg'),
  history: join(PHOSPHOR, 'clock-counter-clockwise-fill.svg'),
  videos: join(PHOSPHOR, 'video-camera-fill.svg'),
  community: join(PHOSPHOR, 'users-three-fill.svg'),
  share: join(PHOSPHOR, 'share-network-fill.svg'),
}
mkdirSync(MENU_ICONS, { recursive: true })
for (const [name, source] of Object.entries(GLYPHS)) {
  // Phosphor draws in currentColor; the hangar's icons are #FAF9F7.
  const svg = readFileSync(source, 'utf8').replace(/currentColor/g, '#FAF9F7')
  const glyph = await sharp(Buffer.from(svg), { density: 600 })
    .resize(26, 26, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toBuffer()
  const file = join(MENU_ICONS, `${name}.png`)
  await sharp({ create: { width: 64, height: 64, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } } })
    .composite([{ input: glyph, gravity: 'center' }])
    .png()
    .toFile(file)
  console.log(`wrote ${file}`)
}
