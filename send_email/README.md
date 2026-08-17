# 发信功能

1. 从对应发信客户端申请 smtp 授权码
2. 创建 `~/.smtp_env` 文件并写入以下内容：
```shell
from_email=xxx@126.com
smtp_key=XXXXX
to_email=xxx@163.com
```
3. 在仓库根目录运行 `python send_email/send_email.py` 测试是否成功
4. 在项目中调用该功能：
```python
import os, sys
sys.path.append(os.path.join(os.environ.get('HOME'), 'Libraries'))
from auto_monitor.send_email.send_email import send_email

subject = f"send_email 功能调用测试"
body = f"""
send_email 功能调用测试
"""

send_email(subject, body)
```
