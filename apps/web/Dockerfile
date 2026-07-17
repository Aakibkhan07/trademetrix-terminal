FROM node:20-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_WS_URL
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
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0 NODE_ENV=production
CMD ["node_modules/.bin/next", "start"]
