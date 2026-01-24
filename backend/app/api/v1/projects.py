"""
Projects API - 项目管理路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from app.core.deps import get_db, get_current_user
from app.models.user import User, Project
from app.models.paper import Paper


router = APIRouter()


# ============ Schemas ============

class ProjectCreate(BaseModel):
    """创建项目请求"""
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    """更新项目请求"""
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    """项目响应"""
    id: int
    name: str
    description: Optional[str]
    paper_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    items: List[ProjectResponse]
    total: int
    page: int
    page_size: int


# ============ Routes ============

@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取项目列表
    
    - **page**: 页码
    - **page_size**: 每页数量
    """
    # 查询总数
    count_query = select(func.count(Project.id)).where(
        Project.user_id == current_user.id
    )
    total = await db.scalar(count_query)
    
    # 分页查询
    query = select(Project).where(
        Project.user_id == current_user.id
    ).order_by(
        Project.updated_at.desc()
    ).offset(
        (page - 1) * page_size
    ).limit(page_size)
    
    result = await db.execute(query)
    projects = result.scalars().all()
    
    # 获取每个项目的文献数量
    items = []
    for project in projects:
        paper_count = await db.scalar(
            select(func.count(Paper.id)).where(Paper.project_id == project.id)
        )
        items.append(ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            paper_count=paper_count or 0,
            created_at=project.created_at,
            updated_at=project.updated_at
        ))
    
    return ProjectListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建新项目"""
    project = Project(
        name=project_data.name,
        description=project_data.description,
        user_id=current_user.id
    )
    
    db.add(project)
    await db.commit()
    await db.refresh(project)
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        paper_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取项目详情"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在"
        )
    
    paper_count = await db.scalar(
        select(func.count(Paper.id)).where(Paper.project_id == project.id)
    )
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        paper_count=paper_count or 0,
        created_at=project.created_at,
        updated_at=project.updated_at
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新项目"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在"
        )
    
    # 更新字段
    if project_data.name is not None:
        project.name = project_data.name
    if project_data.description is not None:
        project.description = project_data.description
    
    project.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(project)
    
    paper_count = await db.scalar(
        select(func.count(Paper.id)).where(Paper.project_id == project.id)
    )
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        paper_count=paper_count or 0,
        created_at=project.created_at,
        updated_at=project.updated_at
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除项目"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id
        )
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在"
        )
    
    await db.delete(project)
    await db.commit()
