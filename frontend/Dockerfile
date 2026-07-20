# Exhale frontend — Sunday COO Briefing UI (static build served by nginx)
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Where the browser reaches the API; baked into the bundle at build time.
ARG VITE_EXHALE_API=http://localhost:8000
ENV VITE_EXHALE_API=${VITE_EXHALE_API}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
