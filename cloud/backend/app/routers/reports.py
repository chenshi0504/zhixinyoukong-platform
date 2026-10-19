"""
报告管理路由：上传、列表、评分、下载。
"""
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..config import get_settings
from ..models.report import Report
from ..models.task import Task
from ..models.classroom import student_classes
from ..models.user import User
from ..schemas.report import ReportRead, GradeRequest
from ..schemas.common import PagedResponse

router = APIRouter(prefix="/api/cloud/reports", tags=["报告管理"])


@router.get("", response_model=PagedResponse[ReportRead])
def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    task_id: int | None = Query(None),
    student_id: int | None = Query(None),
    class_id: int | None = Query(None),
    file_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Report)
    joined_task = False
    if current_user.role == "student":
        q = q.filter(Report.student_id == current_user.id)
    elif current_user.role == "teacher":
        q = q.join(Task, Report.task_id == Task.id).filter(Task.teacher_id == current_user.id)
        joined_task = True
    elif current_user.role == "org_admin":
        q = q.join(Task, Report.task_id == Task.id).filter(Task.org_id == current_user.org_id)
        joined_task = True
    if task_id:
        q = q.filter(Report.task_id == task_id)
    if student_id and current_user.role != "student":
        q = q.filter(Report.student_id == student_id)
    if class_id:
        if not joined_task:
            q = q.join(Task, Report.task_id == Task.id)
        q = q.filter(Task.class_id == class_id)
    if status_filter:
        q = q.filter(Report.status == status_filter)
    if file_type:
        q = q.filter(Report.file_type == file_type)
    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(Report.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.post("/upload", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def upload_report(
    file: UploadFile = File(...),
    task_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("student")),
):
    task = db.query(Task).filter(Task.id == task_id, Task.status == "published").first()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或未发布")
    allowed = db.execute(
        student_classes.select().where(
            student_classes.c.student_id == current_user.id,
            student_classes.c.class_id == task.class_id,
        )
    ).first()
    if task.class_id is not None and allowed is None:
        raise HTTPException(status_code=403, detail="无权提交该任务")

    settings = get_settings()
    upload_dir = os.path.join(settings.upload_dir, "reports")
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, f"{task_id}_{current_user.id}_{file.filename}")
    content = file.file.read()
    existing = db.query(Report).filter(
        Report.task_id == task_id,
        Report.student_id == current_user.id,
        Report.is_independent == False,
    ).first()
    if existing and existing.file_path and existing.file_path != file_path and os.path.exists(existing.file_path):
        try:
            os.remove(existing.file_path)
        except OSError:
            pass
    with open(file_path, "wb") as f:
        f.write(content)

    if existing:
        existing.file_path = file_path
        existing.original_filename = file.filename
        existing.file_size = len(content)
        existing.file_type = "report"
        existing.description = None
        existing.score = None
        existing.feedback = None
        existing.grader_id = None
        existing.status = "submitted"
        existing.submitted_at = datetime.now(timezone.utc)
        existing.graded_at = None
        db.commit()
        db.refresh(existing)
        return existing

    report = Report(
        task_id=task_id,
        student_id=current_user.id,
        file_path=file_path,
        original_filename=file.filename,
        file_size=len(content),
        file_type="report",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.post("/upload/general", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def upload_general_file(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    task_id: int | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("student", "teacher")),
):
    """
    通用文件上传接口
    - 支持三种文件类型：data（实验数据）、report（报告文档）、config（配置文件）
    - task_id 可选，不关联任务时为独立文件
    - 文件大小限制：50MB
    - 支持的扩展名：.csv, .xlsx, .pdf, .docx, .xml, .json, .txt
    """
    if current_user.role == "teacher":
        raise HTTPException(status_code=403, detail="教师不能以学生身份上传任务报告")
    student_id = current_user.id
    if task_id is not None:
        task = db.query(Task).filter(Task.id == task_id, Task.status == "published").first()
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在或未发布")
        if task.class_id is not None:
            allowed = db.execute(
                student_classes.select().where(
                    student_classes.c.student_id == current_user.id,
                    student_classes.c.class_id == task.class_id,
                )
            ).first()
            if allowed is None:
                raise HTTPException(status_code=403, detail="无权提交该任务")

    # 验证文件类型
    allowed_extensions = {
        "data": [".csv", ".xlsx", ".xls"],
        "report": [".pdf", ".docx", ".doc", ".txt"],
        "config": [".xml", ".json", ".txt"],
    }

    if file_type not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file_type}，仅支持 data/report/config"
        )

    # 验证文件扩展名
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions[file_type]:
        raise HTTPException(
            status_code=400,
            detail=f"文件扩展名 {file_ext} 不匹配类型 {file_type}，允许的扩展名: {', '.join(allowed_extensions[file_type])}"
        )

    # 读取文件内容
    content = file.file.read()

    # 验证文件大小（50MB）
    MAX_FILE_SIZE = 50 * 1024 * 1024
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制（50MB），当前文件: {len(content) / (1024 * 1024):.2f}MB"
        )

    # 保存文件到 ./uploads/{file_type}/{student_id}/
    settings = get_settings()
    upload_dir = os.path.join(settings.upload_dir, file_type, str(student_id))
    os.makedirs(upload_dir, exist_ok=True)

    # 文件名：任务ID_时间戳_原文件名（如果有任务ID）或 时间戳_原文件名（独立文件）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if task_id:
        filename = f"{task_id}_{timestamp}_{file.filename}"
    else:
        filename = f"{timestamp}_{file.filename}"

    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # 创建数据库记录
    report = Report(
        task_id=task_id,
        student_id=student_id,
        file_path=file_path,
        original_filename=file.filename,
        file_size=len(content),
        file_type=file_type,
        description=description,
        is_independent=(task_id is None),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.put("/{report_id}/grade", response_model=ReportRead)
def grade_report(
    report_id: int,
    body: GradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "org_admin", "teacher")),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if current_user.role == "teacher":
        task = db.query(Task).filter(Task.id == report.task_id).first()
        if task is None or task.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权批阅该报告")
    report.score = body.score
    report.feedback = body.feedback
    report.grader_id = current_user.id
    report.status = "graded"
    report.graded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return report


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if current_user.role == "student" and report.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权下载该报告")
    if current_user.role == "teacher":
        task = db.query(Task).filter(Task.id == report.task_id).first()
        if task is None or task.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权下载该报告")
    if not report.file_path or not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(report.file_path, filename=report.original_filename)


@router.get("/student/{student_id}/files", response_model=PagedResponse[ReportRead])
def get_student_files(
    student_id: int,
    file_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("student", "teacher", "org_admin")),
):
    """获取学生的所有上传文件（支持分页和过滤）"""
    # 学生只能查看自己的文件
    if current_user.role == "student" and current_user.id != student_id:
        raise HTTPException(status_code=403, detail="无权查看其他学生的文件")

    q = db.query(Report).filter(Report.student_id == student_id)
    if current_user.role == "teacher":
        q = q.join(Task, Report.task_id == Task.id).filter(Task.teacher_id == current_user.id)
    if file_type:
        q = q.filter(Report.file_type == file_type)

    total = q.count()
    pages = (total + page_size - 1) // page_size if total > 0 else 1
    items = q.order_by(Report.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedResponse(items=items, total=total, page=page, page_size=page_size, pages=pages)


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("student", "teacher", "org_admin")),
):
    """删除文件（学生只能删除自己的，教师只能删除自己任务下的文件）"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")

    # 学生只能删除自己的文件
    if current_user.role == "student" and report.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除其他学生的文件")
    if current_user.role == "teacher":
        task = db.query(Task).filter(Task.id == report.task_id).first()
        if task is None or task.teacher_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权删除该文件")

    # 删除物理文件
    if report.file_path and os.path.exists(report.file_path):
        try:
            os.remove(report.file_path)
        except Exception as e:
            # 文件删除失败不影响数据库记录删除
            pass

    # 删除数据库记录
    db.delete(report)
    db.commit()
    return {"success": True, "message": "文件删除成功"}
