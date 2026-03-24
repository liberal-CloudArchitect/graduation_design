"""
顶层测试 conftest

确保 backend/ 在 sys.path 中, 使 `from app.xxx import ...` 可用。

测试分类:
  - test_phase1_components.py: 纯单元测试, 无外部依赖, 可本地直接运行
  - test_quality_regressions.py: 需要完整 app 环境 (DB/Redis/etc.)
  - eval_baseline/: 需要运行中的后端 API 服务
"""
import asyncio
import inspect
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "asyncio: run async tests even when pytest-asyncio is unavailable",
    )


try:
    import pytest_asyncio  # noqa: F401
except ImportError:
    def pytest_pyfunc_call(pyfuncitem):
        test_func = pyfuncitem.obj
        if not inspect.iscoroutinefunction(test_func):
            return None

        kwargs = {
            name: pyfuncitem.funcargs[name]
            for name in pyfuncitem._fixtureinfo.argnames
        }
        asyncio.run(test_func(**kwargs))
        return True
