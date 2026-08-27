FROM node:22-alpine AS build
WORKDIR /app
COPY services/dashboard_frontend/package*.json ./
RUN npm ci
COPY services/dashboard_frontend ./
RUN npm run lint && npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY services/dashboard_frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
CMD ["nginx", "-g", "daemon off;"]
