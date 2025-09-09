# auto_monitor
自用服务器监控工具，以及各种训练调试小工具

## 1 发信功能

1. 从对应发信客户端申请 smtp 授权码
2. 创建 `.smtp_env` 文件并写入以下内容：
```shell
from_email=xxx@126.com
smtp_key=XXXXX
to_email=xxx@163.com
```
3. 运行 `python send_email.py` 测试是否成功
4. 在项目中调用该功能：
```python
import os, sys
sys.path.append(os.path.join(os.environ.get('HOME'), 'Libraries'))
from auto_monitor.send_email import send_email

subject = f"send_email 功能调用测试"
body = f"""
send_email 功能调用测试
"""

send_email(subject, body)
```

## 2 通过 systemctl 实现开机自动恢复训练

1. 拷贝启动脚本 `auto_resume.sh` 到 home 目录：`cp auto_resume.sh ~/`
2. 创建服务文件
```shell
mkdir -p ~/.config/systemd/user/
cat > ~/.config/systemd/user/auto_resume.service <<EOF
[Unit]
Description=Auto Resume Service
After=network.target

[Service]
Type=simple
StandardOutput=null
ExecStart=/bin/bash -lc '$HOME/auto_resume.sh'
Restart=on-failure
RestartSec=180s

[Install]
WantedBy=default.target
EOF
```

3. 赋予执行权限：
```shell
chmod +x ~/auto_resume.sh
```

3. 启动服务
```shell
# 允许用户服务在未登录时运行
loginctl enable-linger $USER
# 启用服务
systemctl --user daemon-reload
systemctl --user enable --now auto_resume
```

4. 验证
```shell
# 查看服务状态
systemctl --user status auto_resume
# 查看详细日志
tail -f auto_resume_*.log
```

## 3 支持 GPU 同步的计时器

在项目中调用该功能：
```python
import os, sys
sys.path.append(os.path.join(os.environ.get('HOME'), 'Libraries'))
from auto_monitor.timer import Timer
```

## 4 打印复杂数据结构

在项目中调用该功能：
```python
import os, sys
sys.path.append(os.path.join(os.environ.get('HOME'), 'Libraries'))
from auto_monitor.show_data import show_data
```