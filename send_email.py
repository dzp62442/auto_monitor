"""
服务器发送邮件通知
"""

import os
import smtplib
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.header import Header

def get_uptime_minutes():
    """获取服务器的运行时间（分钟）"""
    try:
        # 执行 `uptime -s` 获取启动时间（格式：2024-03-01 12:34:56）
        uptime_str = subprocess.check_output(["uptime", "-s"], text=True).strip()

        # 计算当前时间与启动时间的差值（分钟）
        boot_time = datetime.strptime(uptime_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        uptime_minutes = (now - boot_time).total_seconds() / 60

        return boot_time, uptime_minutes
    
    except Exception as e:
        print(f"获取 uptime 失败: {e}")
        return None

def baseline():
    """基本内容"""
    hostname = subprocess.check_output(["hostname"], text=True).strip()
    ip_address = subprocess.check_output(["hostname", "-I"], text=True).strip()
    boot_time, uptime_minutes = get_uptime_minutes()
    # 使用 date 命令获取标准格式的时间
    current_time = subprocess.check_output(["date", "+%Y-%m-%d %H:%M:%S"], text=True).strip()
    current_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")

    body = f"""
        ------
        服务器 {hostname} 地址：{ip_address.split(' ')[0]}
        启动时间：{boot_time}（{uptime_minutes:.2f} 分钟前）
        当前时间: {current_time}
        """
    return body

def send_email(subject, body, smtp_server='smtp.126.com', smtp_port=465):
    """发送邮件"""
    home_path = os.environ.get('HOME')
    load_dotenv(os.path.join(home_path, ".smtp_env"))  # 加载 env 文件
    from_email = os.getenv('from_email')
    smtp_key = os.getenv('smtp_key')
    to_email = os.getenv('to_email')

    base_body = baseline()  # 添加基本信息
    full_body = f"{body}\n{base_body}"  # 合并body和base_body
    message = MIMEText(full_body, 'plain', 'utf-8')
    message['From'] = Header(from_email, 'utf-8')
    message['To'] = Header(to_email, 'utf-8')
    message['Subject'] = Header(subject, 'utf-8')

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(from_email, smtp_key)
            server.sendmail(from_email, [to_email], message.as_string())
            print("邮件发送成功！")
    
    except Exception as e:
        print(f"邮件发送失败：{e}")


if __name__ == "__main__":
    boot_time, uptime_minutes = get_uptime_minutes()
    print(f"服务器已运行时间: {uptime_minutes:.2f} 分钟")

    if uptime_minutes is not None:
        hostname = subprocess.check_output(["hostname"], text=True).strip()
        subject = f"服务器 {hostname} 发信测试"
        body = f"""
        服务器 {hostname} 已启动！
        """
        send_email(subject, body)