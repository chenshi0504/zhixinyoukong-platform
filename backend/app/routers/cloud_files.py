"""
云端文件管理路由
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from ..services.cloud_learning_proxy import (
    delete_cloud_report,
    download_cloud_report,
    get_cloud_access_token,
    list_cloud_general_files,
    upload_cloud_general_file,
)
from ..deps import get_current_user
from ..models.user import User

router = APIRouter(prefix="/api/v1/cloud/files", tags=["云端文件"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@router.post("/upload")
async def upload_to_cloud(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    task_id: int = Form(None),
    description: str = Form(None),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """
    上传文件到云端平台

    流程：
    1. 接收前端上传的文件
    2. 临时保存到本地
    3. 调用云端 API 上传
    4. 删除临时文件
    5. 返回上传结果
    """
    # 验证文件类型
    if file_type not in ["data", "report", "config"]:
        raise HTTPException(status_code=400, detail="文件类型必须是 data、report 或 config")

    cloud_token = get_cloud_access_token(token)
    if not cloud_token:
        raise HTTPException(status_code=403, detail="请使用云端班级账号重新登录后上传")

    content = await file.read()
    result = upload_cloud_general_file(
        cloud_token,
        content=content,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        file_type=file_type,
        task_id=task_id,
        description=description,
    )
    return {"success": True, "data": result}


@router.get("/list")
async def list_cloud_files(
    file_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """获取当前学生的云端文件列表"""
    cloud_token = get_cloud_access_token(token)
    if not cloud_token:
        return {"success": True, "data": {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 1}}
    result = list_cloud_general_files(
        cloud_token,
        file_type=file_type,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": result}


@router.get("/{report_id}/download")
async def download_cloud_file(
    report_id: int,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """下载当前用户有权限查看的云端文件。"""
    cloud_token = get_cloud_access_token(token)
    if not cloud_token:
        raise HTTPException(status_code=403, detail="请重新登录后下载")
    content, headers, media_type = download_cloud_report(cloud_token, report_id)
    return Response(content=content, media_type=media_type, headers=headers)


@router.delete("/{report_id}")
async def delete_cloud_file(
    report_id: int,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    """删除云端文件"""
    cloud_token = get_cloud_access_token(token)
    if not cloud_token:
        raise HTTPException(status_code=403, detail="请重新登录后删除")
    success = delete_cloud_report(cloud_token, report_id)
    return {"success": success, "message": "文件删除成功"}
