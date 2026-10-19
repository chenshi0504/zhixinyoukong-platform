"""
Proxy helpers for class-bound cloud tasks and reports.

The local teaching UI keeps its own JWT, while classroom/task/report ownership now
lives in the cloud backend.  These helpers extract the embedded cloud JWT from the
local token and normalize cloud responses to the legacy local response shape.
"""
from __future__ import annotations

from typing import Any

import requests
from fastapi import HTTPException, UploadFile, status
from jose import JWTError, jwt

from ..cloud_client import create_cloud_session
from ..config import settings


def get_cloud_access_token(local_token: str) -> str | None:
    try:
        payload = jwt.decode(local_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    token = payload.get("cloud_access_token")
    return token if isinstance(token, str) and token.strip() else None


def _cloud_base_url() -> str:
    return (settings.CLOUD_API_URL or "").rstrip("/")


def _extract_error_message(resp: requests.Response, fallback: str) -> str:
    try:
        data = resp.json()
    except Exception:
        return fallback
    if isinstance(data, dict):
        detail = data.get("detail", fallback)
        if isinstance(detail, dict):
            return detail.get("message") or detail.get("detail") or fallback
        if isinstance(detail, str):
            return detail
    return fallback


def _cloud_error(resp: requests.Response, fallback: str) -> HTTPException:
    if resp.status_code == status.HTTP_401_UNAUTHORIZED:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "CLOUD_AUTH_EXPIRED",
                "message": "云端登录状态已过期，请重新登录本地平台",
            },
        )
    return HTTPException(
        status_code=resp.status_code,
        detail={
            "code": "CLOUD_PROXY_ERROR",
            "message": _extract_error_message(resp, fallback),
        },
    )


def _request_cloud(
    method: str,
    path: str,
    cloud_token: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: int = 20,
) -> requests.Response:
    cloud_url = _cloud_base_url()
    if not cloud_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CLOUD_NOT_CONFIGURED", "message": "云端服务未配置"},
        )

    headers = {"Authorization": f"Bearer {cloud_token}"}
    try:
        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.request(
                method,
                f"{cloud_url}{path}",
                params=params,
                json=json,
                data=data,
                files=files,
                headers=headers,
                timeout=timeout,
            )
    except requests.RequestException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "CLOUD_UNAVAILABLE", "message": "无法连接云端平台，请确认云端后端已启动"},
        )

    if resp.status_code >= 400:
        raise _cloud_error(resp, "云端接口返回异常")
    return resp


def _paged_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("items", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def normalize_task(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "title": item.get("title") or "未命名任务",
        "description": item.get("description"),
        "module_id": item.get("module_id"),
        "deadline": item.get("deadline"),
        "scoring_criteria": item.get("scoring_criteria"),
        "teacher_id": item.get("teacher_id") or 0,
        "status": item.get("status") or "published",
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "class_id": item.get("class_id"),
        "class_name": item.get("class_name"),
        "teacher_name": item.get("teacher_name"),
        "max_score": item.get("max_score"),
    }


def normalize_report(item: dict[str, Any]) -> dict[str, Any]:
    filename = item.get("file_name") or item.get("original_filename") or "未命名文件"
    return {
        "id": item.get("id"),
        "task_id": item.get("task_id"),
        "student_id": item.get("student_id"),
        "file_name": filename,
        "file_path": item.get("file_path") or "",
        "score": item.get("score"),
        "feedback": item.get("feedback"),
        "status": item.get("status") or "submitted",
        "is_late": bool(item.get("is_late", False)),
        "submitted_at": item.get("submitted_at"),
        "graded_at": item.get("graded_at"),
        "graded_by": item.get("graded_by") or item.get("grader_id"),
        "task_title": item.get("task_title"),
        "student_name": item.get("student_name"),
        "original_filename": filename,
        "file_size": item.get("file_size"),
        "file_type": item.get("file_type"),
        "description": item.get("description"),
        "is_independent": bool(item.get("is_independent", False)),
    }


def list_cloud_tasks(cloud_token: str, *, page_size: int = 50) -> list[dict[str, Any]]:
    resp = _request_cloud(
        "GET",
        "/api/cloud/tasks",
        cloud_token,
        params={"page_size": page_size},
    )
    return [normalize_task(item) for item in _paged_items(resp.json())]


def get_cloud_task(cloud_token: str, task_id: int) -> dict[str, Any] | None:
    for task in list_cloud_tasks(cloud_token):
        if task.get("id") == task_id:
            return task
    return None


def create_cloud_task(cloud_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = _request_cloud(
        "POST",
        "/api/cloud/tasks",
        cloud_token,
        json=payload,
        timeout=20,
    )
    return normalize_task(resp.json())


def publish_cloud_task(cloud_token: str, task_id: int) -> dict[str, Any]:
    resp = _request_cloud(
        "POST",
        f"/api/cloud/tasks/{task_id}/publish",
        cloud_token,
        timeout=20,
    )
    return normalize_task(resp.json())


def list_cloud_reports(
    cloud_token: str,
    *,
    task_id: int | None = None,
    page_size: int = 50,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"page_size": page_size}
    if task_id is not None:
        params["task_id"] = task_id
    resp = _request_cloud("GET", "/api/cloud/reports", cloud_token, params=params)
    return [normalize_report(item) for item in _paged_items(resp.json())]


async def upload_cloud_report(cloud_token: str, task_id: int, file: UploadFile) -> dict[str, Any]:
    content = await file.read()
    filename = file.filename or "report.pdf"
    content_type = file.content_type or "application/octet-stream"
    resp = _request_cloud(
        "POST",
        "/api/cloud/reports/upload",
        cloud_token,
        data={"task_id": str(task_id)},
        files={"file": (filename, content, content_type)},
        timeout=60,
    )
    return normalize_report(resp.json())


def download_cloud_report(cloud_token: str, report_id: int) -> tuple[bytes, dict[str, str], str]:
    resp = _request_cloud(
        "GET",
        f"/api/cloud/reports/{report_id}/download",
        cloud_token,
        timeout=60,
    )
    headers: dict[str, str] = {}
    for name in ("content-disposition",):
        value = resp.headers.get(name)
        if value:
            headers[name] = value
    return resp.content, headers, resp.headers.get("content-type", "application/octet-stream")


def upload_cloud_general_file(
    cloud_token: str,
    *,
    content: bytes,
    filename: str,
    content_type: str,
    file_type: str,
    task_id: int | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"file_type": file_type}
    if task_id is not None:
        data["task_id"] = str(task_id)
    if description:
        data["description"] = description
    resp = _request_cloud(
        "POST",
        "/api/cloud/reports/upload/general",
        cloud_token,
        data=data,
        files={"file": (filename, content, content_type)},
        timeout=60,
    )
    return normalize_report(resp.json())


def list_cloud_general_files(
    cloud_token: str,
    *,
    file_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if file_type:
        params["file_type"] = file_type
    resp = _request_cloud("GET", "/api/cloud/reports", cloud_token, params=params)
    data = resp.json()
    if isinstance(data, dict):
        data["items"] = [normalize_report(item) for item in _paged_items(data)]
        return data
    return {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 1}


def delete_cloud_report(cloud_token: str, report_id: int) -> bool:
    _request_cloud("DELETE", f"/api/cloud/reports/{report_id}", cloud_token)
    return True


def submit_cloud_password_change_request(
    cloud_token: str,
    *,
    old_password: str,
    new_password: str,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "old_password": old_password,
        "new_password": new_password,
    }
    if reason:
        payload["reason"] = reason
    resp = _request_cloud(
        "POST",
        "/api/cloud/auth/change-password",
        cloud_token,
        json=payload,
    )
    data = resp.json()
    return data if isinstance(data, dict) else {"message": "密码修改申请已提交"}


def list_self_algorithm_packs(cloud_token: str) -> list[dict[str, Any]]:
    resp = _request_cloud("GET", "/api/cloud/self-algorithms/packs", cloud_token)
    data = resp.json()
    return data if isinstance(data, list) else []


def download_self_algorithm_pack(cloud_token: str, algorithm_type: str) -> tuple[bytes, dict[str, str], str]:
    resp = _request_cloud(
        "GET",
        f"/api/cloud/self-algorithms/packs/{algorithm_type}/download",
        cloud_token,
        timeout=60,
    )
    headers: dict[str, str] = {}
    value = resp.headers.get("content-disposition")
    if value:
        headers["content-disposition"] = value
    return resp.content, headers, resp.headers.get("content-type", "application/zip")


async def upload_self_algorithm_submission(
    cloud_token: str,
    *,
    algorithm_type: str,
    code_file: UploadFile,
    spec_file: UploadFile,
    process_file: UploadFile,
    result_file: UploadFile,
    class_id: int | None = None,
    task_id: int | None = None,
) -> dict[str, Any]:
    code_content = await code_file.read()
    spec_content = await spec_file.read()
    process_content = await process_file.read()
    result_content = await result_file.read()
    data: dict[str, Any] = {"algorithm_type": algorithm_type}
    if class_id is not None:
        data["class_id"] = str(class_id)
    if task_id is not None:
        data["task_id"] = str(task_id)
    files = {
        "code_file": (
            code_file.filename or "algorithm.py",
            code_content,
            code_file.content_type or "text/x-python",
        ),
        "spec_file": (
            spec_file.filename or "方案说明.txt",
            spec_content,
            spec_file.content_type or "application/octet-stream",
        ),
        "process_file": (
            process_file.filename or "simulation_process.zip",
            process_content,
            process_file.content_type or "application/octet-stream",
        ),
        "result_file": (
            result_file.filename or "result.csv",
            result_content,
            result_file.content_type or "application/octet-stream",
        ),
    }
    resp = _request_cloud(
        "POST",
        "/api/cloud/self-algorithms/submissions",
        cloud_token,
        data=data,
        files=files,
        timeout=120,
    )
    data = resp.json()
    return data if isinstance(data, dict) else {}


def list_self_algorithm_submissions(
    cloud_token: str,
    *,
    algorithm_type: str | None = None,
    task_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if algorithm_type:
        params["algorithm_type"] = algorithm_type
    if task_id is not None:
        params["task_id"] = task_id
    resp = _request_cloud(
        "GET",
        "/api/cloud/self-algorithms/submissions",
        cloud_token,
        params=params,
    )
    data = resp.json()
    return data if isinstance(data, dict) else {"items": [], "total": 0, "page": page, "page_size": page_size, "pages": 1}


def download_self_algorithm_submission_file(
    cloud_token: str,
    submission_id: int,
    kind: str,
) -> tuple[bytes, dict[str, str], str]:
    resp = _request_cloud(
        "GET",
        f"/api/cloud/self-algorithms/submissions/{submission_id}/download/{kind}",
        cloud_token,
        timeout=60,
    )
    headers: dict[str, str] = {}
    value = resp.headers.get("content-disposition")
    if value:
        headers["content-disposition"] = value
    return resp.content, headers, resp.headers.get("content-type", "application/octet-stream")
