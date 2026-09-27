import re
import pandas
from os.path import join

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

"""工具函数"""
# 获取各种转运方式进行次数
def get_transit_num(edges):
    transit_num = [0, 0, 0]
    for i in range(len(edges[:-1])):
        if (edges[i][0] < N <= edges[i + 1][0] < 2 * N) \
                or (edges[i + 1][0] < N <= edges[i][0] < 2 * N):
            transit_num[0] += 1
        elif (edges[i][0] < N and 2 * N <= edges[i + 1][0] < 3 * N) \
                or (edges[i + 1][0] < N and 2 * N <= edges[i][0] < 3 * N):
            transit_num[1] += 1
        elif (N <= edges[i][0] < 2 * N <= edges[i + 1][0] < 3 * N) \
                or (N <= edges[i + 1][0] < 2 * N <= edges[i][0] < 3 * N):
            transit_num[2] += 1
    return transit_num

# 获取所有路径的运输方式
def get_trans_ty(edges):
    trans_ty = []  # 记录所有路径的运输方式
    for edge in edges:  # 获取运输方式
        if edge[0] < N:
            trans_ty.append(0)
        elif edge[0] < N * 2:
            trans_ty.append(1)
        else:
            trans_ty.append(2)
    return trans_ty

# 构建城市-编号字典
def city_index_map():
    a = pandas.read_excel(join(data_path,
                               "长三角周边各转运点之间的距离.xlsx"), sheet_name=0)
    # 获取城市集合list
    cities = []
    for city in a["起点"]:
        cities.append(city.replace(" ", ""))
    for city in a["终点"]:
        cities.append(city.replace(" ", ""))
    cities = list(set(cities))
    city_num = len(cities)
    print()
    dim = len(cities)*3

    city2id = dict()
    idx = 1
    for city in cities:
        if city == start_city:
            city2id[start_city] = 0
        elif city == end_city:
            city2id[end_city] = city_num - 1
        else:
            city2id[city] = idx
            idx += 1
    return city2id

# 转换起始城市、终止城市数据类型
def transtr(s):
    st = re.sub('[/(/)]','',s).split(",")
    return [int(ii) for ii in st]