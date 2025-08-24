#!/bin/bash
# 初始化日志
log_file=$HOME/auto_resume_$(date +%Y%m%d_%H%M%S).log
exec > >(tee -a "$log_file") 2>&1
echo "[$(date)] Script started"

# 显式加载conda
source $HOME/miniconda3/etc/profile.d/conda.sh || {
    echo "[$(date)] Error: Failed to load conda"
    exit 1
}

# 控制开关
USE_THIS_SCRIPT=true  # TODO: true / false 是否启用该脚本

if $USE_THIS_SCRIPT; then

# 检测进程是否已存在
monitor_process="train"  # TODO: 监控进程名
while pgrep -f "$monitor_process" >/dev/null; do  # 若存在，不退出，而是隔一会监视一次
    echo "[$(date)] Process '$monitor_process' is running, waiting 10 minutes..."
    sleep 600  # 等待10分钟（600秒）
done
    
echo "[$(date)] Process '$monitor_process' not found, starting training..."

# 启动训练程序  # TODO: 训练指令
cd $HOME/Projects
source $HOME/miniconda3/bin/activate test_env
python test_auto_resume.py

fi