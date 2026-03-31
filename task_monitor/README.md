# task_monitor

训练任务生命周期监控子系统。

该目录用于承载和隔离“任务启动注册 + 心跳上报 + 服务端超时判定 + 自动重试识别 + 飞书通知”相关实现，避免与仓库现有的通用脚本工具混在一起。

## 目录规划

```text
task_monitor/
  client/
  server/
  shared/
  deploy/
  docs/
```

### `client/`

运行在训练任务所在集群环境中的客户端代码。

预期放置：

1. `job_watch.sh`
2. `heartbeat_client.py`
3. 客户端本地辅助脚本

### `server/`

运行在公网轻量云服务器上的服务端代码。

预期放置：

1. `monitor_server.py`
2. 任务状态扫描逻辑
3. 飞书通知逻辑
4. 持久化逻辑

### `shared/`

客户端和服务端共用的轻量模块。

预期放置：

1. 常量定义
2. 配置加载
3. 请求结构约定
4. 时间和日志辅助工具

### `deploy/`

部署相关文件。

预期放置：

1. 示例配置
2. systemd service 文件
3. 部署说明

### `docs/`

该子系统的设计文档和后续维护文档。

当前主文档为：

1. `docs/task_lifecycle_monitor_design.md`
