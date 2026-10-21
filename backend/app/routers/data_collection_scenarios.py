"""内置城市交通视频场景目录。

场景视频仍由 data_collection 路由负责检测，这个路由只负责目录发现和
安全地返回内置视频文件名，避免改动已编译的检测路由。
"""
import json
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse


router = APIRouter(prefix="/api/collection", tags=["数据采集场景"])

_ALGO_DIR = Path(__file__).resolve().parents[2] / "algorithms" / "data_collection"
_CATALOG_PATH = _ALGO_DIR / "scenario_catalog.json"
_ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv"}


def _load_catalog():
    try:
        with _CATALOG_PATH.open("r", encoding="utf-8") as f:
            catalog = json.load(f)
        scenarios = catalog.get("scenarios", [])
    except (OSError, ValueError):
        scenarios = []

    result = []
    for scenario in scenarios:
        filename = os.path.basename(str(scenario.get("filename", "")))
        path = _ALGO_DIR / filename
        if not filename or Path(filename).suffix.lower() not in _ALLOWED_VIDEO_SUFFIXES:
            continue
        if not path.is_file():
            continue
        item = dict(scenario)
        item["filename"] = filename
        item["sizeBytes"] = path.stat().st_size
        item["sizeMB"] = f"{path.stat().st_size / 1024 / 1024:.2f} MB"
        result.append(item)
    return result


@router.get("/scenarios")
async def list_collection_scenarios():
    scenarios = _load_catalog()
    return {"success": True, "scenarios": scenarios, "count": len(scenarios)}


@router.get("/scenarios/{scenario_id}")
async def get_collection_scenario(scenario_id: str):
    scenario = next((s for s in _load_catalog() if s.get("id") == scenario_id), None)
    if scenario is None:
        return JSONResponse({"success": False, "message": "场景不存在"}, status_code=404)
    return {"success": True, "scenario": scenario}


@router.get("/scenarios/{scenario_id}/video")
async def serve_collection_scenario_video(scenario_id: str):
    scenario = next((s for s in _load_catalog() if s.get("id") == scenario_id), None)
    if scenario is None:
        return JSONResponse({"success": False, "message": "场景不存在"}, status_code=404)
    video_path = _ALGO_DIR / scenario["filename"]
    if not video_path.is_file():
        return JSONResponse({"success": False, "message": "场景视频文件不存在"}, status_code=404)
    return FileResponse(video_path, media_type="video/mp4")
