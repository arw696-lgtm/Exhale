# Exhale frontend — Sunday COO Briefing UI (static build served by nginx)
FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Where the browser reaches the API; baked into the bundle at build time.
ARG VITE_EXHALE_API=http://localhost:8000
ENV VITE_EXHALE_API=${VITE_EXHALE_API}

# Stamped into the UI so a deploy is verifiable from the phone. The build
# context is ./frontend and carries no .git, so the commit has to be passed
# in; without it the build timestamp alone still identifies the build.
ARG EXHALE_BUILD_COMMIT=""
ENV EXHALE_BUILD_COMMIT=${EXHALE_BUILD_COMMIT}
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
