"""
FastAPI 依赖注入模块
提供通用的依赖项，如获取当前用户等
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .services.auth import decode_token, get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "AUTH_003",
            "message": "令牌无效",
            "suggestion": "请重新登录"
        },
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = decode_token(token)
    if token_data is None:
        raise credentials_exception
    
    user = get_user_by_id(db, token_data.user_id)
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_004",
                "message": "用户已被禁用",
                "suggestion": "请联系管理员"
            }
        )
    
    return user


def require_role(*roles: str):
    """
    创建一个依赖项，要求用户具有指定角色之一
    
    用法:
        @router.get("/admin-only")
        def admin_endpoint(user: User = Depends(require_role("admin"))):
            ...
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERM_001",
                    "message": "权限不足",
                    "suggestion": f"需要以下角色之一: {', '.join(roles)}"
                }
            )
        return current_user
    return role_checker
