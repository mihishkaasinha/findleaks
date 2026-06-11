FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
ARG VITE_API_BASE
ENV VITE_API_BASE=$VITE_API_BASE
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["/bin/sh", "-c", "envsubst '$$PORT' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
