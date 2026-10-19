"""
Common dependencies for role-based access control.
"""
from functools import wraps
from typing import List
from fastapi import Depends, HTTPException, status

from .models import User, UserRole
from .routers.auth import get_current_user


class RoleChecker:
    """Dependency class for checking user roles."""
    
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
    
    def __call__(self, user: User = Depends(get_current_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERM_001",
                    "message": "无权访问此资源",
                    "suggestion": f"此操作需要以下角色之一: {', '.join(self.allowed_roles)}"
                }
            )
        return user


# Pre-configured role checkers
require_admin = RoleChecker([UserRole.ADMIN.value])
require_teacher = RoleChecker([UserRole.TEACHER.value, UserRole.ADMIN.value])
require_student = RoleChecker([UserRole.STUDENT.value])
require_teacher_or_student = RoleChecker([
    UserRole.TEACHER.value, 
    UserRole.STUDENT.value, 
    UserRole.ADMIN.value
])


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the current user is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "AUTH_004",
                "message": "用户已被禁用",
                "suggestion": "请联系管理员"
            }
        )
    return current_user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the current user is an admin."""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_003",
                "message": "仅管理员可执行此操作",
                "suggestion": "请使用管理员账户登录"
            }
        )
    return current_user


def get_current_teacher(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the current user is a teacher or admin."""
    if current_user.role not in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_002",
                "message": "仅教师可执行此操作",
                "suggestion": "请使用教师账户登录"
            }
        )
    return current_user


def get_current_student(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the current user is a student."""
    if current_user.role != UserRole.STUDENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PERM_001",
                "message": "仅学生可执行此操作",
                "suggestion": "请使用学生账户登录"
            }
        )
    return current_user
