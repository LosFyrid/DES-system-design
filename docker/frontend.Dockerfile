# Frontend Dockerfile for DES Formulation System
# Multi-stage build: Node.js build -> Nginx serve

# ============ Build Stage ============
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY src/web_frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY src/web_frontend/ ./

# Build argument for API URL
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Build frontend
RUN npm run build

# ============ Production Stage ============
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
