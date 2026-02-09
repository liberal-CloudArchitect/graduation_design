"""
Visualization Skills - 数据可视化与图表生成技能

包含 1 个 Skill:
1. generate_statistical_chart - 使用 Seaborn 生成专业学术统计图表
"""
import io
import base64
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from app.skills.registry import skill_registry
from loguru import logger


class StatisticalChartInput(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="要绘图的列表数据")
    x: str = Field(..., description="横轴字段名")
    y: str = Field(..., description="纵轴字段名")
    chart_type: str = Field("bar", description="图表类型: bar, line, scatter, box")
    title: str = Field("Research Data Analysis", description="图表标题")


@skill_registry.register(
    name="generate_statistical_chart",
    description="根据提供的结构化数据，使用 Seaborn 生成专业的学术统计图表，并返回 Base64 图片编码。",
    input_schema=StatisticalChartInput,
    category="visualization",
    timeout=30.0,
)
async def generate_statistical_chart(
    data: List[Dict[str, Any]],
    x: str,
    y: str,
    chart_type: str = "bar",
    title: str = "Research Data Analysis",
):
    """使用 Seaborn 生成统计图表并返回 Base64 编码的 PNG"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd

    if not data:
        raise ValueError("数据不能为空")

    df = pd.DataFrame(data)

    if x not in df.columns:
        raise ValueError(f"字段 '{x}' 不存在于数据中，可用字段: {list(df.columns)}")
    if y not in df.columns:
        raise ValueError(f"字段 '{y}' 不存在于数据中，可用字段: {list(df.columns)}")

    plt.figure(figsize=(10, 6))
    sns.set_theme(style="whitegrid")

    # 尝试设置中文字体
    try:
        plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans", "Arial"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    chart_type_lower = chart_type.lower()
    if chart_type_lower == "bar":
        sns.barplot(data=df, x=x, y=y)
    elif chart_type_lower == "line":
        sns.lineplot(data=df, x=x, y=y)
    elif chart_type_lower == "scatter":
        sns.scatterplot(data=df, x=x, y=y)
    elif chart_type_lower == "box":
        sns.boxplot(data=df, x=x, y=y)
    else:
        plt.close()
        raise ValueError(f"不支持的图表类型: {chart_type}，支持: bar, line, scatter, box")

    plt.title(title)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    # 保存到内存缓冲区
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode("utf-8")

    return {
        "image_base64": img_str,
        "mime_type": "image/png",
        "chart_type": chart_type,
        "title": title,
        "data_rows": len(df),
    }
