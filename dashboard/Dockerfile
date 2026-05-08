FROM node:20-slim AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM python:3.12-slim

WORKDIR /app
COPY --from=build /app/dist /app/dist
COPY server.py /app/server.py

CMD ["python", "/app/server.py"]
