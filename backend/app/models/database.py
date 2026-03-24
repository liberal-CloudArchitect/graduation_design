"""
Database Models - Base and Engine Setup
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

from app.core.config import settings

# 命名约定
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """SQLAlchemy Base类"""
    metadata = metadata


_engine = None
_session_factory: Optional[async_sessionmaker] = None


def get_engine():
    """Create the async engine lazily.

    This keeps lightweight imports usable in test environments that do not have
    database drivers installed, while preserving runtime behavior for real DB
    access paths.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            future=True,
        )
    return _engine


def get_async_session_maker():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


class _EngineProxy:
    def __getattr__(self, name):
        return getattr(get_engine(), name)


class _AsyncSessionMakerProxy:
    def __call__(self, *args, **kwargs):
        return get_async_session_maker()(*args, **kwargs)


engine = _EngineProxy()
async_session_maker = _AsyncSessionMakerProxy()


async def init_db():
    """初始化数据库表"""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
