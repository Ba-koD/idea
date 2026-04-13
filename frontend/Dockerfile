FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY public /usr/share/nginx/html
COPY docker-entrypoint.d/30-render-config.sh /docker-entrypoint.d/30-render-config.sh

RUN chmod +x /docker-entrypoint.d/30-render-config.sh
