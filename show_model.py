def show_model(model, prefix=""):
    """树状结构打印模型(只显示叶子节点的参数)"""
    children = list(model.named_children())
    last_idx = len(children) - 1
    
    for idx, (name, module) in enumerate(children):
        connector = "└── " if idx == last_idx else "├── "
        
        # 如果是叶子节点(没有子模块)
        if not list(module.children()):
            module_str = str(module).replace('\n', '\n' + prefix + '    ')
            print(prefix + connector + name + f" {module_str}")
        else:
            print(prefix + connector + name + f" ({module.__class__.__name__})")
            
        next_prefix = prefix + ("    " if idx == last_idx else "│   ")
        if list(module.children()):
            show_model(module, next_prefix)