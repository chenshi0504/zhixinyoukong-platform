"""
实验教材知识库索引构建工具
用于建立教材内容的向量索引，支持语义检索
"""
import os
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "docs" / "教材"
INDEX_FILE = PROJECT_ROOT / "backend" / "data" / "knowledge_index.json"


def read_markdown_file(filepath: str) -> Dict[str, Any]:
    """读取markdown文件并提取章节"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取标题和内容
    sections = []
    current_section = {"title": "", "content": "", "level": 0}

    for line in content.split('\n'):
        if line.startswith('#'):
            # 保存上一个章节
            if current_section["content"].strip():
                sections.append(current_section.copy())

            # 开始新章节
            level = len(line.split()[0])
            title = line.lstrip('#').strip()
            current_section = {
                "title": title,
                "content": "",
                "level": level
            }
        else:
            current_section["content"] += line + "\n"

    # 保存最后一个章节
    if current_section["content"].strip():
        sections.append(current_section)

    return {
        "file": os.path.basename(filepath),
        "path": filepath,
        "sections": sections
    }


def build_keyword_index(docs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """构建关键词索引"""
    index = {}

    # 定义关键词映射
    keywords = {
        "车路协同": ["车路协同", "V2X", "车联网", "智能网联"],
        "数据采集": ["数据采集", "YOLO", "目标检测", "点云", "传感器"],
        "数据融合": ["数据融合", "贝叶斯", "卡尔曼", "融合算法"],
        "交通流重构": ["交通流重构", "DTALite", "OD矩阵", "交通分配"],
        "交通流预测": ["交通流预测", "LSTM", "GRU", "Transformer", "时间序列"],
        "信号优化": ["信号优化", "信号灯", "配时", "绿波", "SUMO"],
        "路径诱导": ["路径诱导", "路径规划", "导航", "最短路径"],
        "车速控制": ["车速控制", "速度控制", "ACC", "CACC", "跟驰"],
        "协同控制": ["协同控制", "三层级", "多层级", "优化控制"],
        "CARLA": ["CARLA", "仿真", "虚实结合", "场景构建"],
        "SUMO": ["SUMO", "交通仿真", "微观仿真"],
    }

    for doc in docs:
        for section in doc["sections"]:
            text = (section["title"] + " " + section["content"]).lower()

            for category, terms in keywords.items():
                for term in terms:
                    if term.lower() in text:
                        if category not in index:
                            index[category] = []

                        # 计算相关度分数（简单的词频统计）
                        score = text.count(term.lower())

                        index[category].append({
                            "file": doc["file"],
                            "section": section["title"],
                            "content": section["content"][:500],  # 限制长度
                            "score": score
                        })
                        break  # 每个section只添加一次

    # 按分数排序
    for category in index:
        index[category] = sorted(index[category], key=lambda x: x["score"], reverse=True)

    return index


def build_index():
    """构建知识库索引"""
    print("开始构建知识库索引...")

    if not DOCS_DIR.exists():
        print(f"教材目录不存在: {DOCS_DIR}")
        return

    # 读取所有markdown文件
    docs = []
    for md_file in DOCS_DIR.glob("*.md"):
        print(f"处理文件: {md_file.name}")
        try:
            doc = read_markdown_file(str(md_file))
            docs.append(doc)
        except Exception as e:
            print(f"处理文件失败 {md_file}: {e}")

    # 构建索引
    print(f"共处理 {len(docs)} 个文件")
    index = build_keyword_index(docs)

    # 保存索引
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"索引已保存到: {INDEX_FILE}")
    print(f"索引包含 {len(index)} 个类别")
    for category, items in index.items():
        print(f"  - {category}: {len(items)} 条记录")


if __name__ == "__main__":
    build_index()
