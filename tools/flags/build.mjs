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
 * The `s` size is natively 16x12, which is the line height we want, so this
 * is a format change and not a resize.
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
    const png = await sharp(path.join(flagpackRoot, file), { density: 384 })
      .resize(16, 12, { fit: 'fill' })
      .png({ compressionLevel: 9 })
      .toBuffer()
    await writeFile(path.join(outputDir, `${code}.png`), png)
    written += 1
  }

  console.log(`${written} flags -> ${outputDir}`)
}

await main()
