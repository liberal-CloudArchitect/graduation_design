"""
Skills 模块 - 自动注册所有 Agent 技能

导入此模块时，所有子模块中通过 @skill_registry.register 装饰器
注册的技能会被自动加载到全局 skill_registry 中。
"""
from app.skills.registry import skill_registry

# 导入各分类技能模块，触发 @skill_registry.register 装饰器
import app.skills.academic.academic_skills  # noqa: F401
import app.skills.analysis.analysis_skills  # noqa: F401
import app.skills.utility.utility_skills  # noqa: F401
import app.skills.utility.util_skills  # noqa: F401
import app.skills.visualization.viz_skills  # noqa: F401

__all__ = ["skill_registry"]
