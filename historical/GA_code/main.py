# -*- coding: utf-8 -*-
import geatpy as ea
from ga import MyProblem

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


if __name__ == "__main__":
    # 实例化问题对象
    problem = MyProblem()
    # 构建算法
    algorithm = ea.soea_SEGA_templet(problem,
                                     ea.Population(Encoding='RI', NIND=100000),
                                     MAXGEN=1,  # 最大进化代数
                                     logTras=1
                                     )  # 表示每隔多少代记录一次日志信息
    # 求解
    res = ea.optimize(algorithm, verbose=True, drawing=1, outputMsg=False, drawLog=True, saveFlag=True,
                      dirName='result')
    print("city2id:", problem.city2id)
    print('最低成本为：%s' % (res['ObjV'][0][0]))
    print('最佳路线为：')
    best_journey, edges = problem.decode(res['Vars'][0])
    for i in range(len(best_journey)):
        if i == 0:
            print(int(best_journey[i]), end=' ')
            continue
        if edges[i-1][0] < int(dim/3):
            ty = "公"
        elif edges[i-1][0] < int(dim/3)*2:
            ty = "铁"
        else:
            ty = "水"
        print("—>{}—>".format(ty), end=' ')
        print(int(best_journey[i]), end=' ')