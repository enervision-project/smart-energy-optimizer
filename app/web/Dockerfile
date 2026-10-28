# Étape 1 : build
FROM node:24-alpine AS build
RUN apk upgrade --no-cache
WORKDIR /app
COPY package*.json ./
RUN npm --ignore-scripts ci
COPY . .
RUN npm run build

# Étape 2 : service des fichiers statiques
FROM nginxinc/nginx-unprivileged:1.31-alpine
USER root
RUN apk upgrade --no-cache
USER nginx
COPY --chmod=444 nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chmod=555 /app/dist/web/browser /usr/share/nginx/html
EXPOSE 8080
