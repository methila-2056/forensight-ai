# FORENSIGHT AI — frontend build + static host image.
#
# The client calls the API through relative /api paths (VITE_API_BASE defaults
# to ""), so the built bundle needs no environment-specific configuration and
# nginx can proxy /api straight through to the backend service.
FROM node:22-alpine AS build

WORKDIR /build

# Dependencies are installed from the lockfile first so the npm layer is
# cached independently of application source changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src

RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]