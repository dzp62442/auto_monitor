"""
飞书自定义机器人消息通知（富文本）
"""

import os
import requests
import subprocess
from datetime import datetime


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
        return None, None


def baseline():
    """返回基础信息后缀"""
    hostname = "未知"
    ip_address = "未知"
    try:
        hostname = subprocess.check_output(["hostname"], text=True).strip()
    except Exception as e:
        print(f"获取 hostname 失败: {e}")
    try:
        ip_raw = subprocess.check_output(["hostname", "-I"], text=True).strip()
        ip_address = ip_raw.split(" ")[0] if ip_raw else "未知"
    except Exception as e:
        print(f"获取 IP 失败: {e}")

    boot_time, uptime_minutes = get_uptime_minutes()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if boot_time and uptime_minutes is not None:
        boot_line = f"启动时间：{boot_time}（{uptime_minutes:.2f} 分钟前）"
    else:
        boot_line = "启动时间：未知"

    lines = [
        "------",
        f"服务器 {hostname} 地址：{ip_address}",
        boot_line,
        f"当前时间：{current_time}",
    ]
    return "\n".join(lines)


def _normalize_text_block(text):
    if text is None:
        return ""
    raw = str(text)
    lines = raw.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    indent = None
    for line in lines:
        if not line.strip():
            continue
        leading = len(line) - len(line.lstrip(" "))
        indent = leading if indent is None else min(indent, leading)
    if indent:
        lines = [line[indent:] if len(line) >= indent else "" for line in lines]
    return "\n".join(lines)


def _parse_timeout(value):
    if not value:
        return 5
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError("FEISHU_TIMEOUT 必须是数字") from exc


def _extract_error_code(data):
    for key in ("code", "StatusCode", "errcode"):
        if key in data:
            return data[key]
    return None


def _load_webhook_config():
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        raise ValueError("FEISHU_WEBHOOK_URL 未配置")
    timeout = _parse_timeout(os.getenv("FEISHU_TIMEOUT"))
    return webhook_url, timeout


def _post_message(webhook_url, payload, timeout):
    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"飞书请求失败: {exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        return True

    error_code = _extract_error_code(data)
    if error_code is not None and error_code != 0:
        raise RuntimeError(f"飞书返回错误: {data}")
    return True


def _build_post_payload(title, body):
    body_text = _normalize_text_block(body)
    lines = body_text.splitlines() if body_text else [""]
    content = [[{"tag": "text", "text": line}] for line in lines]
    return {
        "msg_type": "post",
        "content": {"post": {"zh_cn": {"title": title, "content": content}}},
    }


def send_feishu(title, body):
    if title is None or str(title).strip() == "":
        raise ValueError("标题不能为空")
    if body is None:
        raise ValueError("正文不能为空")
    webhook_url, timeout = _load_webhook_config()
    base_body = baseline()
    body_text = _normalize_text_block(body)
    full_body = f"{body_text}\n{base_body}" if body_text else base_body
    payload = _build_post_payload(str(title), full_body)
    return _post_message(webhook_url, payload, timeout)


if __name__ == "__main__":
    boot_time, uptime_minutes = get_uptime_minutes()
    print(f"服务器已运行时间: {uptime_minutes:.2f} 分钟")

    if uptime_minutes is not None:
        hostname = subprocess.check_output(["hostname"], text=True).strip()
        title = f"服务器 {hostname} 训练发信测试"
        body = f"服务器 {hostname} 已启动！"
        send_feishu(title, body)

        print("飞书消息发送成功！")
