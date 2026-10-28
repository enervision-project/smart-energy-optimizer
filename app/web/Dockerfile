# Étape 1 : build
FROM node:24-alpine AS build
RUN apk upgrade --no-cache
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Étape 2 : service des fichiers statiques
FROM nginx:1.31-alpine
RUN apk upgrade --no-cache
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/web/browser /usr/share/nginx/html
EXPOSE 80
