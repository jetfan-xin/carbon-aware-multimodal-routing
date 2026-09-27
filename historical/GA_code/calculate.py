import numpy as np
from utils import get_transit_num, get_trans_ty

data_path = r"D:\SODA\算例数据\距离"
arg_path = r"D:\SODA\算例数据\参数"
start_city = "重庆"
end_city = "上海"

N = 23  # 节点个数
dim = 23 * 3    # 节点个数*运输方式
jj_e1 = 500     # 运输基价按里程分段 临界值
jj_e2 = 1000
jj_size = 3     # 运输基价区间
ct_size = 4     # 碳排放量区间


"""计算成本"""
# 计算运输成本  return tim, cost
def transport_cost(path, edges, qt, distance, args):  # qt: 货运量
    cost = 0
    trans_ty = get_trans_ty(edges) # 记录所有路径的运输方式

    for i in range(len(path[:-1])):
        dis = distance[str(edges[i])]
        if dis < jj_e1:
            cm = args["CM_1"][trans_ty[i]]
        elif dis < jj_e2:
            cm = args["CM_2"][trans_ty[i]]
        else:
            cm = args["CM_3"][trans_ty[i]]
        cost += qt * dis * cm
    return cost

# 计算转运成本 return tim, cost
def transit_cost(edges, qt, args):  # qt: 货运量
    transit_num = get_transit_num(edges) # 记录各种转运方式进行次数
    for i in range(len(edges[:-1])):
        if (edges[i][0] < N <= edges[i + 1][0] < 2 * N)\
                or (edges[i + 1][0] < N <= edges[i][0] < 2 * N):
            transit_num[0] += 1
        elif (edges[i][0] < N and 2 * N <= edges[i + 1][0] < 3 * N) \
                or (edges[i + 1][0] < N and 2 * N <= edges[i][0] < 3 * N):
            transit_num[1] += 1
        elif (N <= edges[i][0] < 2 * N <= edges[i + 1][0] < 3 * N) \
                or (N <= edges[i + 1][0] < 2 * N <= edges[i][0] < 3 * N):
            transit_num[2] += 1
    return qt * (transit_num[0] * args["CN"][0] + transit_num[1] * args["CN"][1] + transit_num[2] * args["CN"][2]), np.sum(np.array(transit_num))

# 计算时间成本  return tim, cost
def time_cost(path, edges, qt, distance, args):
    trans_ty = get_trans_ty(edges)  # 记录所有路径的运输方式
    transit_num = get_transit_num(edges)  # 记录各种转运方式进行次数
    tim_t = qt * 0.001 * (transit_num[0] * args["T2"][0] + transit_num[1] * args["T2"][1] + transit_num[2] * args["T2"][2])
    tim_p = 0
    for i in range(len(path[:-1])):  # 获取每条路的运输时间
        dis = distance[str(edges[i])]
        sp = args["V"][trans_ty[i]]
        tim_p += dis / sp
    cost = qt * (args["P1"] * max(args["Ta"]-(tim_t + tim_p), 0) + args["P2"] * max(tim_t + tim_p - args["Tb"], 0))
    return tim_t + tim_p, tim_p, tim_t, cost

# 计算碳排成本  return zp(kg), zt(kg), cost
def carbon_cost(path, edges, qt, distance, args):
    zp = 0
    zt = 0
    trans_ty = get_trans_ty(edges)  # 记录所有路径的运输方式
    transit_num = get_transit_num(edges)  # 记录各种转运方式进行次数
    zt += qt * (transit_num[0] * args["MIU"][0] + transit_num[1] * args["MIU"][1] + transit_num[2] * args["MIU"][2])
    for i in range(len(path[:-1])):  # 获取每条路的运输碳排放量
        dis = distance[str(edges[i])]
        zp += qt * dis * args["EM"][trans_ty[i]]

    Z = zt + zp
    Yk = []# 记录速算扣除数
    if Z < args["Zk"][1]:
        Yk.append(0)
        cost = args["W"][0] * Z - Yk[-1]
    elif Z < args["Zk"][2]:
        Yk.append(args["Zk"][1] * (args["W"][1] - args["W"][0]) + Yk[-1])
        cost = args["W"][1] * Z - Yk[-1]
    elif Z < args["Zk"][3]:
        Yk.append(args["Zk"][2] * (args["W"][2] - args["W"][1]) + Yk[-1])
        cost = args["W"][2] * Z - Yk[-1]
    else:
        Yk.append(args["Zk"][3] * (args["W"][3] - args["W"][2]) + Yk[-1])
        cost = args["W"][3] * Z - Yk[-1]
    return zp, zt, cost
