import numpy as np
import torch

def show_data(data, indent_level=0):
    """
    递归可视化数据结构
    
    Args:
        data: 要可视化的数据
        indent_level: 当前递归层级，用于缩进显示
    """
    indent = "  " * indent_level  # 根据层级调整缩进
    
    if isinstance(data, dict):
        for key in data.keys():
            print(f"{indent}{key}:")
            show_data(data[key], indent_level + 1)
    elif isinstance(data, list):
        print(f"{indent}List[{len(data)}]:")
        if len(data) > 0:
            show_data(data[0], indent_level + 1)
    elif isinstance(data, (torch.Tensor, np.ndarray)):
        # 处理张量和numpy数组
        data_type = type(data).__name__
        dtype = str(data.dtype)
        shape = data.shape
        if hasattr(data, 'max') and hasattr(data, 'min'):
            max_val = data.max().item() if hasattr(data.max(), 'item') else data.max()
            min_val = data.min().item() if hasattr(data.min(), 'item') else data.min()
        else:
            max_val = "N/A"
            min_val = "N/A"
        print(f"{indent}{data_type}(dtype={dtype}, shape={shape}, max={max_val}, min={min_val})")
    elif isinstance(data, (int, float, str, bool)):
        # 处理基本数据类型
        print(f"{indent}{type(data).__name__}: {data}")
    else:
        # 处理其他类型
        print(f"{indent}{type(data).__name__}: {str(data)[:100]}{'...' if len(str(data)) > 100 else ''}")