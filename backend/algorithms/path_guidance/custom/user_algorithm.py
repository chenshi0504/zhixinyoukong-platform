# 贪心路径选择算法
# 每步选择effort最小的邻居边

import traci

def greedy_reroute(veh_id):
    """
    贪心路径选择
    每步选择当前节点effort最小的邻居
    """
    current = traci.vehicle.getRoadID(veh_id)
    route = list(traci.vehicle.getRoute(veh_id))
    dest = route[-1]

    path = [current]
    visited = {current}
    max_steps = 50

    for _ in range(max_steps):
        if current == dest:
            break
        # 获取邻接边
        neighbors = []
        try:
            links = traci.lane.getLinks(f"{current}_0")
            for link in links:
                next_edge = link[0].rsplit('_', 1)[0]
                if not next_edge.startswith(':') and next_edge not in visited:
                    effort = traci.edge.getTraveltime(next_edge)
                    neighbors.append((next_edge, effort))
        except:
            break

        if not neighbors:
            break

        # 贪心选择effort最小的邻居
        next_edge, _ = min(neighbors, key=lambda x: x[1])
        path.append(next_edge)
        visited.add(next_edge)
        current = next_edge

    return path

# 在仿真循环中调用:
# for veh in traci.vehicle.getIDList():
#     if traci.vehicle.getTypeID(veh) == 'CAV':
#         new_path = greedy_reroute(veh)
#         traci.vehicle.setRoute(veh, new_path)