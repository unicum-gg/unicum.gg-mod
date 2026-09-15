/**
 * Renders the mod's icons from unicum.gg's own, assets/icon.svg (the site
 * serves it as /icon.svg), each centred on a transparent square:
 *
 *   build/icon/unicum.png                 50x50, the modsListApi menu, which
 *                                         draws every icon at that size
 *   build/icon/tankButton/small.png       56x56  \
 *   build/icon/tankButton/large.png       64x64   } the hangar button, in the
 *   build/icon/tankButton/upscale.png    128x128 /  sizes the hangar's own use
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
  ['unicum.png', 50],
  ['tankButton/small.png', 56],
  ['tankButton/large.png', 64],
  ['tankButton/upscale.png', 128],
]

for (const [name, size] of ICONS) {
  const file = join(OUTPUT, name)
  mkdirSync(dirname(file), { recursive: true })
  await sharp(SOURCE, { density: 600 })
    .resize(size, size, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
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
