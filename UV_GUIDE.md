# UV 项目管理指南

本项目已使用 [uv](https://github.com/astral-sh/uv) 进行依赖管理。

## 常用命令

### 1. 安装依赖
```bash
uv sync
```

### 2. 运行项目
```bash
# 直接运行
uv run python main.py

# 或者指定参数
uv run python main.py --port 9000 --log-file app.log
```

### 3. 添加新依赖
```bash
uv add package-name
```

例如:
```bash
uv add requests
uv add pydantic
```

### 4. 移除依赖
```bash
uv remove package-name
```

### 5. 更新依赖
```bash
uv lock --upgrade
```

### 6. 查看依赖树
```bash
uv tree
```

### 7. 运行测试脚本
```bash
uv run python test.py
```

## 项目结构

- `pyproject.toml` - 项目配置和依赖声明
- `uv.lock` - 锁定的依赖版本(应提交到版本控制)
- `.python-version` - Python 版本要求
- `.venv/` - 虚拟环境目录(不应提交到版本控制)

## 优势

使用 uv 相比传统 pip/poetry 的优势:
- ⚡ 极快的依赖解析和安装速度
- 🔒 自动锁定依赖版本
- 📦 内置虚拟环境管理
- 🎯 简化的工作流程
