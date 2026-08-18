# Built on an internet-connected machine only (see deploy/offline/).
# Stage 1 runs `npm ci` against the committed lockfile; the final image is
# just nginx + static files, so the container never runs npm at runtime and
# works without any internet access.
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
