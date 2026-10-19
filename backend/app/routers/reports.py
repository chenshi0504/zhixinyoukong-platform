"""
Report management API routes.
"""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import FileResponse, Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import os

from ..database import get_db
from ..models import User
from ..schemas import ReportResponse, ReportGrade, ErrorResponse
from ..services import report as report_service
from ..services.cloud_learning_proxy import (
    download_cloud_report,
    get_cloud_access_token,
    list_cloud_reports,
    upload_cloud_report,
)
from ..dependencies import get_current_teacher
from .auth import get_current_user

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@router.get("", response_model=List[dict] | List[ReportResponse])
async def get_reports(
    task_id: "Optional[int]" = Query(None, description="按任务ID筛选"),
    current_user: "User" = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: "Session" = Depends(get_db)
):
    """
    获取报告列表。
    
    - 学生: 只能看到自己提交的报告
    - 教师/管理员: 可以看到所有报告，可按任务筛选
    """
    if current_user.role == "student":
        cloud_token = get_cloud_access_token(token)
        if not cloud_token:
            return []
        return list_cloud_reports(cloud_token, task_id=task_id)
    reports = report_service.get_reports_by_user_role(db, current_user, task_id)
    return reports


@router.get("/pending", response_model=List[ReportResponse])
async def get_pending_reports(
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    获取待批阅的报告列表。
    
    仅教师和管理员可以访问。
    """
    reports = report_service.get_pending_reports(db)
    return reports


@router.post("", response_model=dict | ReportResponse, status_code=status.HTTP_201_CREATED, responses={
    400: {"model": ErrorResponse, "description": "提交失败"},
    404: {"model": ErrorResponse, "description": "任务不存在"}
})
async def submit_report(
    task_id: int = Query(..., description="任务ID"),
    file: UploadFile = File(..., description="报告文件"),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    提交实验报告。
    
    支持PDF和DOCX格式，文件大小限制10MB。
    如果已提交过报告，将覆盖之前的提交。
    """
    if current_user.role == "student":
        cloud_token = get_cloud_access_token(token)
        if not cloud_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "CLOUD_AUTH_REQUIRED",
                    "message": "该任务来自云端班级，请重新登录后提交",
                },
            )
        return await upload_cloud_report(cloud_token, task_id, file)
    report = await report_service.submit_report(db, task_id, current_user.id, file)
    return report


@router.get("/{report_id}", response_model=dict | ReportResponse, responses={
    404: {"model": ErrorResponse, "description": "报告不存在"}
})
async def get_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    获取报告详情。
    
    学生只能查看自己的报告。
    """
    if current_user.role == "student":
        cloud_token = get_cloud_access_token(token)
        if cloud_token:
            for report in list_cloud_reports(cloud_token):
                if report.get("id") == report_id:
                    return report

    report = report_service.get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_003",
                "message": "报告不存在",
                "suggestion": "请检查报告ID是否正确"
            }
        )
    
    # Students can only view their own reports
    if current_user.role == "student" and report.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权查看此报告",
                "suggestion": "您只能查看自己提交的报告"
            }
        )
    
    return report


@router.get("/{report_id}/download")
async def download_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    下载报告文件。
    """
    if current_user.role == "student":
        cloud_token = get_cloud_access_token(token)
        if cloud_token:
            content, headers, media_type = download_cloud_report(cloud_token, report_id)
            return Response(content=content, media_type=media_type, headers=headers)

    report = report_service.get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_003",
                "message": "报告不存在",
                "suggestion": "请检查报告ID是否正确"
            }
        )
    
    # Students can only download their own reports
    if current_user.role == "student" and report.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "无权下载此报告",
                "suggestion": "您只能下载自己提交的报告"
            }
        )
    
    if not os.path.exists(report.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RES_003",
                "message": "报告文件不存在",
                "suggestion": "文件可能已被删除"
            }
        )
    
    return FileResponse(
        path=report.file_path,
        filename=report.file_name,
        media_type="application/octet-stream"
    )


@router.put("/{report_id}/grade", response_model=ReportResponse, responses={
    404: {"model": ErrorResponse, "description": "报告不存在"},
    403: {"model": ErrorResponse, "description": "无权限"}
})
async def grade_report(
    report_id: int,
    grade_data: ReportGrade,
    current_user: User = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    """
    批阅报告。
    
    仅教师和管理员可以批阅报告。
    """
    report = report_service.grade_report(db, report_id, grade_data, current_user)
    return report
