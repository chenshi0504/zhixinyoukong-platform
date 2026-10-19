"""
API routers package.
"""
import importlib
import logging
import traceback

from fastapi import APIRouter

logger = logging.getLogger(__name__)
ROUTER_LOAD_ERRORS = {}

def safe_load_router(module_name: str) -> APIRouter:
    try:
        module = importlib.import_module(f".{module_name}", __name__)
        ROUTER_LOAD_ERRORS.pop(module_name, None)
        return getattr(module, "router")
    except Exception as exc:
        ROUTER_LOAD_ERRORS[module_name] = {
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        logger.error(
            "Required router %s failed to load: %s\n%s",
            module_name,
            exc,
            ROUTER_LOAD_ERRORS[module_name]["traceback"],
        )
        return APIRouter()

auth_router = safe_load_router("auth")
tasks_router = safe_load_router("tasks")
reports_router = safe_load_router("reports")
users_router = safe_load_router("users")
experiments_router = safe_load_router("experiments")
algorithms_router = safe_load_router("algorithm_proxy")
algorithm_templates_router = safe_load_router("algorithm_templates")
algorithm_scripts_router = safe_load_router("algorithm_scripts")

__all__ = [
    "auth_router", "tasks_router", "reports_router",
    "users_router", "experiments_router", "algorithms_router",
    "algorithm_templates_router", "algorithm_scripts_router",
    "ROUTER_LOAD_ERRORS"
]
