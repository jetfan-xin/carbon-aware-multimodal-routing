# -*- coding: utf-8 -*-
import numpy as np
import geatpy as ea
from input import get_distance, get_tparg, get_tsarg, get_timearg, get_carbon, get_input, get_time
from utils import transtr
from calculate import transport_cost, transit_cost, time_cost, carbon_cost


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


class MyProblem(ea.Problem):  # 继承Problem父类
    def __init__(self):
        name = 'Shortest_Path'  # 初始化name（函数名称，可以随意设置）
        M = 1  # 初始化M（目标维数）
        maxormins = [1]  # 初始化maxormins（目标最小最大化标记列表，1：最小化该目标；-1：最大化该目标）
        Dim = dim  # 初始化Dim（决策变量维数）
        varTypes = [1] * Dim  # 初始化varTypes（决策变量的类型，元素为0表示对应的变量是连续的；1表示是离散的）
        lb = [0] * Dim  # 决策变量下界
        ub = [dim-1] * Dim  # 决策变量上界
        lbin = [1] * Dim  # 决策变量下边界，1闭0开
        ubin = [1] * Dim  # 决策变量上边界
        # 调用父类构造方法完成实例化
        ea.Problem.__init__(self, name, M, maxormins, Dim, varTypes, lb, ub, lbin, ubin)
        self.coun = 0
        # 设置有向图中各条边的权重
        self.distance, self.city2id = get_distance()
        print("已获取各点间不同联通方式的距离")
        # 设置每一个结点下一步可达的结点（结点从1开始数，因此列表nodes的第0号元素设为空列表表示无意义）
        self.nodes = []
        for i in range(dim):
            self.nodes.append([])

        lll = list(self.distance.keys())
        for key in lll:
            st = transtr(key)
            self.nodes[st[0]].append(st[1])
        print("已设置每一个结点下一步可达的结点")

        self.qt = 100  # 自定义货运量

        self.args = dict()  # 参数字典
        self.args = get_tparg(self.args)
        self.args = get_tsarg(self.args)
        self.args = get_timearg(self.args)
        self.args = get_carbon(self.args)
        self.args = get_time(self.args)
        self.args = get_input(self.args)


    def decode(self, priority):
        # 将优先级编码的染色体解码得到一条从节点1到节点45的可行路径
        edges = []  # 存储边
        path = [0]  # 结点1是路径起点,1~15
        while path[-1] != int(dim/3)-1:  # 开始从起点走到终点
            currentNode = path[-1]  # 得到当前所在的结点编号(可走三条路径)
            nextNodes = [[],[], []]  # 获取下一步可达的结点编号组成的列表, 三种
            nextNodes[0] = self.nodes[currentNode]
            nextNodes[1] = self.nodes[currentNode+int(dim/3)]
            nextNodes[2] = self.nodes[currentNode+int(dim/3*2)]

            choosePos = [-1,-1,-1]
            chooseNode = [-1,-1,-1]
            for rr in range(3):
                if nextNodes[rr] !=[]:
                    choosePos[rr] = priority[np.array(nextNodes[rr])][np.argmax(priority[np.array(nextNodes[rr])])]  # 用于获取priority种对应区间最大的数
                    chooseNode[rr] = nextNodes[rr][np.argmax(priority[np.array(nextNodes[rr])])]  # 最大的priority中数对应的nextnodes上数（结点编号）

            ultipos = int(np.argmax(choosePos))
            ultinode = chooseNode[ultipos] - ultipos * int(dim / 3)  # 1~15

            edge = (path[-1] + ultipos * int(dim/3), chooseNode[ultipos])
            path.append(ultinode)
            edges.append(edge)
        return path, edges

    def aimFunc(self, pop):  # 目标函数
        pop.ObjV = np.zeros((pop.sizes, 1))  # 初始化ObjV
        pop.CV = np.zeros((pop.sizes, 1))  # 初始化CV
        for i in range(pop.sizes):
            # 遍历种群的每个个体，分别计算各个个体的目标函数值
            priority = pop.Phen[i, :]
            path, edges = self.decode(priority)
            # 将 path，edges 输入成本计算函数C1， C2， C3, C4
            # 将优先级编码的染色体解码得到访问路径及经过的边
            C1 = transport_cost(path, edges, self.qt, self.distance, self.args)
            C2, tur = transit_cost(edges, self.qt, self.args) # tur:总转运次数
            tim, tim_p, tim_t, C3 = time_cost(path, edges, self.qt, self.distance, self.args)
            zp, zt, C4 = carbon_cost(path, edges, self.qt, self.distance, self.args)
            pop.ObjV[i] = C4 + C1 + C2 + C3
            print("总成本: {:.2f} ￥, 时间:{:.2f}({:.2f}+{:.2f}) h, 碳排放量:{:.2f}({:.2f}+{:.2f}) kg\n"
                  "运输成本:{:.2f} ￥, 转运成本:{:.2f} ￥, 时间成本:{:.2f} ￥, 碳排成本:{:.2f} ￥\n"
                  .format(float(pop.ObjV[i]), float(tim), float(tim_p), float(tim_t), float(zp + zt), float(zp),
                          float(zt),
                          float(C1), float(C2), float(C3), float(C4)))