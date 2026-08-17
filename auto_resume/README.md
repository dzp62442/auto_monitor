# 通过 systemctl 实现开机自动恢复训练

1. 在仓库根目录将启动脚本拷贝到 home 目录：
```shell
cp auto_resume/auto_resume.sh ~/
```

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

4. 启动服务
```shell
# 允许用户服务在未登录时运行
loginctl enable-linger $USER
# 启用服务
systemctl --user daemon-reload
systemctl --user enable --now auto_resume
```

5. 验证
```shell
# 查看服务状态
systemctl --user status auto_resume
# 查看详细日志
tail -f auto_resume_*.log
```
