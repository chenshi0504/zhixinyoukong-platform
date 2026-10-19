"""
Services package.
"""
from .auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_token,
    authenticate_user,
    get_user_by_username,
    get_user_by_id
)
from .task import (
    create_task,
    get_task_by_id,
    get_tasks_for_teacher,
    get_all_tasks,
    get_published_tasks,
    get_tasks_by_user_role,
    update_task,
    delete_task,
    publish_task,
    close_task
)
from .report import (
    get_report_by_id,
    get_reports_by_task,
    get_reports_by_student,
    get_pending_reports,
    get_reports_by_user_role,
    submit_report,
    grade_report
)
from .user import (
    create_user,
    get_all_users,
    update_user,
    reset_password,
    delete_user,
    batch_import_students,
    generate_password
)

__all__ = [
    # Auth
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "decode_token",
    "authenticate_user",
    "get_user_by_username",
    "get_user_by_id",
    # Task
    "create_task",
    "get_task_by_id",
    "get_tasks_for_teacher",
    "get_all_tasks",
    "get_published_tasks",
    "get_tasks_by_user_role",
    "update_task",
    "delete_task",
    "publish_task",
    "close_task",
    # Report
    "get_report_by_id",
    "get_reports_by_task",
    "get_reports_by_student",
    "get_pending_reports",
    "get_reports_by_user_role",
    "submit_report",
    "grade_report",
    # User
    "create_user",
    "get_all_users",
    "update_user",
    "reset_password",
    "delete_user",
    "batch_import_students",
    "generate_password"
]
