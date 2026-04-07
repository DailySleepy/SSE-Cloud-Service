# 阶段 1: 构建
FROM node:24-alpine AS build-stage
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# 阶段 2: 生产环境 (使用轻量级 Nginx 镜像)
FROM nginx:stable-alpine AS production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
# 关键修复: 注入自定义配置以支持 SPA 路由 (解决直接访问 /console 等子路径 404 问题)
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
