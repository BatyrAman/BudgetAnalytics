# Third-Party Notices

BudgetAnalytics includes or depends on third-party software, fonts and container images. Each one is licensed by its own authors under the terms listed below. This file is an inventory compiled from package metadata and license files; it does **not** relicense any third-party component.

- **Generated:** 2026-11-20, from the lock files in the repository (`frontend/pnpm-lock.yaml`, `backend/requirements.txt`) and the installed packages.
- **"License (declared)"** is the license stated by the package itself (`package.json` `license` field, Python `License-Expression`/`License` metadata). License files were read for every direct dependency and for every non-permissive or unusual entry; see [docs/legal/LICENSE_AUDIT.md](docs/legal/LICENSE_AUDIT.md).
- **Platform note:** the frontend list was produced on Linux x64 (glibc). The Docker image (Alpine, musl) installs the `linuxmusl` variants of platform-specific packages instead, for example `@img/sharp-libvips-linuxmusl-x64` in place of `@img/sharp-libvips-linux-x64`. Their licenses are the same.

## 1. Items that need attention

| Component | Where | License | Why it matters |
|---|---|---|---|
| **Redis 7.4.8** (`redis:7-alpine` image) | `compose.yaml`, `backend/docker-compose.prod.yml` | **RSALv2 or SSPLv1** (source-available, not OSI open source), since Redis 7.4 | RSALv2 forbids making Redis functionality available to third parties as a service. Internal use as a rate-limit store is likely outside that restriction, but this needs legal confirmation. Redis 7.2.x is BSD-3-Clause, and BSD-licensed forks exist. See the license audit. |
| `@img/sharp-libvips-*` 1.3.4 | Frontend runtime image (optional dependency of `next` via `sharp`) | LGPL-3.0-or-later | A weak-copyleft library inside a distributed image. The app does not use image optimization (`images.unoptimized: true`), but the package is installed. Distributing the image carries LGPL obligations (license text, source availability, relinking). |
| `caniuse-lite` | Frontend (build tooling, browser data) | CC-BY-4.0 | Data licensed under Creative Commons Attribution; keep attribution. |
| `certifi` | Backend image | MPL-2.0 | File-level copyleft; used unmodified, no extra obligation beyond keeping the notice. |
| `@modelcontextprotocol/*`, other `shadcn` CLI dependencies | Frontend runtime tree | Apache-2.0 / MIT | They come from `shadcn` being a production dependency, although the app only imports its CSS file. Not a license conflict; a supply-chain and size concern. |

## 2. Fonts and icons

| Asset | License | Attribution / notice |
|---|---|---|
| **Inter** typeface (loaded with `next/font/google`, self-hosted at build time) | SIL Open Font License 1.1, © The Inter Project Authors | Do not sell the font on its own; keep the OFL notice when redistributing font files. <https://github.com/rsms/inter> |
| **Lucide** icons (`lucide-react` 1.75.0) | ISC, © Lucide Icons and Contributors. Icons derived from Feather are MIT, © Cole Bemis. | Keep both copyright and permission notices (they ship in `node_modules/lucide-react/LICENSE`). <https://lucide.dev> |

Details and the status of the files in `frontend/public/`: [docs/legal/ASSET_ATTRIBUTION.md](docs/legal/ASSET_ATTRIBUTION.md).

## 3. Container base images

These images are pulled at build or run time. Each contains an operating system and tools under many licenses, including GPL. Publishing images built from them means redistributing those components.

| Image | Used by | Main license(s) of the main component |
|---|---|---|
| `python:3.12-slim` (Debian 13) | `backend/Dockerfile` | Python: PSF-2.0; Debian packages: various (including GPL) |
| `node:22-alpine` (Alpine 3.24) | `frontend/Dockerfile` | Node.js: MIT; Alpine packages: various (including GPL-2.0 BusyBox) |
| `postgres:16-alpine` (PostgreSQL 16.15) | `compose.yaml` | PostgreSQL License |
| `redis:7-alpine` (Redis 7.4.8) | `compose.yaml` | RSALv2 / SSPLv1 (see section 1) |

## 4. Development-only tools

These are used to build, lint and test, and are not part of the runtime images. The frontend has 394 development packages: 338 MIT, 22 Apache-2.0, 13 ISC, 9 BSD-2-Clause, 4 BlueOak-1.0.0, 3 MPL-2.0 (`axe-core`, `lightningcss`), 3 BSD-3-Clause, 1 CC-BY-4.0 (`caniuse-lite`), 1 CC0-1.0. Notable ones: TypeScript (Apache-2.0), Playwright (Apache-2.0, ships a NOTICE file), ESLint (MIT), Prettier (MIT), Vitest (MIT), Tailwind CSS (MIT). Backend development tools from `requirements-dev.txt` (pytest, Ruff, mypy, pip-audit) are not shipped in the image.

## 5. Attribution obligations in practice

- Permissive licenses (MIT, ISC, BSD, Apache-2.0, BlueOak, PSF, 0BSD, Unlicense) require keeping the copyright and license notices when the software is redistributed.
- Package managers keep them in `node_modules/*` and `site-packages/*.dist-info`, and those directories are included in the Docker images.
- None of the Apache-2.0 runtime dependencies listed below ships a `NOTICE` file, so there are no NOTICE contents to reproduce at present.
- If the project is distributed in another form (for example a bundled frontend without `node_modules`), these notices must be reproduced separately.

## 6. Full inventory

### A. Frontend runtime dependencies (production dependency tree, `pnpm licenses list --prod`)

259 packages.

| Package | Version | License (declared) | Source |
|---|---|---|---|
| `@babel/code-frame` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-code-frame> |
| `@babel/compat-data` | 7.29.7 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/core` | 7.29.13 | MIT | <https://babel.dev/docs/en/next/babel-core> |
| `@babel/generator` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-generator> |
| `@babel/helper-annotate-as-pure` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-helper-annotate-as-pure> |
| `@babel/helper-compilation-targets` | 7.29.13 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-create-class-features-plugin` | 7.29.13 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-globals` | 7.29.7 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-member-expression-to-functions` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-helper-member-expression-to-functions> |
| `@babel/helper-module-imports` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-helper-module-imports> |
| `@babel/helper-module-transforms` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-helper-module-transforms> |
| `@babel/helper-optimise-call-expression` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-helper-optimise-call-expression> |
| `@babel/helper-plugin-utils` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-helper-plugin-utils> |
| `@babel/helper-replace-supers` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-helper-replace-supers> |
| `@babel/helper-skip-transparent-expression-wrappers` | 7.29.13 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-string-parser` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-helper-string-parser> |
| `@babel/helper-validator-identifier` | 7.29.7 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-validator-option` | 7.29.7 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helpers` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-helpers> |
| `@babel/parser` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-parser> |
| `@babel/plugin-syntax-jsx` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-plugin-syntax-jsx> |
| `@babel/plugin-syntax-typescript` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-plugin-syntax-typescript> |
| `@babel/plugin-transform-modules-commonjs` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-plugin-transform-modules-commonjs> |
| `@babel/plugin-transform-typescript` | 7.29.9 | MIT | <https://babel.dev/docs/en/next/babel-plugin-transform-typescript> |
| `@babel/preset-typescript` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-preset-typescript> |
| `@babel/template` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-template> |
| `@babel/traverse` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-traverse> |
| `@babel/types` | 7.29.14 | MIT | <https://babel.dev/docs/en/next/babel-types> |
| `@dotenvx/dotenvx` | 1.75.1 | BSD-3-Clause | <https://github.com/dotenvx/dotenvx> |
| `@dotenvx/primitives` | 0.8.0 | BSD-3-Clause | <https://github.com/dotenvx/dotenvx> |
| `@img/colour` | 1.1.0 | MIT | <https://github.com/lovell/colour#readme> |
| `@img/sharp-libvips-linux-x64` | 1.3.4 | LGPL-3.0-or-later | <https://sharp.pixelplumbing.com> |
| `@img/sharp-linux-x64` | 0.35.5 | Apache-2.0 | <https://sharp.pixelplumbing.com> |
| `@jridgewell/gen-mapping` | 0.3.13 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/gen-mapping> |
| `@jridgewell/remapping` | 2.3.5 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/remapping> |
| `@jridgewell/resolve-uri` | 3.1.3 | MIT | <https://github.com/jridgewell/resolve-uri#readme> |
| `@jridgewell/sourcemap-codec` | 1.6.0 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/sourcemap-codec> |
| `@jridgewell/trace-mapping` | 0.3.31 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/trace-mapping> |
| `@modelcontextprotocol/core` | 2.4.0 | Apache-2.0 | <https://modelcontextprotocol.io> |
| `@modelcontextprotocol/server` | 2.4.0 | Apache-2.0 | <https://modelcontextprotocol.io> |
| `@next/env` | 16.4.6 | MIT | <https://github.com/vercel/next.js#readme> |
| `@next/swc-linux-x64-gnu` | 16.4.6 | MIT | <https://github.com/vercel/next.js#readme> |
| `@nodelib/fs.scandir` | 2.1.5 | MIT | <https://github.com/nodelib/nodelib/tree/master#readme> |
| `@nodelib/fs.stat` | 2.0.5 | MIT | <https://github.com/nodelib/nodelib/tree/master#readme> |
| `@nodelib/fs.walk` | 1.2.8 | MIT | <https://github.com/nodelib/nodelib/tree/master#readme> |
| `@reduxjs/toolkit` | 2.14.0 | MIT | <https://redux-toolkit.js.org> |
| `@sec-ant/readable-stream` | 0.4.1 | MIT | <https://github.com/Sec-ant/readable-stream> |
| `@shadcn/registry` | 0.2.1 | MIT | <https://ui.shadcn.com/docs/registry> |
| `@sindresorhus/merge-streams` | 4.0.0 | MIT | <https://github.com/sindresorhus/merge-streams#readme> |
| `@standard-schema/spec` | 1.1.0 | MIT | <https://standardschema.dev> |
| `@standard-schema/utils` | 0.3.0 | MIT | <https://github.com/standard-schema/standard-schema#readme> |
| `@swc/helpers` | 0.5.23 | Apache-2.0 | <https://swc.rs> |
| `@ts-morph/common` | 0.27.0 | MIT | <https://github.com/dsherret/ts-morph#readme> |
| `@types/d3-array` | 3.2.2 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-array> |
| `@types/d3-color` | 3.1.3 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-color> |
| `@types/d3-ease` | 3.0.2 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-ease> |
| `@types/d3-interpolate` | 3.0.4 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-interpolate> |
| `@types/d3-path` | 3.1.1 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-path> |
| `@types/d3-scale` | 4.0.9 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-scale> |
| `@types/d3-shape` | 3.2.0 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-shape> |
| `@types/d3-time` | 3.0.4 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-time> |
| `@types/d3-timer` | 3.0.2 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/d3-timer> |
| `@types/use-sync-external-store` | 0.0.6 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/use-sync-external-store> |
| `@types/validate-npm-package-name` | 4.0.2 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/validate-npm-package-name> |
| `ajv` | 8.20.0 | MIT | <https://ajv.js.org> |
| `ajv-formats` | 2.1.1 | MIT | <https://github.com/ajv-validator/ajv-formats#readme> |
| `ansi-colors` | 4.1.3 | MIT | <https://github.com/doowb/ansi-colors> |
| `ansi-regex` | 5.0.1, 6.6.0 | MIT | <https://github.com/chalk/ansi-regex#readme> |
| `ast-types` | 0.16.3 | MIT | <https://github.com/benjamn/ast-types> |
| `atomically` | 1.7.0 | MIT | <https://github.com/fabiospampinato/atomically#readme> |
| `balanced-match` | 4.0.4 | MIT | <https://github.com/juliangruber/balanced-match#readme> |
| `baseline-browser-mapping` | 2.11.38 | Apache-2.0 | <https://github.com/web-platform-dx/baseline-browser-mapping#readme> |
| `brace-expansion` | 5.0.13 | MIT | <https://github.com/juliangruber/brace-expansion#readme> |
| `braces` | 3.0.3 | MIT | <https://github.com/micromatch/braces> |
| `browserslist` | 4.29.6 | MIT | <https://github.com/browserslist/browserslist#readme> |
| `bundle-name` | 4.1.1 | MIT | <https://github.com/sindresorhus/bundle-name#readme> |
| `caniuse-lite` | 1.0.30001826 | CC-BY-4.0 | <https://github.com/browserslist/caniuse-lite#readme> |
| `chalk` | 5.6.2 | MIT | <https://github.com/chalk/chalk#readme> |
| `cli-cursor` | 5.0.0 | MIT | <https://github.com/sindresorhus/cli-cursor#readme> |
| `cli-spinners` | 2.9.2 | MIT | <https://github.com/sindresorhus/cli-spinners#readme> |
| `client-only` | 0.0.1 | MIT | <https://reactjs.org/> |
| `clsx` | 2.1.1 | MIT | <https://github.com/lukeed/clsx#readme> |
| `cn` | 0.2.6 | MIT | <https://github.com/shadcn-ui/cn#readme> |
| `code-block-writer` | 13.0.3 | MIT | <https://github.com/dsherret/code-block-writer#readme> |
| `commander` | 11.1.0, 14.0.3 | MIT | <https://github.com/tj/commander.js#readme> |
| `conf` | 10.2.0 | MIT | <https://github.com/sindresorhus/conf#readme> |
| `convert-source-map` | 2.0.0 | MIT | <https://github.com/thlorenz/convert-source-map> |
| `cross-spawn` | 7.0.6 | MIT | <https://github.com/moxystudio/node-cross-spawn> |
| `d3-array` | 3.2.5 | ISC | <https://d3js.org/d3-array/> |
| `d3-color` | 3.1.1 | ISC | <https://d3js.org/d3-color/> |
| `d3-ease` | 3.0.2 | BSD-3-Clause | <https://d3js.org/d3-ease/> |
| `d3-format` | 3.1.3 | ISC | <https://d3js.org/d3-format/> |
| `d3-interpolate` | 3.0.2 | ISC | <https://d3js.org/d3-interpolate/> |
| `d3-path` | 3.1.1 | ISC | <https://d3js.org/d3-path/> |
| `d3-scale` | 4.0.3 | ISC | <https://d3js.org/d3-scale/> |
| `d3-shape` | 3.2.1 | ISC | <https://d3js.org/d3-shape/> |
| `d3-time` | 3.1.1 | ISC | <https://d3js.org/d3-time/> |
| `d3-time-format` | 4.1.1 | ISC | <https://d3js.org/d3-time-format/> |
| `d3-timer` | 3.0.2 | ISC | <https://d3js.org/d3-timer/> |
| `debounce-fn` | 4.0.0 | MIT | <https://github.com/sindresorhus/debounce-fn#readme> |
| `debug` | 4.4.3 | MIT | <https://github.com/debug-js/debug#readme> |
| `decimal.js-light` | 2.5.1 | MIT | <https://github.com/MikeMcl/decimal.js-light#readme> |
| `dedent` | 1.7.2 | MIT | <https://github.com/dmnd/dedent> |
| `deepmerge` | 4.3.1 | MIT | <https://github.com/TehShrike/deepmerge> |
| `default-browser` | 5.5.1 | MIT | <https://github.com/sindresorhus/default-browser#readme> |
| `default-browser-id` | 5.0.1 | MIT | <https://github.com/sindresorhus/default-browser-id#readme> |
| `define-lazy-prop` | 2.0.0, 3.0.0 | MIT | <https://github.com/sindresorhus/define-lazy-prop#readme> |
| `dequal` | 2.0.3 | MIT | <https://github.com/lukeed/dequal#readme> |
| `detect-libc` | 2.1.2 | Apache-2.0 | <https://github.com/lovell/detect-libc#readme> |
| `diff` | 8.0.4 | BSD-3-Clause | <https://github.com/kpdecker/jsdiff#readme> |
| `dot-prop` | 6.0.1 | MIT | <https://github.com/sindresorhus/dot-prop#readme> |
| `dotenv` | 17.4.2 | BSD-2-Clause | <https://github.com/motdotla/dotenv#readme> |
| `electron-to-chromium` | 1.5.489 | ISC | <https://github.com/Kilian/electron-to-chromium#readme> |
| `emoji-regex` | 10.6.0 | MIT | <https://mths.be/emoji-regex> |
| `enquirer` | 2.4.1 | MIT | <https://github.com/enquirer/enquirer> |
| `env-paths` | 2.2.1 | MIT | <https://github.com/sindresorhus/env-paths#readme> |
| `es-toolkit` | 1.53.2 | MIT | <https://es-toolkit.dev> |
| `escalade` | 3.2.0 | MIT | <https://github.com/lukeed/escalade#readme> |
| `esprima` | 4.0.1 | BSD-2-Clause | <http://esprima.org> |
| `eventemitter3` | 5.0.4 | MIT | <https://github.com/primus/eventemitter3#readme> |
| `execa` | 5.1.1, 9.6.1 | MIT | <https://github.com/sindresorhus/execa#readme> |
| `fast-deep-equal` | 3.1.3 | MIT | <https://github.com/epoberezkin/fast-deep-equal#readme> |
| `fast-glob` | 3.3.3 | MIT | <https://github.com/mrmlnc/fast-glob#readme> |
| `fast-uri` | 3.1.9 | BSD-3-Clause | <https://github.com/fastify/fast-uri> |
| `fastq` | 1.20.3 | ISC | <https://github.com/mcollina/fastq#readme> |
| `fdir` | 6.5.0 | MIT | <https://github.com/thecodrr/fdir#readme> |
| `figures` | 6.1.0 | MIT | <https://github.com/sindresorhus/figures#readme> |
| `fill-range` | 7.1.1 | MIT | <https://github.com/jonschlinkert/fill-range> |
| `find-up` | 3.0.0 | MIT | <https://github.com/sindresorhus/find-up#readme> |
| `fs-extra` | 11.4.1 | MIT | <https://github.com/jprichardson/node-fs-extra> |
| `fuzzysort` | 3.1.0 | MIT | <https://github.com/farzher/fuzzysort#readme> |
| `gensync` | 1.0.0-beta.2 | MIT | <https://github.com/loganfsmyth/gensync> |
| `get-east-asian-width` | 1.7.0 | MIT | <https://github.com/sindresorhus/get-east-asian-width#readme> |
| `get-own-enumerable-keys` | 1.0.0 | MIT | <https://github.com/sindresorhus/get-own-enumerable-keys#readme> |
| `get-stream` | 6.0.1, 9.0.1 | MIT | <https://github.com/sindresorhus/get-stream#readme> |
| `glob-parent` | 5.1.2 | ISC | <https://github.com/gulpjs/glob-parent#readme> |
| `graceful-fs` | 4.2.12 | BlueOak-1.0.0 | <https://github.com/isaacs/node-graceful-fs#readme> |
| `human-signals` | 2.1.0, 8.0.1 | Apache-2.0 | <https://www.github.com/ehmicky/human-signals> |
| `ignore` | 5.3.2 | MIT | <https://github.com/kaelzhang/node-ignore#readme> |
| `immer` | 11.2.10 | MIT | <https://github.com/immerjs/immer#readme> |
| `internmap` | 2.0.3 | ISC | <https://github.com/mbostock/internmap/> |
| `ip-address` | 10.7.6 | MIT | <https://github.com/beaugunderson/ip-address#readme> |
| `is-docker` | 2.2.1, 3.0.0 | MIT | <https://github.com/sindresorhus/is-docker#readme> |
| `is-extglob` | 2.1.1 | MIT | <https://github.com/jonschlinkert/is-extglob> |
| `is-glob` | 4.0.3 | MIT | <https://github.com/micromatch/is-glob> |
| `is-in-ssh` | 1.0.0 | MIT | <https://github.com/sindresorhus/is-in-ssh#readme> |
| `is-inside-container` | 1.0.0 | MIT | <https://github.com/sindresorhus/is-inside-container#readme> |
| `is-interactive` | 2.0.0 | MIT | <https://github.com/sindresorhus/is-interactive#readme> |
| `is-number` | 7.0.0 | MIT | <https://github.com/jonschlinkert/is-number> |
| `is-obj` | 2.0.0, 3.0.0 | MIT | <https://github.com/sindresorhus/is-obj#readme> |
| `is-plain-obj` | 4.1.0 | MIT | <https://github.com/sindresorhus/is-plain-obj#readme> |
| `is-regexp` | 3.1.0 | MIT | <https://github.com/sindresorhus/is-regexp#readme> |
| `is-stream` | 2.0.1, 4.0.1 | MIT | <https://github.com/sindresorhus/is-stream#readme> |
| `is-unicode-supported` | 1.3.0, 2.1.0 | MIT | <https://github.com/sindresorhus/is-unicode-supported#readme> |
| `is-wsl` | 2.2.0, 3.1.1 | MIT | <https://github.com/sindresorhus/is-wsl#readme> |
| `isexe` | 2.0.0 | ISC | <https://github.com/isaacs/isexe#readme> |
| `isexe` | 3.1.5 | BlueOak-1.0.0 | <https://github.com/isaacs/isexe#readme> |
| `js-tokens` | 4.0.0 | MIT | <https://github.com/lydell/js-tokens#readme> |
| `jsesc` | 3.1.0 | MIT | <https://mths.be/jsesc> |
| `json-schema-traverse` | 1.0.0 | MIT | <https://github.com/epoberezkin/json-schema-traverse#readme> |
| `json-schema-typed` | 7.0.3 | BSD-2-Clause | <https://github.com/typeslick/json-schema-typed> |
| `json5` | 2.2.3 | MIT | <http://json5.org/> |
| `jsonfile` | 6.2.1 | MIT | <https://github.com/jprichardson/node-jsonfile#readme> |
| `kleur` | 3.0.3, 4.1.5 | MIT | <https://github.com/lukeed/kleur#readme> |
| `locate-path` | 3.0.0 | MIT | <https://github.com/sindresorhus/locate-path#readme> |
| `log-symbols` | 6.0.0 | MIT | <https://github.com/sindresorhus/log-symbols#readme> |
| `lru-cache` | 5.1.1 | ISC | <https://github.com/isaacs/node-lru-cache#readme> |
| `lucide-react` | 1.75.0 | ISC | <https://lucide.dev> |
| `merge-stream` | 2.0.0 | MIT | <https://github.com/grncdr/merge-stream#readme> |
| `merge2` | 1.4.1 | MIT | <https://github.com/teambition/merge2> |
| `micromatch` | 4.0.8 | MIT | <https://github.com/micromatch/micromatch> |
| `mimic-fn` | 2.1.0, 3.1.0 | MIT | <https://github.com/sindresorhus/mimic-fn#readme> |
| `mimic-function` | 5.0.1 | MIT | <https://github.com/sindresorhus/mimic-function#readme> |
| `minimatch` | 10.2.6 | BlueOak-1.0.0 | <https://github.com/isaacs/minimatch#readme> |
| `minimist` | 1.2.8 | MIT | <https://github.com/minimistjs/minimist> |
| `ms` | 2.1.3 | MIT | <https://github.com/vercel/ms#readme> |
| `nanoid` | 3.3.20 | MIT | <https://github.com/ai/nanoid#readme> |
| `next` | 16.4.6 | MIT | <https://nextjs.org> |
| `next-themes` | 0.4.6 | MIT | <https://github.com/pacocoursey/next-themes#readme> |
| `node-releases` | 2.0.65 | MIT | <https://github.com/chicoxyzzy/node-releases#readme> |
| `npm-run-path` | 4.0.1, 6.0.0 | MIT | <https://github.com/sindresorhus/npm-run-path#readme> |
| `object-treeify` | 1.1.33 | MIT | <https://github.com/blackflux/object-treeify#readme> |
| `onetime` | 5.1.2, 7.0.0 | MIT | <https://github.com/sindresorhus/onetime#readme> |
| `open` | 8.4.2, 11.0.4 | MIT | <https://github.com/sindresorhus/open#readme> |
| `ora` | 8.2.0 | MIT | <https://github.com/sindresorhus/ora#readme> |
| `p-limit` | 2.3.0 | MIT | <https://github.com/sindresorhus/p-limit#readme> |
| `p-locate` | 3.0.0 | MIT | <https://github.com/sindresorhus/p-locate#readme> |
| `p-try` | 2.2.0 | MIT | <https://github.com/sindresorhus/p-try#readme> |
| `parse-ms` | 4.0.0 | MIT | <https://github.com/sindresorhus/parse-ms#readme> |
| `path-browserify` | 1.0.1 | MIT | <https://github.com/browserify/path-browserify> |
| `path-exists` | 3.0.0 | MIT | <https://github.com/sindresorhus/path-exists#readme> |
| `path-key` | 3.1.1, 4.0.0 | MIT | <https://github.com/sindresorhus/path-key#readme> |
| `picocolors` | 1.1.1 | ISC | <https://github.com/alexeyraspopov/picocolors#readme> |
| `picomatch` | 2.3.2, 4.0.7 | MIT | <https://github.com/micromatch/picomatch> |
| `pkg-up` | 3.1.0 | MIT | <https://github.com/sindresorhus/pkg-up#readme> |
| `postcss` | 8.5.23, 8.5.33 | MIT | <https://postcss.org/> |
| `postcss-selector-parser` | 7.2.1 | MIT | <https://github.com/postcss/postcss-selector-parser> |
| `powershell-utils` | 0.2.1 | MIT | <https://github.com/sindresorhus/powershell-utils#readme> |
| `pretty-ms` | 9.3.1 | MIT | <https://github.com/sindresorhus/pretty-ms#readme> |
| `prompts` | 2.4.2 | MIT | <https://github.com/terkelg/prompts#readme> |
| `queue-microtask` | 1.2.3 | MIT | <https://github.com/feross/queue-microtask> |
| `react` | 19.3.1 | MIT | <https://react.dev/> |
| `react-dom` | 19.3.1 | MIT | <https://react.dev/> |
| `react-is` | 16.13.1 | MIT | <https://reactjs.org/> |
| `react-redux` | 9.3.1 | MIT | <https://github.com/reduxjs/react-redux> |
| `recast` | 0.23.21 | MIT | <http://github.com/benjamn/recast> |
| `recharts` | 3.11.0 | MIT | <https://github.com/recharts/recharts> |
| `redux` | 5.0.1 | MIT | <http://redux.js.org> |
| `redux-thunk` | 3.1.0 | MIT | <https://github.com/reduxjs/redux-thunk> |
| `require-from-string` | 2.0.2 | MIT | <https://github.com/floatdrop/require-from-string#readme> |
| `reselect` | 5.2.0 | MIT | <https://github.com/reduxjs/reselect#readme> |
| `restore-cursor` | 5.1.0 | MIT | <https://github.com/sindresorhus/restore-cursor#readme> |
| `reusify` | 1.1.0 | MIT | <https://github.com/mcollina/reusify#readme> |
| `run-applescript` | 7.1.0 | MIT | <https://github.com/sindresorhus/run-applescript#readme> |
| `run-parallel` | 1.2.0 | MIT | <https://github.com/feross/run-parallel> |
| `scheduler` | 0.28.0 | MIT | <https://react.dev/> |
| `semver` | 6.3.2, 7.8.6 | ISC | <https://github.com/npm/node-semver#readme> |
| `server-only` | 0.0.1 | MIT | <https://reactjs.org/> |
| `shadcn` | 4.23.0 | MIT | <https://ui.shadcn.com> |
| `sharp` | 0.35.5 | Apache-2.0 | <https://sharp.pixelplumbing.com> |
| `shebang-command` | 2.0.0 | MIT | <https://github.com/kevva/shebang-command#readme> |
| `shebang-regex` | 3.0.0 | MIT | <https://github.com/sindresorhus/shebang-regex#readme> |
| `signal-exit` | 3.0.7, 4.1.0 | ISC | <https://github.com/tapjs/signal-exit#readme> |
| `sisteransi` | 1.0.5 | MIT | <https://github.com/terkelg/sisteransi#readme> |
| `smart-buffer` | 4.2.0 | MIT | <https://github.com/JoshGlazebrook/smart-buffer/> |
| `socks` | 2.8.10 | MIT | <https://github.com/JoshGlazebrook/socks/> |
| `sonner` | 2.0.8 | MIT | <https://sonner.emilkowal.ski/> |
| `source-map` | 0.6.1 | BSD-3-Clause | <https://github.com/mozilla/source-map> |
| `source-map-js` | 1.2.2 | BSD-3-Clause | <https://github.com/7rulnik/source-map-js> |
| `stdin-discarder` | 0.2.2 | MIT | <https://github.com/sindresorhus/stdin-discarder#readme> |
| `string-width` | 7.2.0 | MIT | <https://github.com/sindresorhus/string-width#readme> |
| `stringify-object` | 5.0.0 | BSD-2-Clause | <https://github.com/yeoman/stringify-object#readme> |
| `strip-ansi` | 6.0.1, 7.2.0 | MIT | <https://github.com/chalk/strip-ansi#readme> |
| `strip-bom` | 3.0.0 | MIT | <https://github.com/sindresorhus/strip-bom#readme> |
| `strip-final-newline` | 2.0.0, 4.0.0 | MIT | <https://github.com/sindresorhus/strip-final-newline#readme> |
| `styled-jsx` | 5.1.6 | MIT | <https://github.com/vercel/styled-jsx#readme> |
| `swr` | 2.5.1 | MIT | <https://swr.vercel.app> |
| `systeminformation` | 5.33.23 | MIT | <https://systeminformation.io> |
| `tiny-invariant` | 1.3.3 | MIT | <https://github.com/alexreardon/tiny-invariant#readme> |
| `to-regex-range` | 5.0.1 | MIT | <https://github.com/micromatch/to-regex-range> |
| `ts-morph` | 26.0.0 | MIT | <https://github.com/dsherret/ts-morph#readme> |
| `tsconfig-paths` | 4.2.0 | MIT | <https://github.com/dividab/tsconfig-paths#readme> |
| `tslib` | 2.9.1 | 0BSD | <https://www.typescriptlang.org/> |
| `tw-animate-css` | 1.4.0 | MIT | <https://github.com/Wombosvideo/tw-animate-css#readme> |
| `type-fest` | 4.41.0 | (MIT OR CC0-1.0) | <https://github.com/sindresorhus/type-fest#readme> |
| `undici` | 7.30.2 | MIT | <https://undici.nodejs.org> |
| `unicorn-magic` | 0.3.0 | MIT | <https://github.com/sindresorhus/unicorn-magic#readme> |
| `universalify` | 2.0.1 | MIT | <https://github.com/RyanZim/universalify#readme> |
| `update-browserslist-db` | 1.4.0 | MIT | <https://github.com/browserslist/update-db#readme> |
| `use-sync-external-store` | 1.7.0 | MIT | <https://github.com/react/react#readme> |
| `util-deprecate` | 1.0.2 | MIT | <https://github.com/TooTallNate/util-deprecate> |
| `validate-npm-package-name` | 7.0.2 | ISC | <https://github.com/npm/validate-npm-package-name> |
| `victory-vendor` | 37.4.1 | MIT AND ISC AND BSD-3-Clause | <https://commerce.nearform.com/open-source/victory> |
| `which` | 2.0.2, 4.0.0 | ISC | <https://github.com/npm/node-which#readme> |
| `wsl-utils` | 1.0.1 | MIT | <https://github.com/sindresorhus/wsl-utils#readme> |
| `yallist` | 3.1.1 | ISC | <https://github.com/isaacs/yallist#readme> |
| `yocto-spinner` | 1.2.2 | MIT | <https://github.com/sindresorhus/yocto-spinner#readme> |
| `yoctocolors` | 2.2.0 | MIT | <https://github.com/sindresorhus/yoctocolors#readme> |
| `zod` | 4.6.7 | MIT | <https://zod.dev> |

### B. Backend runtime dependencies (`backend/requirements.txt`, shipped in the API image)

45 packages.

| Package | Version | License (declared) | Source |
|---|---|---|---|
| `alembic` | 1.20.1 | MIT | <https://pypi.org/project/alembic/1.20.1/> |
| `annotated-doc` | 0.0.6 | MIT | <https://pypi.org/project/annotated-doc/0.0.6/> |
| `annotated-types` | 0.8.0 | MIT | <https://pypi.org/project/annotated-types/0.8.0/> |
| `anyio` | 4.16.0 | MIT | <https://pypi.org/project/anyio/4.16.0/> |
| `argon2-cffi` | 25.1.0 | MIT | <https://pypi.org/project/argon2-cffi/25.1.0/> |
| `argon2-cffi-bindings` | 26.2.0 | MIT | <https://pypi.org/project/argon2-cffi-bindings/26.2.0/> |
| `asyncpg` | 0.32.0 | Apache-2.0 | <https://pypi.org/project/asyncpg/0.32.0/> |
| `bcrypt` | 5.0.0 | Apache-2.0 | <https://pypi.org/project/bcrypt/5.0.0/> |
| `certifi` | 2026.10.23 | MPL-2.0 | <https://pypi.org/project/certifi/2026.10.23/> |
| `cffi` | 2.1.1 | MIT-0 | <https://pypi.org/project/cffi/2.1.1/> |
| `click` | 8.5.1 | BSD-3-Clause | <https://pypi.org/project/click/8.5.1/> |
| `defusedxml` | 0.7.1 | PSF-2.0 | <https://pypi.org/project/defusedxml/0.7.1/> |
| `dnspython` | 2.9.2 | ISC | <https://pypi.org/project/dnspython/2.9.2/> |
| `email-validator` | 2.4.0 | Unlicense | <https://pypi.org/project/email-validator/2.4.0/> |
| `et-xmlfile` | 2.0.0 | MIT | <https://pypi.org/project/et-xmlfile/2.0.0/> |
| `fastapi` | 0.163.2 | MIT | <https://pypi.org/project/fastapi/0.163.2/> |
| `greenlet` | 3.5.6 | MIT AND PSF-2.0 | <https://pypi.org/project/greenlet/3.5.6/> |
| `h11` | 0.16.0 | MIT | <https://pypi.org/project/h11/0.16.0/> |
| `httpcore` | 1.0.9 | BSD-3-Clause | <https://pypi.org/project/httpcore/1.0.9/> |
| `httptools` | 0.9.0 | MIT | <https://pypi.org/project/httptools/0.9.0/> |
| `httpx` | 0.28.1 | BSD-3-Clause | <https://pypi.org/project/httpx/0.28.1/> |
| `idna` | 3.20 | BSD-3-Clause | <https://pypi.org/project/idna/3.20/> |
| `mako` | 1.4.3 | MIT | <https://pypi.org/project/mako/1.4.3/> |
| `markupsafe` | 3.0.4 | BSD-3-Clause | <https://pypi.org/project/markupsafe/3.0.4/> |
| `openpyxl` | 3.1.5 | MIT | <https://pypi.org/project/openpyxl/3.1.5/> |
| `opentelemetry-api` | 1.45.2 | Apache-2.0 | <https://pypi.org/project/opentelemetry-api/1.45.2/> |
| `pwdlib` | 0.4.2 | MIT | <https://pypi.org/project/pwdlib/0.4.2/> |
| `pycparser` | 3.12 | BSD-3-Clause | <https://pypi.org/project/pycparser/3.12/> |
| `pydantic` | 2.14.3 | MIT | <https://pypi.org/project/pydantic/2.14.3/> |
| `pydantic-core` | 2.50.4 | MIT | <https://pypi.org/project/pydantic-core/2.50.4/> |
| `pydantic-settings` | 2.16.3 | MIT | <https://pypi.org/project/pydantic-settings/2.16.3/> |
| `pyjwt` | 2.15.1 | MIT | <https://pypi.org/project/pyjwt/2.15.1/> |
| `python-dotenv` | 1.2.4 | BSD-3-Clause | <https://pypi.org/project/python-dotenv/1.2.4/> |
| `python-multipart` | 0.0.34 | Apache-2.0 | <https://pypi.org/project/python-multipart/0.0.34/> |
| `pyyaml` | 6.0.3 | MIT | <https://pypi.org/project/pyyaml/6.0.3/> |
| `redis` | 8.1.0 | MIT | <https://pypi.org/project/redis/8.1.0/> |
| `sqlalchemy` | 2.1.9 | MIT | <https://pypi.org/project/sqlalchemy/2.1.9/> |
| `starlette` | 1.10.0 | BSD-3-Clause | <https://pypi.org/project/starlette/1.10.0/> |
| `typing-extensions` | 4.16.0 | PSF-2.0 | <https://pypi.org/project/typing-extensions/4.16.0/> |
| `typing-inspection` | 0.4.5 | MIT | <https://pypi.org/project/typing-inspection/0.4.5/> |
| `tzdata` | 2026.6 | Apache-2.0 | <https://pypi.org/project/tzdata/2026.6/> |
| `uvicorn` | 0.54.0 | BSD-3-Clause | <https://pypi.org/project/uvicorn/0.54.0/> |
| `uvloop` | 0.23.0 | MIT OR Apache-2.0 (ships both texts) | <https://pypi.org/project/uvloop/0.23.0/> |
| `watchfiles` | 1.3.0 | MIT | <https://pypi.org/project/watchfiles/1.3.0/> |
| `websockets` | 17.4 | BSD-3-Clause | <https://pypi.org/project/websockets/17.4/> |
