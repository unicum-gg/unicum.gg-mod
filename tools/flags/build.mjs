/**
 * Rasterises Flagpack SVGs into the PNGs the Scaleform UI needs.
 *
 * The battle and roster name fields resolve <IMG SRC> through the client's
 * resource tree and nothing else. A URL there is looked up as a SWF export
 * name, never fetched -- the client logs
 *
 *   ProcessImageTags: can't find a resource for export name 'https://...'
 *
 * and no request is made. So flags cannot be served from unicum.gg for those
 * surfaces the way they are for the web views; they have to ship as files.
 *
 * Source is the same `react-flagpack` package the site installs, so the
 * flags in game are the flags on the site, from one version of one package.
 * The `s` size is natively 16x12, the height of the rating badge
 * (tools/badges), so this is a format change and not a resize. The corners
 * are rounded with the badge's radius, so a flag and a badge side by side
 * read as one set.
 *
 *   npm install && npm run build
 */
import { mkdir, readdir, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import sharp from 'sharp'

const require = createRequire(import.meta.url)

// Resolve through the package rather than a hardcoded path, so the version
// in package.json is the single source of truth.
const flagpackRoot = path.join(
  path.dirname(require.resolve('react-flagpack/package.json')),
  'dist',
  'flags',
  's',
)

const outputDir = path.resolve(
  process.argv[2] ?? path.join(import.meta.dirname, '..', '..', 'build', 'flags'),
)

// Alpha-2, plus subdivisions like GB-UKM that Flagpack uses and the site's
// language map depends on. The package also ships alpha-3 and numeric names
// for the same images; taking all three would triple the output for nothing.
const NAME = /^([A-Z]{2}(?:-[A-Z]{3})?)\.svg$/

const WIDTH = 16
const HEIGHT = 12
// tools/badges/build.mjs RADIUS.
const RADIUS = 2

// Keeps the flag inside a rounded rectangle, and nothing of its corners.
const CORNERS = Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" width="${WIDTH}" height="${HEIGHT}">` +
  `<rect width="${WIDTH}" height="${HEIGHT}" rx="${RADIUS}" fill="#fff"/></svg>`,
)

async function main() {
  const entries = (await readdir(flagpackRoot))
    .map((file) => [file, NAME.exec(file)])
    .filter(([, match]) => match !== null)
    .map(([file, match]) => ({ file, code: match[1] }))

  if (entries.length === 0) {
    throw new Error(`no flags found under ${flagpackRoot}`)
  }

  // Rebuilt from scratch: a code retired upstream must disappear here too,
  // rather than linger and ship in the next package.
  await rm(outputDir, { recursive: true, force: true })
  await mkdir(outputDir, { recursive: true })

  let written = 0
  for (const { file, code } of entries) {
    const flag = await sharp(path.join(flagpackRoot, file), { density: 384 })
      .resize(WIDTH, HEIGHT, { fit: 'fill' })
      .ensureAlpha()
      .toBuffer()
    const png = await sharp(flag)
      .composite([{ input: CORNERS, blend: 'dest-in' }])
      .png({ compressionLevel: 9 })
      .toBuffer()
    await writeFile(path.join(outputDir, `${code}.png`), png)
    written += 1
  }

  console.log(`${written} flags -> ${outputDir}`)
}

await main()
