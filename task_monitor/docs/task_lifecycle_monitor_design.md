# 任务生命周期监控系统设计

## 1. 背景

当前开发流程是：

1. 本地完成代码开发。
2. 在火山云 A100 服务器集群上提交自定义任务。
3. 任务通过类似如下入口命令启动训练：

```bash
cd /vepfs-mlp2/c20250502/haoce/dzp/GaussianFormer
. /root/miniconda3/bin/activate
source haoce_activate.sh
python train.py --py-config config/prob/nuscenes_gs6400.py --work-dir out/prob/gs6400_my/
```

由于平台存在任务优先级抢占、GPU 碎片整理、自动重试等机制，训练任务可能被平台中断。当前仓库已经支持通过 `send_feishu.py` 主动上报训练进度，但这类上报依赖训练代码内部手动调用，无法独立承担任务生命周期监管。

因此，需要建立一套与训练逻辑解耦的“任务生命周期监控系统”，用于自动感知任务启动、运行、中断和自动重试等关键状态，并将结果推送到个人飞书。

## 2. 目标

系统需要满足以下目标：

1. 训练任务启动时，能够自动向公网服务器注册当前任务。
2. 训练任务运行期间，能够持续发送心跳包。
3. 公网服务器超过阈值未收到心跳时，能够判断任务疑似中断并通知飞书。
4. 若平台自动重试成功并拉起同名任务，公网服务器能够识别这是旧任务被替换，并通知飞书。
5. 方案按单用户使用场景设计，配置放在个人工作目录下的配置文件中，不考虑多用户隔离。
6. 集群侧调用必须极简，最好只需要在提交任务时额外写一行命令，且不能阻塞终端。
7. 生命周期监控系统必须作为本仓库下的一个独立子系统存在，客户端和服务端代码明确分离。

## 3. 已知条件与约束

### 3.1 已具备条件

1. 当前仓库已有 [send_feishu.py](/home/dzp62442/Libraries/auto_monitor/send_feishu.py) 可用于飞书机器人通知。
2. 用户拥有一台带公网 IP 的火山云轻量云服务器，可部署监控服务端。
3. 训练任务所在的 A100 集群可以访问公网服务器。

### 3.2 约束

1. 当前实现按单用户使用，不考虑共享账号下的多用户隔离问题。
2. 平台可能直接杀掉任务进程，导致任务没有机会执行清理逻辑。
3. 平台自动重试可能成功，也可能失败，且达到上限后不再重试。
4. 任务提交时希望只传入“任务名”这一项主要自定义参数，其余配置从个人工作目录下的 `.auto_monitor_cfg` 自动读取。
5. 由于生命周期监控与训练进度上报解耦，系统不尝试区分“正常训练结束后退出”和“被平台中断后退出”，两者在本系统里都统一表现为“心跳消失后超时”。
6. 代码组织上必须避免“客户端脚本、服务端服务、共享工具、部署文件”混写在仓库根目录。

## 4. 核心需求拆解

### 4.1 生命周期事件

系统需要识别以下事件：

1. `register`：任务启动并完成注册。
2. `heartbeat`：任务仍在存活。
3. `timeout`：超过阈值未收到心跳，判定任务疑似中断。
4. `retry`：同名任务重新注册，推测平台已触发自动重试并成功拉起新实例。

### 4.2 单用户配置

系统按单用户使用设计，配置集中保存在个人工作目录下的 `.auto_monitor_cfg` 文件中。建议至少包含：

1. `MONITOR_SERVER_URL`
2. `MONITOR_HEARTBEAT_SEC`
3. `MONITOR_TIMEOUT_SEC`
4. `FEISHU_WEBHOOK_URL`

在该方案下，任务只通过 `task_name` 区分，不再额外区分用户身份。

### 4.3 极简调用

理想调用方式：

```bash
source /path/to/auto_monitor/task_monitor/client/job_watch.sh "gf_nuscenes_gs6400"
```

随后继续执行原训练命令，无需修改训练代码，也不会阻塞终端。

## 5. 子系统架构规划

本需求在仓库中不应作为零散脚本实现，而应整理为单独的 `task_monitor/` 子系统目录。

推荐目录结构如下：

```text
task_monitor/
  README.md
  client/
    job_watch.sh
    heartbeat_client.py
    client_main.py
  server/
    monitor_server.py
    service.py
    storage.py
    notifier.py
    scanner.py
  shared/
    config.py
    constants.py
    schemas.py
    utils.py
  deploy/
    server.example.cfg
    client.example.cfg
    task-monitor.service
  docs/
    task_lifecycle_monitor_design.md
```

其中：

1. `client/` 只放运行在训练集群环境中的代码。
2. `server/` 只放运行在公网轻量云上的服务端代码。
3. `shared/` 只放两端可复用、且不依赖运行环境的轻量模块。
4. `deploy/` 只放部署和配置样例，不放业务逻辑。
5. `docs/` 只放设计和维护文档。

## 6. 分层职责设计

### 6.1 client 层

`client/` 负责“采集本地任务状态并上报”，不负责状态决策，不负责通知。

建议职责：

1. 读取 `.auto_monitor_cfg`
2. 生成 `run_id`
3. 上报 `register`
4. 周期上报 `heartbeat`
5. 管理本地后台心跳进程

明确不负责：

1. 判定任务是否超时
2. 判定是否自动重试成功
3. 直接调用飞书通知
4. 保存全局任务状态

### 6.2 server 层

`server/` 负责“维护全局状态并做判断”，是整个系统的控制中心。

建议职责：

1. 提供 HTTP 接口
2. 落库任务状态
3. 扫描超时任务
4. 识别同名任务重注册
5. 调用飞书通知

明确不负责：

1. 运行训练命令
2. 持有集群侧 shell 上下文
3. 修改训练脚本

### 6.3 shared 层

`shared/` 负责放置两端都需要的最小公用代码，避免 client/server 重复实现协议细节。

建议职责：

1. 配置加载
2. 默认常量
3. 请求体结构约定
4. 时间格式化
5. 公共日志格式

控制原则：

1. `shared/` 不得依赖服务端专有模块。
2. `shared/` 不得依赖客户端专有 shell 环境。
3. `shared/` 只保留真正跨端复用的内容，避免演化成杂项目录。

## 7. 运行链路设计

完整链路如下：

1. 用户在训练脚本前执行 `source task_monitor/client/job_watch.sh "task_name"`。
2. `job_watch.sh` 读取本地配置，生成 `run_id`，启动后台心跳客户端。
3. `heartbeat_client.py` 先向服务端发送 `register`。
4. 之后按固定周期向服务端发送 `heartbeat`。
5. 服务端收到 `register` 后建立或更新任务记录。
6. 服务端收到 `heartbeat` 后刷新 `last_heartbeat_at`。
7. 服务端后台扫描器检查是否存在心跳超时任务。
8. 若超时，则标记任务为 `interrupted` 并通知飞书。
9. 若同名任务再次 `register`，则认为发生自动重试成功，旧任务标记为 `superseded`，并发送飞书通知。

## 8. 服务端设计

### 8.1 server 内部模块建议

推荐拆分为以下文件：

1. `monitor_server.py`
   服务入口，负责启动 HTTP 服务和后台扫描器。
2. `service.py`
   编排 `register`、`heartbeat`、状态更新等核心业务流程。
3. `storage.py`
   负责 SQLite 或文件持久化。
4. `notifier.py`
   负责飞书消息发送，可复用根目录 [send_feishu.py](/home/dzp62442/Libraries/auto_monitor/send_feishu.py) 或包装成子系统内适配器。
5. `scanner.py`
   后台超时扫描逻辑。

### 8.2 接口设计

建议提供以下 HTTP 接口：

1. `POST /register`
   客户端任务启动时调用。
2. `POST /heartbeat`
   客户端后台周期调用。
3. `GET /health`
   健康检查接口。

### 8.3 建议请求体

#### `POST /register`

```json
{
  "task_name": "gf_nuscenes_gs6400",
  "run_id": "uuid-or-timestamp",
  "host_name": "worker-a100-03",
  "pid": 12345,
  "cwd": "/vepfs-mlp2/c20250502/haoce/dzp/GaussianFormer",
  "command": "python train.py --py-config ...",
  "started_at": "2026-03-31T22:00:00+08:00",
  "meta": {
    "platform": "volcengine-a100",
    "cluster": "shared"
  }
}
```

#### `POST /heartbeat`

```json
{
  "task_name": "gf_nuscenes_gs6400",
  "run_id": "uuid-or-timestamp",
  "sent_at": "2026-03-31T22:01:00+08:00"
}
```

### 8.4 状态机

建议任务状态包括：

1. `registered`
2. `running`
3. `interrupted`
4. `superseded`

建议状态流转如下：

1. `register` 后进入 `registered`。
2. 收到首个 `heartbeat` 后进入 `running`。
3. 心跳超时后进入 `interrupted`。
4. 若同一 `task_name` 下出现新的 `register`，且旧任务仍被视为当前活动实例，则旧任务进入 `superseded`，新任务进入 `registered`。

### 8.5 自动重试判定规则

自动重试的核心判定依据是：

1. 同一任务名。
2. 新的 `run_id`。
3. 旧任务仍被认为是当前活动实例。

当服务端收到同名任务的新注册时：

1. 若旧任务处于 `registered` 或 `running` 状态，则说明旧实例已失效或即将失效。
2. 将旧实例标记为 `superseded`。
3. 为新实例创建任务记录。
4. 向飞书发送“任务自动重试成功，新实例已启动”的通知。

### 8.6 超时扫描

服务端需要有后台扫描线程或定时任务，建议：

1. 每 10 到 15 秒扫描一次运行中任务。
2. 若 `当前时间 - last_heartbeat_at > timeout_sec`，则标记为 `interrupted`。
3. 进入 `interrupted` 时只通知一次，避免重复报警。

推荐默认值：

1. 心跳周期：30 秒
2. 超时阈值：120 秒
3. 扫描周期：15 秒

## 9. 客户端设计

### 9.1 client 内部模块建议

推荐拆分为以下文件：

1. `job_watch.sh`
   面向用户的一行入口脚本。
2. `heartbeat_client.py`
   负责执行注册与心跳循环。
3. `client_main.py`
   作为 Python 侧统一入口，封装参数解析和运行模式。

### 9.2 调用形式

推荐由用户在训练启动前执行：

```bash
source /path/to/auto_monitor/task_monitor/client/job_watch.sh "gf_nuscenes_gs6400"
```

随后执行原训练命令：

```bash
cd /vepfs-mlp2/c20250502/haoce/dzp/GaussianFormer
. /root/miniconda3/bin/activate
source haoce_activate.sh
python train.py --py-config config/prob/nuscenes_gs6400.py --work-dir out/prob/gs6400_my/
```

### 9.3 为什么推荐 `source`

推荐 `source job_watch.sh` 而不是直接后台执行一个 shell 脚本，原因是：

1. `source` 可以在当前 shell 环境里保存 `run_id` 和后台心跳进程 PID。
2. 使用者只需新增一行命令，不必改训练主命令。
3. 即使后续要补充更多环境变量透传，`source` 也更容易扩展。

### 9.4 客户端行为

`job_watch.sh` 建议完成以下动作：

1. 读取个人工作目录下的配置文件，例如 `.auto_monitor_cfg`。
2. 解析 `MONITOR_SERVER_URL`、`MONITOR_HEARTBEAT_SEC`、`MONITOR_TIMEOUT_SEC` 等参数。
3. 生成唯一 `run_id`。
4. 立即调用 `client/heartbeat_client.py register`。
5. 在后台启动 `client/heartbeat_client.py loop`。
6. 将后台心跳进程 PID 保存到当前 shell 环境，便于后续排查或手动清理。

### 9.5 非阻塞要求

后台心跳必须以守护方式运行，不能阻塞训练命令的继续执行。也就是说，用户执行 `source job_watch.sh "task_name"` 后，终端应立即回到可继续输入训练命令的状态。

## 10. 配置设计

### 10.1 client 配置

建议在个人工作目录下维护 `.auto_monitor_cfg`，例如：

```bash
MONITOR_SERVER_URL=http://<public-ip>:<port>
MONITOR_HEARTBEAT_SEC=30
MONITOR_TIMEOUT_SEC=120
FEISHU_WEBHOOK_URL=https://open.feishu.cn/xxx
```

其中：

1. `MONITOR_SERVER_URL` 用于指向公网监控服务。
2. `MONITOR_HEARTBEAT_SEC` 用于控制心跳发送频率。
3. `MONITOR_TIMEOUT_SEC` 用于控制服务端超时阈值。
4. `FEISHU_WEBHOOK_URL` 可直接供服务端读取，或由部署脚本同步到服务端配置。

### 10.2 server 配置

服务端也维护一份本地 `.auto_monitor_cfg`，至少包含：

```bash
MONITOR_BIND_HOST=0.0.0.0
MONITOR_BIND_PORT=18080
MONITOR_TIMEOUT_SEC=120
FEISHU_WEBHOOK_URL=https://open.feishu.cn/xxx
```

当前方案中，服务端维护单套全局配置，不做多用户映射。

## 11. 持久化方案

最小可用版本建议优先使用本地文件或 SQLite 持久化，而不是一开始引入数据库服务。

推荐优先级：

1. 第一阶段：SQLite
2. 第二阶段：如有需要，再切换到 MySQL 或 PostgreSQL

原因：

1. 公网轻量云单机部署简单。
2. 查询逻辑不复杂。
3. 任务量通常不大，SQLite 足够支撑。

建议至少保存以下字段：

1. `task_name`
2. `run_id`
3. `status`
4. `host_name`
5. `pid`
6. `command`
7. `registered_at`
8. `last_heartbeat_at`
9. `last_event_at`
10. `notify_flags`

## 12. 通知策略

建议服务端统一负责通知，通知事件如下：

1. 任务已启动。
2. 任务心跳正常，可选是否通知，默认不通知。
3. 任务疑似中断。
4. 检测到同名任务重新注册，判定自动重试成功。

建议默认启用以下通知：

1. 启动通知
2. 中断通知
3. 自动重试成功通知

不建议默认发送周期性“心跳正常”通知，否则飞书噪声会过大。

## 13. 失败场景与处理策略

### 13.1 任务被强杀

现象：

1. 客户端心跳进程和训练进程一起被杀掉。

处理：

1. 服务端依靠心跳超时判定为 `interrupted`。

### 13.2 网络抖动

现象：

1. 单次心跳发送失败。

处理：

1. 心跳周期短于超时阈值。
2. 客户端允许心跳重试。
3. 服务端只有连续超时后才发告警。

### 13.3 自动重试失败

现象：

1. 旧任务超时中断。
2. 长时间没有新任务注册。

处理：

1. 先发送“任务中断”通知。
2. 不主动假设自动重试成功。
3. 如果后续出现同名新注册，再单独发送“自动重试成功”通知。

### 13.4 配置错误

现象：

1. 客户端配置文件缺失、地址错误或服务端不可达。

处理：

1. 客户端启动时立即输出错误。
2. 若注册失败，明确提示用户当前任务未进入监管状态。

## 14. 与现有训练进度上报的关系

这套系统应与训练进度上报机制严格分离：

1. 生命周期监控负责“任务是否活着、是否中断、是否重试”。
2. 训练代码里的 `send_feishu` 调用负责“训练到哪一步、当前指标如何、loss 是否异常”等业务内容。

两者分离后有以下好处：

1. 生命周期监控不依赖训练代码。
2. 即使训练代码没有主动上报进度，也能知道任务是否被平台中断。
3. 训练进度通知频率和生命周期通知频率可以独立控制。

## 15. 推荐实施顺序

### 第一阶段：目录与骨架

1. 创建 `task_monitor/` 子系统目录。
2. 划分 `client/`、`server/`、`shared/`、`deploy/`、`docs/`。
3. 固定文件职责边界，避免根目录继续堆放监控相关脚本。

### 第二阶段：最小可用版本

1. 实现 `server/monitor_server.py`。
2. 实现 `client/heartbeat_client.py`。
3. 实现 `client/job_watch.sh`。
4. 支持 `register`、`heartbeat`。
5. 支持心跳超时报警。
6. 支持基础飞书通知。

### 第三阶段：增强版本

1. 支持自动重试识别。
2. 支持任务历史查询接口。
3. 支持更详细的上下文字段，如工作目录、启动命令、节点信息。
4. 支持部署样例和服务化运行。

### 第四阶段：稳定性增强

1. 支持通知去重。
2. 支持客户端重试和退避。
3. 支持服务端日志轮转和异常恢复。
4. 支持简单 Web 页面或命令行查询最近任务状态。

## 16. 当前结论

针对当前需求，推荐采用：

1. 在仓库下新增独立子系统目录 `task_monitor/`。
2. 将客户端代码固定放在 `task_monitor/client/`。
3. 将服务端代码固定放在 `task_monitor/server/`。
4. 将公共代码固定放在 `task_monitor/shared/`。
5. 将部署与文档分别放在 `task_monitor/deploy/` 和 `task_monitor/docs/`。
6. 通过个人工作目录下的 `.auto_monitor_cfg` 管理配置。
7. 通过“同任务名重新注册”识别自动重试成功。
8. 通过 `source task_monitor/client/job_watch.sh "任务名"` 满足极简、非阻塞、与训练代码解耦的使用方式。

这套方案与当前仓库定位一致，同时在代码组织层面更清晰，便于后续逐步落地实现，而不会把任务生命周期监控逻辑继续扩散到仓库根目录。
