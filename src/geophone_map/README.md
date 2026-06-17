# geophone_map

核心代码模块。

- `sac_coordinates.py`: SAC 头段读取、空经纬度过滤、阵列行列号解析、点集合生成。
- `georeference.py`: 将阵列索引按原点经纬度、间距和方位角近似投影到 WGS84 经纬度。
- `plotting.py`: 输出坐标 CSV、静态 PNG 图和 Folium/OpenStreetMap HTML 地图。

