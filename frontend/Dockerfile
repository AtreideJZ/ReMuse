FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Next.js 的 rewrites 在构建期固化（见 next.config.ts），
# 因此 API_ORIGIN 必须以构建参数注入，运行时 -e 无效
ARG API_ORIGIN=http://localhost:8001
ENV API_ORIGIN=$API_ORIGIN
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder --chown=node:node /app ./
# 非 root 运行（node:24-alpine 自带 node 用户，uid 1000）
USER node
EXPOSE 3000
CMD ["npm", "start"]
