FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY html/ /usr/share/nginx/html/

VOLUME /app/data

ENV ROOT_DIR=/app/data/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
