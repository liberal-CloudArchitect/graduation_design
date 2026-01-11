"""
Paper Model
"""
from datetime import datetime, date
from typing import Optional, List, Any
from sqlalchemy import String, Text, Boolean, DateTime, Integer, Date, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.models.database import Base


class Paper(Base):
    """文献模型"""
    __tablename__ = "papers"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # 基础信息
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)  # [{name, affiliation, email}]
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)  # ["keyword1", "keyword2"]
    
    # 来源信息
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # upload, semantic_scholar, arxiv
    doi: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # 文件信息
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 向量索引
    vector_ids: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)  # Milvus中的向量ID列表
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # 处理状态
    status: Mapped[str] = mapped_column(
        String(50), 
        default="pending", 
        index=True
    )  # pending, processing, completed, failed
    parse_result: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="papers")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="papers")
    notes: Mapped[List["Note"]] = relationship(
        "Note",
        back_populates="paper",
        cascade="all, delete-orphan"
    )


class Note(Base):
    """文献笔记模型"""
    __tablename__ = "notes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    highlight_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # 关联关系
    paper: Mapped["Paper"] = relationship("Paper", back_populates="notes")


class Conversation(Base):
    """对话历史模型"""
    __tablename__ = "conversations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    messages: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)  # [{role, content, references, timestamp}]
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # 关联关系
    user: Mapped["User"] = relationship("User", back_populates="conversations")
