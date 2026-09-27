import folium
import pandas

tiles = 'https://wprd01.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=1&style=7'
data_path = r"D:\SODA\算例数据\参数\各转运点经纬度.xlsx"


def get_points():
    a = pandas.read_excel(data_path, sheet_name=0)
    leng = len(a)
    city_list = []
    city_num = 0
    for i in range(leng):
        city_list.append([a["城市名称"][i], a["纬度"][i], a["经度"][i]])
        city_num += 1
        folium.CircleMarker(
            location=[a["纬度"][i], a["经度"][i]],
            radius=6,
            tooltip=a["城市名称"][i],
            color="#3186cc",
            fill=True,
            fill_color="#3186cc",
        ).add_to(m)
    folium.Marker(
        location=[29.57, 106.55],
        # popup="重庆",
        tooltip="起点",
        icon=folium.Icon(color="green", icon="info-sign"),
    ).add_to(m)

    folium.Marker(
        location=[31.53, 122.12],
        # popup="重庆",
        tooltip="终点",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)
    return leng, city_list

"""========================================背景图========================================="""

m = folium.Map([30.71, 114.62],
               tiles=tiles,
               attr='高德-常规图',
               zoom_start=5.2,
               control_scale=True,
               )

leng, city_list = get_points()

folium.PolyLine(  # polyline方法为将坐标用虚线形式连接起来
    [city_list[i][1:] for i in range(leng)],  # 将坐标点连接起来
    weight=1.5,  # 线的大小为2
    color='blue',  # 线的颜色为蓝色
    opacity=1,  # 线的透明度
    dash_array='5'  # 虚线频率
).add_to(m)  # 将这条线添加到刚才的区域m内

# 组合
all_pair = []
for i in range(leng):
    j = 0
    while j < i:
        all_pair.append([city_list[i][1:], city_list[j][1:]])
        j += 1

for p in all_pair[:]:
    tooltip = None
    weight = 0.5
    op = 0.3
    # print(p)
    if p[1] == [29.57, 106.55] and p[0] == [31.53, 122.12]:
        tooltip = "灰色虚线：所有联通路径"
        weight = 1
        op = 0.8
    folium.PolyLine(  # polyline方法为将坐标用虚线形式连接起来
        p,  # 将坐标点连接起来
        weight=weight,  # 线的大小为2
        color='gray',  # 线的颜色为蓝色
        opacity=op,  # 线的透明度
        tooltip=tooltip,
        dash_array='5'  # 虚线频率
    ).add_to(m)  # 将这条线添加到刚才的区域m内

folium.PolyLine(  # polyline方法为将坐标用虚线形式连接起来
    [city_list[i][1:] for i in range(leng)],  # 将坐标点连接起来
    weight=1.5,  # 线的大小为2
    color='blue',  # 线的颜色为蓝色
    opacity=1,  # 线的透明度
    dash_array='5'  # 虚线频率
).add_to(m)  # 将这条线添加到刚才的区域m内

m.save(r"D:\SODA\算例数据\结果\background.html")



"""========================================结果图========================================="""

m = folium.Map([30.71, 114.62],
               tiles=tiles ,
               attr='高德-常规图',
               zoom_start=5.2,
               control_scale=True,
              )

# 组合
all_pair = []
for i in range(leng):
    j = 0
    while j < i:
        all_pair.append([city_list[i][1:], city_list[j][1:]])
        j += 1

for p in all_pair[:]:
    tooltip = None
    weight = 0.4
    op = 0.15
    # print(p)

    folium.PolyLine(  # polyline方法为将坐标用虚线形式连接起来
        p,  # 将坐标点连接起来
        weight=weight,  # 线的大小为2
        color='gray',  # 线的颜色为蓝色
        opacity=op,  # 线的透明度
        tooltip=tooltip,
        dash_array='5'  # 虚线频率
    ).add_to(m)  # 将这条线添加到刚才的区域m内

folium.PolyLine(  # polyline方法为将坐标用虚线形式连接起来
    [city_list[i][1:] for i in range(leng)],  # 将坐标点连接起来
    weight=1.5,  # 线的大小为2
    color='gray',  # 线的颜色为蓝色
    opacity=1,  # 线的透明度
    dash_array='5'  # 虚线频率
).add_to(m)  # 将这条线添加到刚才的区域m内

iframe = folium.IFrame("综合最优：水路<br>距离：1543km", height=60)
popup = folium.Popup(iframe, min_width=150, max_width=150)

folium.PolyLine(  # polyline方法为将坐标用实线形式连接起来
    [[29.57, 106.55], [29.61, 115.91]],  # 将坐标点连接起来
    weight=3,  # 线的大小为2
    color='blue',  # 线的颜色为蓝色
    opacity=0.7,  # 线的透明度
    tooltip="综合最优：水路<br>距离：1543km",
    popup=popup,
).add_to(m)  # 将这条线添加到刚才的区域m内

iframe = folium.IFrame("综合最优：铁路<br>距离：194km", height=60)
popup = folium.Popup(iframe, min_width=150, max_width=150)

folium.PolyLine(  # polyline方法为将坐标用实线形式连接起来
    [[29.61, 115.91], [30.52, 117.05]],  # 将坐标点连接起来
    weight=3,  # 线的大小为2
    color='red',  # 线的颜色为蓝色
    opacity=0.7,  # 线的透明度
    tooltip="综合最优：铁路<br>距离：194km",
    popup=popup,
).add_to(m)  # 将这条线添加到刚才的区域m内

iframe = folium.IFrame("综合最优 & 碳排最优：铁路<br>距离：487km", height=60)
popup = folium.Popup(iframe, min_width=250, max_width=250)

folium.PolyLine(  # polyline方法为将坐标用实线形式连接起来
    [[30.52, 117.05], [31.53, 122.12]],  # 将坐标点连接起来
    weight=3,  # 线的大小为2
    color='red',  # 线的颜色为蓝色
    opacity=0.7,  # 线的透明度
    tooltip="综合最优 & 碳排最优：铁路<br>距离：487km",
    popup=popup,
).add_to(m)  # 将这条线添加到刚才的区域m内

iframe = folium.IFrame("碳排最优：水路<br>距离：1707km", height=60)
popup = folium.Popup(iframe, min_width=150, max_width=150)

folium.PolyLine(  # polyline方法为将坐标用实线形式连接起来
    [[29.57, 106.55], [30.52, 117.05]],  # 将坐标点连接起来
    weight=5,  # 线的大小为2
    color="#00FFFF",  # 线的颜色为蓝色
    opacity=0.6,  # 线的透明度
    tooltip="碳排最优：水路<br>距离：1707km",
    popup=popup,
).add_to(m)  # 将这条线添加到刚才的区域m内

m.save(r"D:\SODA\算例数据\结果\best_route.html")