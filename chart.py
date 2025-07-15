import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import json
from itertools import cycle

# 顯示中文字
plt.rcParams['font.family'] = 'Arial Unicode Ms'  

# 讀取配置檔案
def load_config(config_path='config.json'):
    """讀取樓層配置檔案"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config['floors']
    except FileNotFoundError:
        # 如果沒有配置檔案，使用預設配置
        print("未找到配置檔案，使用預設配置")
        return {
            'floor1': [1, 2, 3, 4, 5],
            'floor2': [6, 7, 8, 9, 10]
        }

# 讀取樓層配置
floors_config = load_config()

def get_node_floor(node_id, floors_config):
    """獲取節點所在樓層"""
    node_int = int(node_id)
    for floor_name, nodes in floors_config.items():
        if node_int in nodes:
            return floor_name
    return None

def get_same_floor_neighbors(node_id, floors_config, df, antenna_type):
    """獲取同樓層鄰居（按接收率排序取前兩名）"""
    node_floor = get_node_floor(node_id, floors_config)
    if not node_floor:
        return []
    
    # 獲取同樓層所有節點（排除自己）
    same_floor_nodes = [str(n) for n in floors_config[node_floor] if str(n) != node_id]
    
    # 獲取與這些節點的連線數據
    connections = df[(df['節點ID'] == node_id) & 
                    (df['鄰居ID'].isin(same_floor_nodes)) & 
                    (df['天線類型'] == antenna_type)]
    
    # 按接收率排序並取前兩名
    top_connections = connections.nlargest(2, '平均接收率')
    return top_connections['鄰居ID'].tolist()

def get_cross_floor_neighbors(node_id, floors_config, df, antenna_type):
    """獲取跨樓層鄰居（按接收率排序取前兩名）"""
    node_floor = get_node_floor(node_id, floors_config)
    if not node_floor:
        return []
    
    # 獲取其他樓層所有節點
    other_floor_nodes = []
    for floor_name, nodes in floors_config.items():
        if floor_name != node_floor:
            other_floor_nodes.extend([str(n) for n in nodes])
    
    # 獲取與這些節點的連線數據
    connections = df[(df['節點ID'] == node_id) & 
                    (df['鄰居ID'].isin(other_floor_nodes)) & 
                    (df['天線類型'] == antenna_type)]
    
    # 按接收率排序並取前兩名
    top_connections = connections.nlargest(2, '平均接收率')
    return top_connections['鄰居ID'].tolist()

# 讀取資料
df = pd.read_csv('testData_all.csv')

# 把節點ID、鄰居ID當成字串處理，避免自動變數字
df['節點ID'] = df['節點ID'].astype(str)
df['鄰居ID'] = df['鄰居ID'].astype(str)
df['天線類型'] = df['天線類型'].astype(str)

# 所有節點、天線類型
nodes = sorted(df['節點ID'].unique(), key=lambda x: int(x))
antenna_types = sorted(df['天線類型'].unique())

# 定義天線類型的基本顏色
antenna_colors = {
    'PVC載版天線': '#D4A574',  # 橘棕色
    '外接交棒天線': '#9FD4E8'   # 淺藍色
}

def get_node_color(node_id, antenna_type):
    """獲取節點對應的顏色"""
    return antenna_colors[antenna_type]

# 計算 X 軸位置
x = np.arange(len(nodes))
bar_width = 0.35
group_gap = 0.1

fig, ax = plt.subplots(figsize=(16, 8))

# 為每個天線類型創建堆疊柱狀圖
for i, antenna in enumerate(antenna_types):
    x_pos = x + (i - 0.5) * (bar_width + group_gap/2)
    
    for j, node in enumerate(nodes):
        # 篩選當前節點、天線的資料
        group = df[(df['節點ID'] == node) & (df['天線類型'] == antenna)]
        
        if len(group) == 0:
            continue
            
        stack_bottom = 0
        
        # 按平均接收率降序排序，最高的在最下方
        group = group.sort_values('平均接收率', ascending=False)
        
        for _, row in group.iterrows():
            recv = row['平均接收率']
            neighbor = row['鄰居ID']
            
            # 判斷鄰居是否為同樓層
            node_floor = get_node_floor(node, floors_config)
            neighbor_floor = get_node_floor(neighbor, floors_config)
            is_same_floor = (node_floor == neighbor_floor)
            
            # 根據是否同樓層決定顏色和透明度
            base_color = get_node_color(node, antenna)
            if is_same_floor:
                # 同樓層：深色（較低透明度）
                color = base_color
                alpha = 0.9
            else:
                # 跨樓層：淺色（較高透明度）
                color = base_color
                alpha = 0.4
            
            # 畫堆疊區塊
            bar = ax.bar(x_pos[j], recv, width=bar_width, bottom=stack_bottom,
                        color=color, edgecolor='white', linewidth=0.5,
                        alpha=alpha)
            
            # 在堆疊區塊中央顯示鄰居ID（紅色）
            if recv > 0:  
                ax.text(x_pos[j], stack_bottom + recv * 0.7, neighbor,
                       ha='center', va='center', fontsize=9, color='red',
                       fontweight='bold')
            
            # 在堆疊區塊中央顯示平均接收率（黑色）
            if recv > 0:  
                ax.text(x_pos[j], stack_bottom + recv * 0.2, f'{recv:.1f}',
                       ha='center', va='center', fontsize=8, color='black')
            
            stack_bottom += recv

# 設定 X 軸
ax.set_xticks(x)
ax.set_xticklabels([f'{node:0>2}' for node in nodes])
ax.set_xlabel('節點ID', fontsize=12)
ax.set_ylabel('平均接收率（次/秒）', fontsize=12)
ax.set_title('每節點PVC載版天線與外接交棒天線平均接收率圖', fontsize=14, fontweight='bold')

# 設定 Y 軸
ax.set_ylim(0, max(df.groupby(['節點ID', '天線類型'])['平均接收率'].sum()) * 1.1)
ax.grid(True, axis='y', linestyle='--', alpha=0.3)

# 創建圖例
legend_elements = []
for antenna in antenna_types:
    color = antenna_colors[antenna]
    # 同樓層（深色）
    legend_elements.append(
        plt.Rectangle((0,0),1,1, facecolor=color, edgecolor='white', 
                     alpha=0.9, label=f'{antenna} (同樓層)')
    )
    # 跨樓層（淺色）
    legend_elements.append(
        plt.Rectangle((0,0),1,1, facecolor=color, edgecolor='white', 
                     alpha=0.4, label=f'{antenna} (跨樓層)')
    )

ax.legend(handles=legend_elements, loc='upper right', fontsize=9)

# 動態生成同樓層和跨樓層映射
def generate_mappings():
    same_floor_mapping = {}
    cross_floor_mapping = {}
    
    for node in nodes:
        # 獲取同樓層鄰居（每種天線類型分別計算）
        same_neighbors_pvc = get_same_floor_neighbors(node, floors_config, df, 'PVC載版天線')
        same_neighbors_ext = get_same_floor_neighbors(node, floors_config, df, '外接交棒天線')
        
        # 合併並去重
        same_neighbors = list(set(same_neighbors_pvc + same_neighbors_ext))
        same_floor_mapping[node] = same_neighbors
        
        # 獲取跨樓層鄰居（每種天線類型分別計算）
        cross_neighbors_pvc = get_cross_floor_neighbors(node, floors_config, df, 'PVC載版天線')
        cross_neighbors_ext = get_cross_floor_neighbors(node, floors_config, df, '外接交棒天線')
        
        # 合併並去重
        cross_neighbors = list(set(cross_neighbors_pvc + cross_neighbors_ext))
        cross_floor_mapping[node] = cross_neighbors
    
    return same_floor_mapping, cross_floor_mapping

same_floor_mapping, cross_floor_mapping = generate_mappings()

# 建立完整的跨樓層數據
cross_floor_data_complete = []
for antenna_type in antenna_types:
    for node_id, cross_neighbors in cross_floor_mapping.items():
        for neighbor_id in cross_neighbors:
            actual_data = df[(df['節點ID'] == node_id) & 
                           (df['鄰居ID'] == neighbor_id) & 
                           (df['天線類型'] == antenna_type)]
            
            if len(actual_data) > 0:
                recv_rate = actual_data.iloc[0]['平均接收率']
            else:
                recv_rate = 0.0
            
            cross_floor_data_complete.append({
                '節點ID': node_id,
                '鄰居ID': neighbor_id,
                '天線類型': antenna_type,
                '平均接收率': recv_rate
            })

cross_floor_df = pd.DataFrame(cross_floor_data_complete)

# 建立完整的同樓層數據
same_floor_data_complete = []
for antenna_type in antenna_types:
    for node_id, same_neighbors in same_floor_mapping.items():
        for neighbor_id in same_neighbors:
            actual_data = df[(df['節點ID'] == node_id) & 
                           (df['鄰居ID'] == neighbor_id) & 
                           (df['天線類型'] == antenna_type)]
            
            if len(actual_data) > 0:
                recv_rate = actual_data.iloc[0]['平均接收率']
            else:
                recv_rate = 0.0
            
            same_floor_data_complete.append({
                '節點ID': node_id,
                '鄰居ID': neighbor_id,
                '天線類型': antenna_type,
                '平均接收率': recv_rate
            })

same_floor_df = pd.DataFrame(same_floor_data_complete)

# 計算統計數據
pvc_cross_avg = cross_floor_df[cross_floor_df['天線類型'] == 'PVC載版天線']['平均接收率'].mean()
external_cross_avg = cross_floor_df[cross_floor_df['天線類型'] == '外接交棒天線']['平均接收率'].mean()

pvc_same_avg = same_floor_df[same_floor_df['天線類型'] == 'PVC載版天線']['平均接收率'].mean()
external_same_avg = same_floor_df[same_floor_df['天線類型'] == '外接交棒天線']['平均接收率'].mean()

total_pvc_avg = df[df['天線類型'] == 'PVC載版天線']['平均接收率'].mean()
total_external_avg = df[df['天線類型'] == '外接交棒天線']['平均接收率'].mean()

# 計算提升率
cross_improvement_rate = ((external_cross_avg - pvc_cross_avg) / pvc_cross_avg) * 100 if pvc_cross_avg > 0 else 0
same_improvement_rate = ((external_same_avg - pvc_same_avg) / pvc_same_avg) * 100 if pvc_same_avg > 0 else 0
total_improvement = ((total_external_avg - total_pvc_avg) / total_pvc_avg) * 100 if total_pvc_avg > 0 else 0

cross_improvement_diff = external_cross_avg - pvc_cross_avg
same_improvement_diff = external_same_avg - pvc_same_avg

plt.tight_layout()

# 添加統計信息
stats_cross_text = f"""跨樓層分析
PVC載版天線平均: {pvc_cross_avg:.2f} 次/秒
外接交棒天線平均: {external_cross_avg:.2f} 次/秒
提升幅度: {cross_improvement_diff:.2f} 次/秒
提升率: {cross_improvement_rate:.1f}%"""

ax.text(0.02, 0.98, stats_cross_text, transform=ax.transAxes, 
        fontsize=9, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

stats_same_text = f"""同樓層分析
PVC載版天線平均: {pvc_same_avg:.2f} 次/秒
外接交棒天線平均: {external_same_avg:.2f} 次/秒
提升幅度: {same_improvement_diff:.2f} 次/秒
提升率: {same_improvement_rate:.1f}%"""

ax.text(0.02, 0.86, stats_same_text, transform=ax.transAxes, 
        fontsize=9, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.9))

stats_total_text = f"""總體平均接收率
PVC載版天線平均: {total_pvc_avg:.2f} 次/秒
外接交棒天線平均: {total_external_avg:.2f} 次/秒
總體提升率: {total_improvement:.1f}%"""

ax.text(0.02, 0.74, stats_total_text, transform=ax.transAxes, 
        fontsize=9, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.9))

plt.show()

# 打印調試信息
print("樓層配置:", floors_config)
print("同樓層映射:", same_floor_mapping)
print("跨樓層映射:", cross_floor_mapping)