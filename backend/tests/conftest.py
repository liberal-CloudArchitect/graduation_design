"""
顶层测试 conftest

确保 backend/ 在 sys.path 中, 使 `from app.xxx import ...` 可用。

测试分类:
  - test_phase1_components.py: 纯单元测试, 无外部依赖, 可本地直接运行
  - test_quality_regressions.py: 需要完整 app 环境 (DB/Redis/etc.)
  - eval_baseline/: 需要运行中的后端 API 服务
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
