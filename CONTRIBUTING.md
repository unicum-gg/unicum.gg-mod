# Contributing

Read [`AGENTS.md`](./AGENTS.md) first. It contains the non-obvious rules that matter for safe changes, above all how hot reload stays safe.

## Setup

Follow the Development section of [`README.md`](./README.md): rasterise the flags, build the title SWF, run `tools/install_dev.py`, start the client once. After that, saving a file under `src/` reloads the mod in place.

## Validation

```bash
python2.7 tools/selftest.py
```

Run it before every commit, and look at `game.log` after the change has reloaded in the client.

## Commit and PR Titles

Use the onRuntime gitmoji commit convention for every commit and PR title:

```text
<gitmoji> <type> <description> [(#<issue>)]
```

Reference: https://onruntime.com/docs/gitmoji

Rules:

- Use a lowercase, imperative description.
- Keep each commit to one logical change.
- Use exactly one of these types: `add`, `fix`, `improve`, `update`, `remove`, `refactor`, `rename`, `move`, `upgrade`, `downgrade`, `release`.
- Do not derive the type from the gitmoji name.
- Do not add signatures, generated-by notices, or co-author footers.

Examples:

```text
✨ add player wnx to the skirmish room
🐛 fix raw img markup in the battle damage panel
```
