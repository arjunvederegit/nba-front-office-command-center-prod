FROM node:22-alpine AS builder
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /srv
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /srv/.next/standalone ./
COPY --from=builder /srv/.next/static ./.next/static
COPY --from=builder /srv/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
