FROM nginx:1.25-alpine

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy portal landing page and error assets
COPY html/ /usr/share/nginx/html/

# Expose HTTP entry port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
