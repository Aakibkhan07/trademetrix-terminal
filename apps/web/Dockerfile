FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --cache /tmp/npm-cache
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs && \
    apk add --no-cache curl wget
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
# Fix chunk resolution: Next.js webpack runtime (loaded via pages/_document.js
# as require("../webpack-runtime.js")) has f.require("./chunks/1072.js") which
# resolves relative to pages/ (the runtime's effective cwd), NOT server/.
# The build only populates server/chunks/. Copy chunks into pages/chunks/ too.
RUN cp -r /app/.next/server/chunks/. /app/.next/server/pages/chunks/ && \
    cp -r /app/.next/server/chunks/. /app/.next/server/
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./
COPY --from=builder /app/server.js ./
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0 NODE_ENV=production
CMD ["node", "server.js"]
