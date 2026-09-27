# -*- coding: utf-8 -*-
import pandas
from os.path import join
from utils import  city_index_map


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


"""默认参数"""
# 解析各城市间不同运输方式的距离
def get_distance():
    city2id = city_index_map()  # 字典{城市名：编号}
    print(city2id)
    a = pandas.read_excel(join(data_path,
                               "长三角周边各转运点之间的距离.xlsx"), sheet_name=0)
    distance = dict()
    for i in range(len(a)):
        if(a["公路距离"][i]!="#"):
            name = "("+str(city2id[a["起点"][i].replace(" ", "")])+", "+\
                   str(city2id[a["终点"][i].replace(" ", "")])+")"
            distance[name] = int(a["公路距离"][i])
        if(a["铁路距离"][i]!="#"):
            name = "("+str(city2id[a["起点"][i].replace(" ", "")]+int(dim/3))+", "+\
                   str(city2id[a["终点"][i].replace(" ", "")]+int(dim/3))+")"
            distance[name] = int(a["铁路距离"][i])
        if(a["水路距离"][i]!="#"):
            name = "("+str(city2id[a["起点"][i].replace(" ", "")]+int(dim/3*2))+", "+\
                   str(city2id[a["终点"][i].replace(" ", "")]+int(dim/3*2))+")"
            distance[name] = int(a["水路距离"][i])
    return distance, city2id

# 获取运输参数
def get_tparg(args):  # args是参数字典
    a = pandas.read_excel(join(arg_path, "不同运输方式的运输参数.xlsx"), sheet_name=0)
    args["V"] = (a["平均速度（km/h）"][0], a["平均速度（km/h）"][1], a["平均速度（km/h）"][2])
    args["CM_1"] = (a["运行基价1（￥/km*t）"][0], a["运行基价1（￥/km*t）"][1], a["运行基价1（￥/km*t）"][2])
    args["CM_2"] = (a["运行基价2（￥/km*t）"][0], a["运行基价2（￥/km*t）"][1], a["运行基价2（￥/km*t）"][2])
    args["CM_3"] = (a["运行基价3（￥/km*t）"][0], a["运行基价3（￥/km*t）"][1], a["运行基价3（￥/km*t）"][2])
    args["EM"] = (a["单位碳排放量（kg/km*t）"][0], a["单位碳排放量（kg/km*t）"][1], a["单位碳排放量（kg/km*t）"][2])
    return args

# 获取转运参数
def get_tsarg(args):
    '''
    按序排列： 公-铁, 公-水, 铁-水
    '''
    a = pandas.read_excel(join(arg_path, "不同运输方式转运相关数据.xlsx"), sheet_name=0)
    args["T2"] = (a["转运时间（h/1000t）"][0], a["转运时间（h/1000t）"][1], a["转运时间（h/1000t）"][2])
    args["MIU"] = (a["转运碳排放系数（kg/t）"][0], a["转运碳排放系数（kg/t）"][1], a["转运碳排放系数（kg/t）"][2])
    args["CN"] = (a["转运成本（￥/t）"][0], a["转运成本（￥/t）"][1], a["转运成本（￥/t）"][2])
    return args

# 获取时间成本
def get_timearg(args):
    a = pandas.read_excel(join(arg_path, "单位仓储和单位惩罚成本.xlsx"), sheet_name=0)
    args["P1"] = a["单位仓储费用（￥/h*t）"][0]
    args["P2"] = a["单位惩罚成本（￥/h*t）"][0]
    return args

# 获取碳政策
def get_carbon(args):
    a = pandas.read_excel(join(arg_path, "碳政策.xlsx"), sheet_name=0)
    args["Zk"] = (a["碳排放量（kg)"][0], a["碳排放量（kg)"][1], a["碳排放量（kg)"][2], a["碳排放量（kg)"][3])
    args["W"] = (a["碳税率（￥/kg）"][0], a["碳税率（￥/kg）"][1], a["碳税率（￥/kg）"][2], a["碳税率（￥/kg）"][3])
    return args



"""输入数据"""
# 获取时间段
def get_time(args):
    a = pandas.read_excel(join(arg_path, "时间段.xlsx"), sheet_name=0)
    args["Ta"] = a["最短时间（h）"][0]
    args["Tb"] = a["最长时间（h）"][0]
    return args

# 获取输入
def get_input(args):
    a = pandas.read_excel(join(arg_path, "输入 情景-运货量-概率.xlsx"), sheet_name=0)
    args["Q"] = (a["运货量（t）"][0], a["运货量（t）"][1], a["运货量（t）"][2])
    args["P"] = (a["概率"][0], a["概率"][1], a["概率"][2])
    return args