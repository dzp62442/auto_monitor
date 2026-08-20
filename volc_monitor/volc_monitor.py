"""只读监控火山引擎机器学习任务，并在状态变化时发送飞书通知。"""

import argparse
import fcntl
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from auto_monitor.send_feishu import send_feishu
from dotenv import dotenv_values


ACTIVE_STATUSES = ("Initialized", "Queue", "Staging", "Running", "Killing")
TERMINAL_STATUSES = ("Success", "Failed", "Exception", "Killed")
ALL_STATUSES = ACTIVE_STATUSES + TERMINAL_STATUSES
FORCED_HOURS = {9, 12, 15, 18, 21}
INTERVAL_SECONDS = 15 * 60
NOTIFICATION_DELAY_MIN_SECONDS = 30
NOTIFICATION_DELAY_MAX_SECONDS = 90
RECENT_COUNT = 5
TIMEZONE = ZoneInfo("Asia/Shanghai")

DEFAULT_STATE_FILE = Path.home() / ".local/state/auto_monitor/volc_monitor_state.json"
DEFAULT_LOCK_FILE = Path.home() / ".local/state/auto_monitor/volc_monitor.lock"
DEFAULT_FEISHU_ENV_FILE = Path.home() / ".volc_monitor_env"
FEISHU_WEBHOOK_KEY = "VOLC_MONITOR_FEISHU_WEBHOOK_URL"
TASK_PREFIX_KEY = "VOLC_MONITOR_TASK_PREFIX"
FEISHU_BODY_SPACER = "\u200b"

ACTIVE_LABELS = {
    "Initialized": ("⚪", "初始化"),
    "Queue": ("🟡", "排队中"),
    "Staging": ("🟠", "调度中"),
    "Running": ("🟢", "运行中"),
    "Killing": ("🔴", "结束中"),
}
TERMINAL_LABELS = {
    "Success": ("✅", "成功"),
    "Failed": ("❌", "失败"),
    "Exception": ("❌", "异常"),
    "Killed": ("⛔", "已终止"),
}


def _extract_json_list(raw: str) -> list[dict[str, Any]]:
    """从 volc CLI 输出中提取 JSON 数组，容忍 JSON 前的版本提示。"""
    decoder = json.JSONDecoder()
    for line_start in (0, *(index + 1 for index, char in enumerate(raw) if char == "\n")):
        candidate = raw[line_start:].lstrip()
        if not candidate.startswith("["):
            continue
        try:
            value, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    raise ValueError("volc CLI 输出中没有可解析的 JSON 任务列表")


def _compact_error(stdout: str, stderr: str, returncode: int) -> str:
    lines = [line.strip() for line in f"{stderr}\n{stdout}".splitlines() if line.strip()]
    detail = " ".join(lines[-3:]) if lines else "无详细输出"
    return f"volc ml_task list 失败（退出码 {returncode}）：{detail}"[:2000]


def query_tasks(task_prefix: str, timeout: int = 120) -> list[dict[str, Any]]:
    """仅通过 ``volc ml_task list`` 读取任务，不调用任何写操作。"""
    command = [
        "volc",
        "ml_task",
        "list",
        "-n",
        task_prefix,
        "--status",
        ",".join(ALL_STATUSES),
        "--limit",
        "100",
        "--offset",
        "0",
        "--output",
        "json",
        "--format=JobId,JobName,Status,Start,End",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 volc 命令，请先安装并配置 Volc CLI") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"volc ml_task list 超过 {timeout} 秒未返回") from exc

    if result.returncode != 0:
        raise RuntimeError(_compact_error(result.stdout, result.stderr, result.returncode))

    try:
        return _extract_json_list(f"{result.stdout}\n{result.stderr}")
    except ValueError as exc:
        raise RuntimeError(_compact_error(result.stdout, result.stderr, result.returncode)) from exc


def _task_record(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": task.get("JobName"),
        "id": task.get("JobId"),
        "status": task.get("Status"),
        "start": task.get("Start"),
        "end": task.get("End"),
    }


def build_snapshot(tasks: list[dict[str, Any]], task_prefix: str) -> dict[str, Any]:
    """构造用于比较的稳定快照，不使用签名或指纹。"""
    ordered = sorted(
        tasks,
        key=lambda task: (str(task.get("Start") or ""), str(task.get("JobId") or "")),
        reverse=True,
    )
    active = [_task_record(task) for task in ordered if task.get("Status") in ACTIVE_STATUSES]
    recent = [
        _task_record(task) for task in ordered if task.get("Status") in TERMINAL_STATUSES
    ][:RECENT_COUNT]
    return {
        "read_status": "ok",
        "task_prefix": task_prefix,
        "active": active,
        "recent": recent,
    }


def _error_snapshot(error: Exception, task_prefix: str) -> dict[str, Any]:
    return {
        "read_status": "error",
        "task_prefix": task_prefix,
        "error": str(error)[:2000],
    }


def _read_state(path: Path) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"无法读取上次状态，本轮按首次状态处理：{exc}", flush=True)
        return None


def _write_state(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _load_env_value(key: str, path: Path = DEFAULT_FEISHU_ENV_FILE) -> str:
    try:
        value = dotenv_values(path).get(key)
    except OSError as exc:
        raise RuntimeError(f"无法读取 {path}：{exc}") from exc
    if not value or not str(value).strip():
        raise RuntimeError(f"{key} 未配置，请检查 {path}")
    return str(value).strip()


def _load_feishu_webhook(path: Path = DEFAULT_FEISHU_ENV_FILE) -> str:
    return _load_env_value(FEISHU_WEBHOOK_KEY, path)


def _load_task_prefix(path: Path = DEFAULT_FEISHU_ENV_FILE) -> str:
    return _load_env_value(TASK_PREFIX_KEY, path)


def _short_time(value: Any) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(str(value)).astimezone(TIMEZONE).strftime("%m-%d %H:%M")
    except ValueError:
        return str(value)[5:16].replace("T", " ")


def is_forced_slot(moment: datetime) -> bool:
    local = moment.astimezone(TIMEZONE) if moment.tzinfo else moment.replace(tzinfo=TIMEZONE)
    return local.minute == 0 and local.hour in FORCED_HOURS


def next_check_epoch(now_epoch: Optional[float] = None) -> int:
    now = time.time() if now_epoch is None else now_epoch
    return (int(now) // INTERVAL_SECONDS + 1) * INTERVAL_SECONDS


def _notification_reason(
    previous: Optional[dict[str, Any]], snapshot: dict[str, Any], moment: datetime
) -> Optional[str]:
    if previous is None:
        return "首次状态"
    if snapshot != previous:
        return "状态变化"
    if is_forced_slot(moment):
        return "固定整点播报"
    return None


def format_report(snapshot: dict[str, Any], moment: datetime, reason: str) -> str:
    local = moment.astimezone(TIMEZONE) if moment.tzinfo else moment.replace(tzinfo=TIMEZONE)
    time_text = local.strftime("%m-%d %H:%M")
    lines = [f"{time_text}｜{reason}"]

    if snapshot.get("read_status") != "ok":
        lines.extend(
            ["", "【状态读取失败】", "", f"⚠️ {snapshot.get('error') or '未知错误'}"]
        )
    else:
        active = snapshot.get("active", [])
        recent = snapshot.get("recent", [])
        lines.extend(["", "【运行中】"])

        if not active:
            lines.extend(["", "无"])
        for task in active:
            status = task.get("status")
            icon, label = ACTIVE_LABELS.get(status, ("⚪", str(status)))
            status_line = label
            if status == "Running":
                status_line = f"{label}｜{_short_time(task.get('start'))}"
            lines.extend(
                ["", f"{icon} {task.get('name') or '-'}", status_line, task.get("id") or "-"]
            )

        lines.extend(["", "【近期结束】"])
        if not recent:
            lines.extend(["", "无"])
        for task in recent:
            icon, label = TERMINAL_LABELS.get(
                task.get("status"), ("⚪", str(task.get("status")))
            )
            lines.extend(
                [
                    "",
                    f"{icon} {task.get('name') or '-'}",
                    f"{label}｜{_short_time(task.get('start'))}｜{_short_time(task.get('end'))}",
                ]
            )

    # send_feishu 会裁掉正文末尾的普通空白行；零宽空格可保留一个视觉空行。
    lines.append(FEISHU_BODY_SPACER)
    return "\n".join(lines)


def check_once(
    task_prefix: str,
    state_file: Path = DEFAULT_STATE_FILE,
    moment: Optional[datetime] = None,
    dry_run: bool = False,
) -> bool:
    """执行一次检查；返回本轮是否需要通知。"""
    checked_at = moment or datetime.now(TIMEZONE)
    timestamp = checked_at.astimezone(TIMEZONE).strftime("%m-%d %H:%M")
    try:
        snapshot = build_snapshot(query_tasks(task_prefix=task_prefix), task_prefix)
    except Exception as exc:
        print(f"[{timestamp}] 火山任务查询失败：{exc}", file=sys.stderr, flush=True)
        snapshot = _error_snapshot(exc, task_prefix)

    previous = _read_state(state_file)
    if previous is not None and "task_prefix" not in previous:
        previous["task_prefix"] = task_prefix
    reason = _notification_reason(previous, snapshot, checked_at)
    if reason is None:
        print(f"[{timestamp}] 状态无变化，本轮不发送。", flush=True)
        return False

    report = format_report(snapshot, checked_at, reason)
    print(report, flush=True)
    if dry_run:
        print(f"[{timestamp}] DRY-RUN：应发送，未调用飞书、未更新状态。", flush=True)
        return True

    notification_delay = random.randint(
        NOTIFICATION_DELAY_MIN_SECONDS, NOTIFICATION_DELAY_MAX_SECONDS
    )
    print(
        f"[{timestamp}] 查询完成，通知原因：{reason}；"
        f"随机延迟 {notification_delay} 秒后发送飞书。",
        flush=True,
    )
    time.sleep(notification_delay)

    try:
        webhook_url = _load_feishu_webhook()
    except RuntimeError as exc:
        print(f"[{timestamp}] 飞书配置错误：{exc}", file=sys.stderr, flush=True)
        return True

    if not send_feishu("火山任务监控", report, webhook_url=webhook_url):
        print(
            f"[{timestamp}] 飞书发送失败，状态未更新；"
            "状态变化可在下一次查询再次触发，固定播报本轮不补发。",
            file=sys.stderr,
            flush=True,
        )
        return True

    try:
        _write_state(state_file, snapshot)
    except OSError as exc:
        print(f"[{timestamp}] 状态保存失败，下一个整刻可能重复通知：{exc}", file=sys.stderr, flush=True)
    return True


def _run_daemon(task_prefix: str, state_file: Path) -> None:
    while True:
        scheduled_epoch = next_check_epoch()
        scheduled_at = datetime.fromtimestamp(scheduled_epoch, TIMEZONE)
        delay = max(0.0, scheduled_epoch - time.time())
        print(
            f"下一次检查：{scheduled_at.strftime('%m-%d %H:%M')}（{delay:.0f} 秒后）",
            flush=True,
        )
        time.sleep(delay)
        try:
            check_once(task_prefix=task_prefix, state_file=state_file, moment=scheduled_at)
        except Exception as exc:
            # 不让单次未预期异常终止长驻服务。
            print(f"[{scheduled_at:%m-%d %H:%M}] 监控程序异常：{exc}", file=sys.stderr, flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读监控指定前缀的火山机器学习任务")
    parser.add_argument("--once", action="store_true", help="立即检查一次后退出")
    parser.add_argument("--dry-run", action="store_true", help="只打印应发内容，不发飞书也不更新状态")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE, help="上次通知状态的保存路径")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    state_file = args.state_file.expanduser()
    try:
        task_prefix = _load_task_prefix()
    except RuntimeError as exc:
        print(f"监控配置错误：{exc}", file=sys.stderr, flush=True)
        return 2
    if args.once:
        check_once(task_prefix=task_prefix, state_file=state_file, dry_run=args.dry_run)
        return 0

    DEFAULT_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_LOCK_FILE.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("已有 volc_monitor 实例在运行，本次不重复启动。", file=sys.stderr)
            return 1
        try:
            _run_daemon(task_prefix=task_prefix, state_file=state_file)
        except KeyboardInterrupt:
            print("volc_monitor 已停止。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
