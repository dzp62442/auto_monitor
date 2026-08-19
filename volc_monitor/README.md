# 火山任务状态监控

只读监控名称或 ID 中包含指定前缀的火山引擎机器学习任务，并通过飞书自定义机器人发送简洁的状态通知。

- 按北京时间的 `00/15/30/45` 分整刻检查，不是从服务启动时开始相对计时。
- 活动任务或最近 5 条结束记录有任何变化时才通知。
- 每天 `09:00/12:00/15:00/18:00/21:00` 无论状态是否变化都会通知。
- 查询完成且本轮需要通知时，随机等待 30–90 秒再推送；查询时刻本身不变。
- 查询失败与恢复也视为状态变化，相同错误不会每 15 分钟重复推送。
- 只执行 `volc ml_task list`，不会创建、停止或删除任务，也不读取训练日志。

## 配置

1. 按照[官方文档](https://docs.volcengine.com/docs/6459/72394?lang=zh)，安装火山 volc 命令行工具，并完成相关配置
2. 为本监控单独创建飞书自定义机器人，将它的 Webhook 写入专用配置：

```shell
cat > ~/.volc_monitor_env <<'EOF'
VOLC_MONITOR_TASK_PREFIX=<任务名前缀>
VOLC_MONITOR_FEISHU_WEBHOOK_URL=https://open.feishu.cn/xxx
EOF
chmod 600 ~/.volc_monitor_env
```

`VOLC_MONITOR_TASK_PREFIX` 用于过滤任务名或任务 ID。`volc_monitor` 只读取 `~/.volc_monitor_env`，不会读取通用的 `~/.feishu_env`。修改配置后需执行 `systemctl --user restart volc_monitor`。

## 手动验证

先在仓库根目录执行一次只读演练：

```shell
source "$HOME/.volc_env"
PYTHONPATH="$HOME/Libraries" python volc_monitor/volc_monitor.py --once --dry-run
```

`--dry-run` 不发送飞书、不等待随机延迟，也不写入上次状态。确认输出无误后，可去掉 `--dry-run` 发送一次测试通知。

## 注册 user service

以仓库位于 `~/Libraries/auto_monitor` 为例：

```shell
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/volc_monitor.service <<'EOF'
[Unit]
Description=Volc ML Task Monitor
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/Libraries/auto_monitor
Environment=PYTHONUNBUFFERED=1
UMask=0077
ExecStart=/bin/bash -lc 'source "$HOME/.volc_env" && export PYTHONPATH="$HOME/Libraries" && exec "$HOME/miniconda3/bin/python" "$HOME/Libraries/auto_monitor/volc_monitor/volc_monitor.py"'
Restart=on-failure
RestartSec=60

[Install]
WantedBy=default.target
EOF

loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now volc_monitor
```

服务启动后会等到下一个 15 分钟整刻再首次检查。

## 查看与停止

```shell
systemctl --user status volc_monitor
journalctl --user -u volc_monitor -f

systemctl --user disable --now volc_monitor
```

最后一次成功通知的状态保存在 `~/.local/state/auto_monitor/volc_monitor_state.json`，内容只包含任务名、ID、状态和时间，不包含密钥。
