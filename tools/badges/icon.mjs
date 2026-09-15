/**
 * Renders the mod's icon for the modsListApi menu ("Open settings").
 *
 *   node icon.mjs
 *
 * assets/icon.svg is unicum.gg's own icon (the site serves it as /icon.svg).
 * The menu draws every icon at 50x50, like its default icon, so that is the
 * size rendered, centred on a transparent square: the shield is taller than
 * it is wide. Written to build/icon/unicum.png, which tools/install_dev.py
 * copies into the client.
 */
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import sharp from 'sharp'

const SIZE = 50
const REPO = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const SOURCE = join(REPO, 'assets', 'icon.svg')
const OUTPUT = join(REPO, 'build', 'icon', 'unicum.png')

mkdirSync(dirname(OUTPUT), { recursive: true })
await sharp(SOURCE, { density: 300 })
  .resize(SIZE, SIZE, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
  .png()
  .toFile(OUTPUT)
console.log(`wrote ${OUTPUT}`)
