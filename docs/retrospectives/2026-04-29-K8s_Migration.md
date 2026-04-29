# 2026-04-29-CourseBot Kubernetes 迁移复盘记录

## 1. 核心任务回顾 (Executive Summary)
本次任务的核心目标是将原有的 `docker-compose` 架构下的 CourseBot 项目整体迁移至基于 Minikube 的 Kubernetes 集群。任务涵盖了从架构重新设计、存储持久化、数据热迁移到云端 CI/CD 流转的全流程。

**技术栈变更**:
- **编排工具**: 由 Docker Compose 切换为 **Kubernetes (Minikube)**。
- **配置管理**: 引入 **Kustomize** 实现 dev/prod 多环境分层配置。
- **自动化部署**: 更新 GitHub Actions 流程，支持镜像自动 Patch 与集群内资源滚动更新。
- **存储方案**: 使用 Kubernetes **Persistent Volume Claims (PVC)** 替代原有的 Docker Local Volumes。

---

## 2. 迁移历程总结 (Process & Logic)

### 阶段一：架构抽象与 Kustomize 声明式重构
- **阶段目标 (Goal)**: 将平铺的 Docker 服务定义解构为标准的 K8s 资源，并解决开发与生产环境的差异化配置问题。
- **设计思路 (Design)**: 选取 **Kustomize** 作为配置管理工具。采用 `base/` 存放通用 Deployment、Service 和 StatefulSet，通过 `overlays/` 进行环境特定补丁（如副本数、镜像拉取策略、Secrets 注入）。
- **实施过程 (Implementation)**:
    - 针对有状态服务（Redis, Chroma, Ollama）定义 **StatefulSet** 以确保 Pod 标识稳定。
    - 针对无状态服务定义 Deployment。
    - 统一通过 Service 实现内部 `ClusterIP` 通信。

### 阶段二：有状态数据迁移与存储持久化
- **阶段目标 (Goal)**: 确保数 GB 的 Ollama 模型、Chroma 向量索引及 Redis 缓存数据从原有 Docker 卷无损迁移至 K8s PVC。
- **设计思路 (Design)**: 由于 Minikube 存储在虚拟内网，采用“容器级中转”方案。先通过临时容器挂载旧卷并 Tar 打包，再利用 `kubectl cp` 注入运行中的新 Pod。
- **实施过程 (Implementation)**:
    - 使用 `redis:7-alpine` 作为中转镜像执行 `cp -a` 提取数据。
    - 在 K8s 中通过 `volumeClaimTemplates` 动态申请存储资源。

### 阶段三：云端自动化部署与公网暴露
- **阶段目标 (Goal)**: 实现代码推送后自动构建镜像并更新到云端集群，同时确保外网可访问。
- **设计思路 (Design)**: 
    - 修改 `.github/workflows/deploy.yml`，集成 `kustomize edit set image` 实现镜像版本动态绑定。
    - 利用宿主机 Nginx 作为反向代理，将公网流量转发至 Minikube 内部 Service 端口。

---

## 3. 深水区：关键避坑点与解决方案 (Pits & Solutions)

### 问题一：Kustomize 越级路径安全拦截
- **问题现象**: 执行部署时报错 `security; file '.env' is not in or below ...`。
- **根因分析**: Kustomize 的 `secretGenerator` 严禁读取其所在目录层级以外的文件。
- **最终解法**: 在 GitHub Actions 脚本中，利用 `kubectl create secret generic cb-secrets --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -` 动态生成 Secret，规避了路径限制。

### 问题二：数据热迁移导致的文件系统权限冲突
- **问题现象**: 迁移完成后，Redis 缓存失效，Chroma 无法新增文档。
- **根因分析**: 
    1. **权限丢失**: `kubectl cp` 将文件以 root 身份存入，而 Redis 等镜像运行在非 root 用户下，导致无法写入 AOF/RDB。
    2. **文件描述符陈旧**: 在进程运行时覆盖底层 SQLite 或 AOF 文件，导致进程内存状态与磁盘不一致。
- **最终解法**: 在 `kubectl cp` 后强制执行 `chown -R 999:1000 /data`（针对 Redis），并对相关 Pod 执行删除重建，确保进程启动时重新加载最新磁盘文件。

### 问题三：磁盘 I/O 阻塞引发的 RAG 链路超时
- **问题现象**: 系统运行一段时间后，RAG 检索失效，服务器 `iowait` 飙升。
- **根因分析**: Ollama 默认的模型卸载机制触发了云服务器低 IOPS 磁盘的高频加载。
- **最终解法**: 设置环境变量 `OLLAMA_KEEP_ALIVE: "-1"` 实现模型常驻内存，并将服务间调用超时时间由 30s 提升至 120s。

### 问题四：本地开发环境下的“连通性断层”
- **问题现象**: 访问 `127.0.0.1:8080` 返回 `Connection refused`。
- **根因分析**: 开发者习惯了 Docker Compose 的端口直映射，未考虑到 K8s NodePort 与物理宿主机的隔离性。
- **最终解法**: 确立了使用 `kubectl port-forward svc/nginx-gateway 8080:80` 建立临时隧道作为标准本地接入方案。

### 问题五：低级编码错误阻塞 CI/CD 流水线
- **问题现象**: 仅因一个未使用的 Import 导致远程部署失败。
- **根因分析**: `vue-tsc --noEmit` 在 Project References 模式下未能正确识别项目引用，导致本地检查“伪通过”。
- **最终解法**: 
    - 升级脚本为 `vue-tsc -b` 以强制执行项目引用检查。
    - 部署了一套基于 `git diff` 识别改动范围的 Git pre-commit hook，实现“测试前置（Shift Left）”。

---

## 4. 经验沉淀与未来展望 (Lessons & Future)

### 核心沉淀
1. **数据迁移原子性**: 涉及数据库迁移时，务必“先导数据、再改权限、最后启服务”，严禁在运行中直接热覆盖 DB 文件。
2. **AI 模型资源隔离**: AI 类业务的 `iowait` 往往比 `CPU usage` 更致命，资源受限环境下应优先考虑模型常驻内存。
3. **K8s 本地化适配**: Minikube 在云端运行时，宿主机反代与内部 Service 的端口映射是连通性的关键点。

### 后续优化
- **全量指标监控**: 引入 Prometheus 监控 Pod 的 OOM 事件及 I/O 延迟。
- **模型量化升级**: 针对 I/O 敏感环境，考虑对嵌入模型进行更深度的量化以降低加载体积。
- **资源动态治理**: 未来考虑根据实际负载自动微调各组件的 `limits` 以提高资源利用率。
