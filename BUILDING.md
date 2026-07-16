# Frontend build with Bun

The frontend toolchain uses Bun for dependency management and bundling. npm and
esbuild are not part of the build pipeline.

## Prerequisite

Install Bun 1.3.14 or newer. On Windows with Scoop:

```powershell
scoop install bun
bun --version
```

## Install and build

From the repository root:

```powershell
bun install --frozen-lockfile
bun run typecheck
bun run build
```

`bun run build` type-checks the TypeScript sources and then uses Bun's native
bundler to generate:

- `src/pu_tool/web_static/app.js`
- `src/pu_tool/web_static/reminders.js`
- `src/pu_tool/web_static/reminders.css`

Commit generated static assets because the Python package serves them directly.
Use `bun.lock` as the only JavaScript dependency lockfile.
