# Multi-stage build for React frontend
FROM --platform=linux/amd64 node:22.14.0-alpine3.21 AS build

WORKDIR /app

# Enable corepack and install dependencies
RUN corepack enable && corepack prepare pnpm@10.34.5 --activate

COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

COPY . .
RUN pnpm run build

# Production image with Nginx
FROM --platform=linux/amd64 nginx:1.27.4-alpine3.21

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
