# syntax=docker/dockerfile:1
# Next.js frontend (BFF). The browser talks only to this server; it keeps the
# session in httpOnly cookies and proxies /api/v1/* to FastAPI at BACKEND_URL,
# which is read at RUNTIME (not baked into the image).
ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS base
# Keep in sync with "packageManager" in package.json.
ARG PNPM_VERSION=12.21.0
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install -g --no-fund --no-audit "pnpm@${PNPM_VERSION}"
WORKDIR /app

# All dependencies (dev ones are needed to build: TypeScript, Tailwind, PostCSS).
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# Runtime: production dependencies + the build output only.
FROM base AS runtime
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prod
COPY --from=build /app/next.config.mjs ./
COPY --from=build /app/public ./public
COPY --from=build --chown=node:node /app/.next ./.next
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node_modules/.bin/next", "start"]
