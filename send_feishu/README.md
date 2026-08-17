# 飞书机器人推送

1. 飞书创建群组，添加自定义机器人，记录 Webhook 地址
2. 创建 `~/.feishu_env` 文件并写入以下内容：
```shell
FEISHU_WEBHOOK_URL=https://open.feishu.cn/xxx
```
3. 在仓库根目录运行 `python send_feishu/send_feishu.py` 测试是否成功
4. 在项目中调用该功能：
```python
import os, sys
sys.path.append(os.path.join(os.environ.get('HOME'), 'Libraries'))
from auto_monitor.send_feishu.send_feishu import send_feishu

title = f"send_feishu 功能调用测试"
body = f"send_feishu 功能调用测试"

send_feishu(title, body)  # 需要使用独立 Webhook 的子项目可显式传入 webhook_url，传入后不会读取 ~/.feishu_env
```
