"""
云端文件上传服务
"""
import os
from typing import Optional
from app.cloud_client import create_cloud_session
from app.config import settings


class CloudFileService:
    """云端文件上传服务"""

    @staticmethod
    def upload_file(
        file_path: str,
        file_type: str,
        student_id: int,
        task_id: Optional[int] = None,
        description: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict:
        """
        上传文件到云端平台

        Args:
            file_path: 本地文件路径
            file_type: 文件类型（data/report/config）
            student_id: 学生 ID
            task_id: 任务 ID（可选）
            description: 文件描述（可选）
            token: JWT token

        Returns:
            上传结果字典，包含 file_id, file_url 等
        """
        cloud_url = settings.CLOUD_API_URL
        if not cloud_url:
            raise ValueError("云端服务未配置，请在设置中配置 CLOUD_API_URL")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            data = {
                "student_id": student_id,
                "file_type": file_type,
            }
            if task_id:
                data["task_id"] = task_id
            if description:
                data["description"] = description

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            with create_cloud_session(base_url=cloud_url) as session:
                resp = session.post(
                    f"{cloud_url}/api/cloud/reports/upload/general",
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=60,  # 文件上传需要更长超时
                )

            if resp.status_code in (200, 201):
                return resp.json()
            else:
                error_msg = f"上传失败: {resp.status_code}"
                try:
                    error_detail = resp.json().get("detail", resp.text)
                    error_msg = f"{error_msg} - {error_detail}"
                except:
                    error_msg = f"{error_msg} - {resp.text}"
                raise Exception(error_msg)

    @staticmethod
    def list_files(
        student_id: int,
        file_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        token: Optional[str] = None,
    ) -> dict:
        """
        获取学生的文件列表

        Args:
            student_id: 学生 ID
            file_type: 文件类型过滤（可选）
            page: 页码
            page_size: 每页数量
            token: JWT token

        Returns:
            文件列表字典
        """
        cloud_url = settings.CLOUD_API_URL
        if not cloud_url:
            raise ValueError("云端服务未配置")

        params = {
            "page": page,
            "page_size": page_size,
        }
        if file_type:
            params["file_type"] = file_type

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.get(
                f"{cloud_url}/api/cloud/reports/student/{student_id}/files",
                params=params,
                headers=headers,
                timeout=10,
            )

        if resp.status_code == 200:
            return resp.json()
        else:
            raise Exception(f"获取文件列表失败: {resp.status_code} {resp.text}")

    @staticmethod
    def delete_file(report_id: int, token: Optional[str] = None) -> bool:
        """
        删除云端文件

        Args:
            report_id: 报告 ID
            token: JWT token

        Returns:
            是否删除成功
        """
        cloud_url = settings.CLOUD_API_URL
        if not cloud_url:
            raise ValueError("云端服务未配置")

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with create_cloud_session(base_url=cloud_url) as session:
            resp = session.delete(
                f"{cloud_url}/api/cloud/reports/{report_id}",
                headers=headers,
                timeout=10,
            )

        if resp.status_code in (200, 204):
            return True
        else:
            raise Exception(f"删除文件失败: {resp.status_code} {resp.text}")
