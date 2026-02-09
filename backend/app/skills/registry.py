"""
Skill Registry - Agent 技能注册中心

负责管理、发现和调用 Agent 可用的原子技能。
支持：
- 装饰器注册
- 输入验证（Pydantic）
- OpenAI Function Calling 格式导出
- 按类别筛选
- 超时控制与沙箱化错误处理
"""
import asyncio
import functools
import inspect
from typing import Any, Dict, List, Optional, Callable, Type
from pydantic import BaseModel, Field
from loguru import logger


class SkillResult(BaseModel):
    """Skill 执行结果的标准包装"""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    skill_name: str = ""

    class Config:
        arbitrary_types_allowed = True


class Skill:
    """技能包装类"""

    DEFAULT_TIMEOUT = 60.0  # 默认超时秒数

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        input_schema: Type[BaseModel],
        category: str = "general",
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.name = name
        self.func = func
        self.description = description
        self.input_schema = input_schema
        self.category = category
        self.timeout = timeout

    async def run(self, **kwargs) -> SkillResult:
        """
        执行技能（含输入验证、超时控制、沙箱化错误处理）

        单个 Skill 的失败不会向上抛出异常，而是返回包含错误信息的 SkillResult。
        """
        try:
            # 1. 验证输入
            validated_input = self.input_schema(**kwargs)
            input_dict = validated_input.model_dump()

            # 2. 执行函数 (支持异步和同步)，带超时控制
            if inspect.iscoroutinefunction(self.func):
                result = await asyncio.wait_for(
                    self.func(**input_dict), timeout=self.timeout
                )
            else:
                # 在线程池中运行同步函数，同样带超时
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self.func(**input_dict)),
                    timeout=self.timeout,
                )

            logger.info(f"Skill '{self.name}' executed successfully")
            return SkillResult(success=True, data=result, skill_name=self.name)

        except asyncio.TimeoutError:
            msg = f"Skill '{self.name}' timed out after {self.timeout}s"
            logger.warning(msg)
            return SkillResult(success=False, error=msg, skill_name=self.name)
        except Exception as e:
            msg = f"Skill '{self.name}' execution failed: {e}"
            logger.error(msg)
            return SkillResult(success=False, error=msg, skill_name=self.name)


class SkillRegistry:
    """技能注册表"""

    def __init__(self):
        self.skills: Dict[str, Skill] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Type[BaseModel],
        category: str = "general",
        timeout: float = Skill.DEFAULT_TIMEOUT,
    ):
        """注册技能的装饰器"""

        def decorator(func: Callable):
            skill = Skill(
                name, func, description, input_schema, category, timeout
            )
            self.skills[name] = skill
            logger.debug(f"Skill registered: {name} [{category}]")

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await skill.run(**kwargs)

            return wrapper

        return decorator

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取技能"""
        return self.skills.get(name)

    def list_skills(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有技能及其描述（用于发送给 LLM）"""
        results = []
        for name, skill in self.skills.items():
            if category and skill.category != category:
                continue
            results.append({
                "name": name,
                "description": skill.description,
                "parameters": skill.input_schema.model_json_schema(),
                "category": skill.category,
            })
        return results

    def get_skills_by_categories(
        self, categories: List[str]
    ) -> List[Dict[str, Any]]:
        """按多个类别批量获取技能列表"""
        results = []
        for cat in categories:
            results.extend(self.list_skills(category=cat))
        return results

    # ---- OpenAI Function Calling 集成 ----

    def to_openai_functions(
        self, category: Optional[str] = None, categories: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        将注册的 Skills 转换为 OpenAI Function Calling 格式 (tools)。

        可按单个 category 或多个 categories 过滤。
        """
        functions = []
        for skill in self.skills.values():
            if category and skill.category != category:
                continue
            if categories and skill.category not in categories:
                continue
            functions.append({
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": skill.input_schema.model_json_schema(),
                },
            })
        return functions

    def get_skills_prompt(
        self, category: Optional[str] = None, categories: Optional[List[str]] = None
    ) -> str:
        """
        生成供 System Prompt 使用的 Skills 描述文本。

        让 LLM 了解可用的 Skills 并决定是否调用。
        """
        skills = []
        for name, skill in self.skills.items():
            if category and skill.category != category:
                continue
            if categories and skill.category not in categories:
                continue
            skills.append(skill)

        if not skills:
            return ""

        lines = [
            "你可以使用以下工具(Skills)来辅助完成任务。"
            "当你需要调用工具时，请在回复中使用如下 JSON 格式：",
            '{"skill_call": {"name": "<skill_name>", "arguments": {<参数>}}}',
            "",
            "可用工具列表：",
        ]

        for skill in skills:
            schema = skill.input_schema.model_json_schema()
            props = schema.get("properties", {})
            required = schema.get("required", [])
            params_parts = []
            for k, v in props.items():
                ptype = v.get("type", "any")
                pdesc = v.get("description", "")
                req_mark = "*" if k in required else ""
                params_parts.append(f"{k}{req_mark}({ptype}): {pdesc}")
            params_str = "; ".join(params_parts) if params_parts else "无参数"
            lines.append(f"- **{skill.name}** [{skill.category}]: {skill.description}")
            lines.append(f"  参数: {params_str}")

        lines.append("")
        lines.append("如果当前任务不需要调用工具，请直接回答。")
        return "\n".join(lines)


# 全局注册中心实例
skill_registry = SkillRegistry()
