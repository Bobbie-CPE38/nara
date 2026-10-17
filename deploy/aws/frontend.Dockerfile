# Production image of the frontend for the AWS test machine (round 6 PR F3,
# docs/workflow.md 6.30). `next build` runs here, so the code is inside the image and
# nothing is mounted at run time. Build context: ./frontend.
#
# NEXT_PUBLIC_API_BASE_URL is written into the browser bundle by `next build`. It is the
# only value that gets there: setting it when the container starts changes nothing.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL
RUN test -n "$NEXT_PUBLIC_API_BASE_URL" || (echo "NEXT_PUBLIC_API_BASE_URL is required" >&2; exit 1)
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/.next ./.next
COPY next.config.ts ./
USER node
EXPOSE 3000
# node is PID 1 (no npm in between), so `docker stop` reaches the server
CMD ["./node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
