"""
A/B测试命令行工具
用于管理和查看A/B测试结果
"""

import sys
import os
from pathlib import Path

# 设置UTF-8编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.ab_testing import get_ab_test_manager, setup_default_ab_test


def cmd_init():
    """初始化默认A/B测试配置"""
    print("初始化A/B测试配置...")
    manager = setup_default_ab_test()
    print(f"✅ 已注册 {len(manager.configs)} 个测试配置:")
    for name, config in manager.configs.items():
        print(f"  - {name}: {config.description}")


def cmd_list_configs():
    """列出所有测试配置"""
    manager = get_ab_test_manager()

    if not manager.configs:
        print("暂无测试配置，请先运行 'init' 命令")
        return

    print(f"\n当前测试配置 (共 {len(manager.configs)} 个):\n")
    for name, config in manager.configs.items():
        print(f"【{name}】")
        print(f"  描述: {config.description}")
        print(f"  配置: {config.config}")
        print()


def cmd_assign_user(user_id: int, group: str = None):
    """分配用户到测试组"""
    manager = get_ab_test_manager()

    try:
        assigned_group = manager.assign_user_to_group(user_id, group)
        print(f"✅ 用户 {user_id} 已分配到组: {assigned_group}")
    except Exception as e:
        print(f"❌ 分配失败: {e}")


def cmd_list_users():
    """列出所有用户分组"""
    manager = get_ab_test_manager()

    if not manager.user_groups:
        print("暂无用户分组")
        return

    # 按组统计
    from collections import defaultdict
    group_users = defaultdict(list)
    for user_id, group in manager.user_groups.items():
        group_users[group].append(user_id)

    print(f"\n用户分组 (共 {len(manager.user_groups)} 个用户):\n")
    for group, users in group_users.items():
        print(f"【{group}】: {len(users)} 个用户")
        print(f"  用户ID: {', '.join(map(str, users[:10]))}")
        if len(users) > 10:
            print(f"  ... 还有 {len(users) - 10} 个用户")
        print()


def cmd_stats():
    """显示测试统计数据"""
    manager = get_ab_test_manager()
    stats = manager.get_statistics()

    print("\n" + "="*60)
    print("A/B测试统计数据")
    print("="*60)

    print(f"\n总查询数: {stats['total_queries']}")

    if not stats['groups']:
        print("\n暂无测试数据")
        return

    print("\n各组数据:\n")
    for group, data in stats['groups'].items():
        print(f"【{group}】")
        print(f"  查询数: {data['query_count']}")
        print(f"  平均响应时间: {data['avg_response_time']:.0f}ms")
        print(f"  点击率: {data['click_rate']:.2%}")
        print(f"  点赞率: {data['like_rate']:.2%}")
        print(f"  点踩率: {data['dislike_rate']:.2%}")
        if data['avg_first_click_rank'] > 0:
            print(f"  平均首次点击排名: {data['avg_first_click_rank']:.2f}")
        print()

    print("="*60 + "\n")


def cmd_report():
    """生成测试报告"""
    manager = get_ab_test_manager()
    report = manager.generate_report()

    # 保存到文件
    output_dir = project_root / '.RAG'
    output_path = output_dir / 'ab_test_report.md'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    print(f"\n报告已保存到: {output_path}")


def cmd_simulate(num_queries: int = 100):
    """模拟测试数据（用于演示）"""
    import random
    import time

    manager = get_ab_test_manager()

    # 确保有配置
    if not manager.configs:
        print("正在初始化配置...")
        setup_default_ab_test()

    print(f"开始模拟 {num_queries} 次查询...\n")

    test_queries = [
        "DQN算法原理",
        "如何配置SUMO",
        "实验失败原因",
        "信号优化参数",
        "路径规划算法",
        "数据采集使用",
        "CARLA环境配置",
        "训练不收敛",
    ]

    for i in range(num_queries):
        # 随机用户
        user_id = random.randint(1, 20)

        # 分配到组（如果还没分配）
        group = manager.assign_user_to_group(user_id)

        # 随机查询
        query = random.choice(test_queries)

        # 模拟响应时间（优化组更快）
        if group == 'optimized':
            response_time = random.uniform(200, 400)
        else:
            response_time = random.uniform(300, 600)

        # 模拟结果
        results = [{'content': f'结果{j}'} for j in range(5)]

        # 记录查询
        manager.record_query(user_id, query, results, response_time)

        # 模拟用户反馈（优化组点击率更高）
        if group == 'optimized':
            click_prob = 0.7
            like_prob = 0.3
        else:
            click_prob = 0.5
            like_prob = 0.2

        if random.random() < click_prob:
            rank = random.randint(1, 3)
            manager.record_user_feedback(user_id, query, 'click', rank)

        if random.random() < like_prob:
            manager.record_user_feedback(user_id, query, 'like')

        if i % 20 == 0:
            print(f"  已模拟 {i}/{num_queries} 次查询...")

    print(f"\n✅ 模拟完成！共 {num_queries} 次查询")
    print(f"   用户数: {len(manager.user_groups)}")
    print(f"   记录数: {len(manager.results)}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='A/B测试管理工具')
    subparsers = parser.add_subparsers(dest='command', help='命令')

    # init命令
    subparsers.add_parser('init', help='初始化默认A/B测试配置')

    # list-configs命令
    subparsers.add_parser('list-configs', help='列出所有测试配置')

    # assign命令
    assign_parser = subparsers.add_parser('assign', help='分配用户到测试组')
    assign_parser.add_argument('user_id', type=int, help='用户ID')
    assign_parser.add_argument('--group', type=str, help='指定组名（可选）')

    # list-users命令
    subparsers.add_parser('list-users', help='列出所有用户分组')

    # stats命令
    subparsers.add_parser('stats', help='显示测试统计数据')

    # report命令
    subparsers.add_parser('report', help='生成测试报告')

    # simulate命令
    simulate_parser = subparsers.add_parser('simulate', help='模拟测试数据')
    simulate_parser.add_argument('--num', type=int, default=100, help='模拟查询数量')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 执行命令
    if args.command == 'init':
        cmd_init()
    elif args.command == 'list-configs':
        cmd_list_configs()
    elif args.command == 'assign':
        cmd_assign_user(args.user_id, args.group)
    elif args.command == 'list-users':
        cmd_list_users()
    elif args.command == 'stats':
        cmd_stats()
    elif args.command == 'report':
        cmd_report()
    elif args.command == 'simulate':
        cmd_simulate(args.num)


if __name__ == '__main__':
    main()
