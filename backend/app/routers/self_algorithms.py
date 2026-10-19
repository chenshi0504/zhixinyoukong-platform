"""
本地平台自研算法代理路由。
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer

from ..deps import get_current_user
from ..models.user import User
from ..services.cloud_learning_proxy import (
    download_self_algorithm_pack,
    download_self_algorithm_submission_file,
    get_cloud_access_token,
    list_self_algorithm_packs,
    list_self_algorithm_submissions,
    upload_self_algorithm_submission,
)

router = APIRouter(prefix="/api/v1/self-algorithms", tags=["自研算法"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PACK_ROOT = _BACKEND_ROOT / "algorithms" / "student_packs"
_LOCAL_PACKS = {
    "data_fusion": {
        "dir": "data_fusion",
        "label": "多源数据融合自研算法",
        "description": "基于路侧检测与点云特征，提交自研多源感知融合结果并与平台贝叶斯融合 baseline 对比。",
    },
    "traffic_reconstruction": {
        "dir": "traffic_reconstruction",
        "label": "交通流重构自研算法",
        "description": "基于 DTALite 路网、观测流量和验证样本，提交自研交通流重构结果。",
    },
    "traffic_prediction": {
        "dir": "traffic_prediction",
        "label": "交通流预测自研算法",
        "description": "基于历史交通流特征，提交短时流量预测结果并与平台决策树 baseline 对比。",
    },
    "signal_optimization": {
        "dir": "signal_optimization",
        "label": "上层-交通信号优化",
        "description": "基于单点交叉口场景，提交自研信号配时结果并与平台 baseline 对比。",
    },
    "path_guidance": {
        "dir": "path_guidance",
        "label": "中层-路径诱导",
        "description": "基于 SiouxFalls 路网 OD 与边权数据，提交自研路径诱导结果。",
    },
    "vehicle_speed_control": {
        "dir": "vehicle_speed_control",
        "label": "下层-车速控制",
        "description": "基于车辆控制指标模板，提交自研车速控制仿真结果。",
    },
    "coordination_control": {
        "dir": "coordination_control",
        "label": "三层级协同对比",
        "description": "基于无协同、局部协同、全协同 baseline，提交三层级协同控制对比结果。",
    },
}


def _require_cloud_token(token: str) -> str:
    cloud_token = get_cloud_access_token(token)
    if not cloud_token:
        raise HTTPException(status_code=403, detail="请使用云端班级账号重新登录后访问自研算法功能")
    return cloud_token


def _read_pack_metadata(pack_dir: Path) -> dict[str, Any]:
    metadata_path = pack_dir / "metadata.json"
    if not metadata_path.is_file():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _local_pack_schema(algorithm_type: str, item: dict[str, str]) -> dict[str, Any] | None:
    pack_dir = _PACK_ROOT / item["dir"]
    if not pack_dir.is_dir():
        return None
    metadata = _read_pack_metadata(pack_dir)
    baseline_file = metadata.get("baseline_file")
    if not baseline_file and (pack_dir / "baseline_predictions.csv").is_file():
        baseline_file = "baseline_predictions.csv"
    primary_metric = metadata.get("primary_metric")
    if not primary_metric and isinstance(metadata.get("evaluation"), dict):
        primary_metric = metadata["evaluation"].get("primary_metric")
    return {
        "algorithm_type": algorithm_type,
        "label": item["label"],
        "description": item["description"],
        "baseline_file": baseline_file,
        "primary_metric": primary_metric,
        "input_files": metadata.get("input_files") or [],
        "submission_columns": metadata.get("submission_columns") or [],
        "download_name": f"{algorithm_type}_基础数据包.zip",
    }


def _list_local_packs() -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    for algorithm_type, item in _LOCAL_PACKS.items():
        schema = _local_pack_schema(algorithm_type, item)
        if schema:
            packs.append(schema)
    return packs


def _download_headers(filename: str, ascii_fallback: str) -> dict[str, str]:
    encoded = quote(filename)
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"
        )
    }


def _build_local_pack_response(algorithm_type: str) -> Response:
    item = _LOCAL_PACKS.get(algorithm_type)
    if not item:
        raise HTTPException(status_code=404, detail="自研算法类型不存在")
    pack_dir = _PACK_ROOT / item["dir"]
    if not pack_dir.is_dir():
        raise HTTPException(status_code=404, detail="基础数据包不存在")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(pack_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=str(file_path.relative_to(pack_dir)))
    filename = f"{algorithm_type}_基础数据包.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers=_download_headers(filename, f"{algorithm_type}_pack.zip"),
    )


@router.get("/packs")
async def get_packs(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    local_packs = _list_local_packs()
    try:
        cloud_token = _require_cloud_token(token)
        cloud_packs = list_self_algorithm_packs(cloud_token)
    except HTTPException:
        cloud_packs = []

    merged: dict[str, dict[str, Any]] = {}
    for pack in local_packs:
        merged[pack["algorithm_type"]] = pack
    for pack in cloud_packs:
        algorithm_type = pack.get("algorithm_type")
        if isinstance(algorithm_type, str):
            merged.setdefault(algorithm_type, pack)
    return {"success": True, "data": list(merged.values())}


@router.get("/packs/{algorithm_type}/download")
async def download_pack(
    algorithm_type: str,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    if algorithm_type in _LOCAL_PACKS and (_PACK_ROOT / _LOCAL_PACKS[algorithm_type]["dir"]).is_dir():
        return _build_local_pack_response(algorithm_type)

    cloud_token = _require_cloud_token(token)
    content, headers, media_type = download_self_algorithm_pack(cloud_token, algorithm_type)
    return Response(content=content, media_type=media_type, headers=headers)


@router.post("/submissions")
async def submit_algorithm(
    algorithm_type: str = Form(...),
    class_id: int | None = Form(None),
    task_id: int | None = Form(None),
    code_file: UploadFile = File(...),
    spec_file: UploadFile = File(...),
    process_file: UploadFile = File(...),
    result_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    cloud_token = _require_cloud_token(token)
    result = await upload_self_algorithm_submission(
        cloud_token,
        algorithm_type=algorithm_type,
        class_id=class_id,
        task_id=task_id,
        code_file=code_file,
        spec_file=spec_file,
        process_file=process_file,
        result_file=result_file,
    )
    return {"success": True, "data": result}


@router.get("/submissions")
async def get_submissions(
    algorithm_type: str | None = Query(None),
    task_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    cloud_token = _require_cloud_token(token)
    data = list_self_algorithm_submissions(
        cloud_token,
        algorithm_type=algorithm_type,
        task_id=task_id,
        page=page,
        page_size=page_size,
    )
    return {"success": True, "data": data}


@router.get("/submissions/{submission_id}/download/{kind}")
async def download_submission_file(
    submission_id: int,
    kind: str,
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    cloud_token = _require_cloud_token(token)
    content, headers, media_type = download_self_algorithm_submission_file(cloud_token, submission_id, kind)
    return Response(content=content, media_type=media_type, headers=headers)
