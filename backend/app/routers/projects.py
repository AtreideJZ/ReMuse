"""项目空间 API。"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException

from ..db import get_pool
from ..schemas import ProjectCreate, ProjectListOut, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])

_SELECT = """
    SELECT p.*, COUNT(i.id)::int AS idea_count
    FROM projects p
    LEFT JOIN ideas i ON i.project_id = p.id
"""


@router.get("", response_model=ProjectListOut)
async def list_projects():
    pool = await get_pool()
    rows = await pool.fetch(f"{_SELECT} GROUP BY p.id ORDER BY p.created_at DESC")
    return ProjectListOut(items=[ProjectOut.model_validate(dict(r)) for r in rows])


@router.post("", status_code=201, response_model=ProjectOut)
async def create_project(body: ProjectCreate):
    pool = await get_pool()
    try:
        row = await pool.fetchrow(
            "INSERT INTO projects (name, description) VALUES ($1, $2) RETURNING id",
            body.name.strip(),
            body.description,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "项目名已存在") from None
    return await get_project(row["id"])


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID):
    pool = await get_pool()
    row = await pool.fetchrow(f"{_SELECT} WHERE p.id = $1 GROUP BY p.id", project_id)
    if row is None:
        raise HTTPException(404, "项目不存在")
    return ProjectOut.model_validate(dict(row))


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: UUID, body: ProjectUpdate):
    pool = await get_pool()
    sets: list[str] = []
    args: list = []
    if body.name is not None:
        args.append(body.name.strip())
        sets.append(f"name = ${len(args)}")
    if body.description is not None:
        args.append(body.description)
        sets.append(f"description = ${len(args)}")
    if not sets:
        return await get_project(project_id)
    args.append(project_id)
    try:
        result = await pool.execute(
            f"UPDATE projects SET {', '.join(sets)} WHERE id = ${len(args)}", *args
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, "项目名已存在") from None
    if result == "UPDATE 0":
        raise HTTPException(404, "项目不存在")
    return await get_project(project_id)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: UUID):
    """删除项目：其下灵感转为「无项目」而非被删除（AC-F006-02）。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE ideas SET project_id = NULL WHERE project_id = $1", project_id
            )
            result = await conn.execute(
                "DELETE FROM projects WHERE id = $1", project_id
            )
    if result == "DELETE 0":
        raise HTTPException(404, "项目不存在")
