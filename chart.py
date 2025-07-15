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

def get_same_floor_neighbors(node_id, floors_config, df, test_group):
    """獲取同樓層鄰居（按接收率排序取前兩名）"""
    node_floor = get_node_floor(node_id, floors_config)
    if not node_floor:
        return []
    
    # 獲取同樓層所有節點（排除自己）
    same_floor_nodes = [str(n) for n in floors_config[node_floor] if str(n) != node_id]
    
    # 獲取與這些節點的連線數據
    connections = df[(df['節點ID'] == node_id) & 
                    (df['鄰居ID'].isin(same_floor_nodes)) & 
                    (df['測試組別'] == test_group)]
    
    # 按接收率排序並取前兩名
    top_connections = connections.nlargest(2, '平均接收率')
    return top_connections['鄰居ID'].tolist()

def get_cross_floor_neighbors(node_id, floors_config, df, test_group):
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
                    (df['測試組別'] == test_group)]
    
    # 按接收率排序並取前兩名
    top_connections = connections.nlargest(2, '平均接收率')
    return top_connections['鄰居ID'].tolist()

# 讀取資料
df = pd.read_csv('testData_all.csv')

# 把相關欄位當成字串處理
df['節點ID'] = df['節點ID'].astype(str)
df['鄰居ID'] = df['鄰居ID'].astype(str)
df['測試組別'] = df['測試組別'].astype(str)

# 所有節點、測試組別
nodes = sorted(df['節點ID'].unique(), key=lambda x: int(x))
test_groups = sorted(df['測試組別'].unique())

# 定義測試組別的顏色（可以根據需要調整）
# 使用色彩循環來支援多組測試
color_palette = [
    '#D4A574',  # 橘棕色
    '#9FD4E8',  # 淺藍色
    '#E8A5A5',  # 淺紅色
    '#A5E8A5',  # 淺綠色
    '#E8C5E8',  # 淺紫色
    '#E8E8A5',  # 淺黃色
    '#C5E8E8',  # 淺青色
    '#E8C5A5',  # 淺棕色
]

# 為每個測試組別分配顏色
group_colors = {}
for i, group in enumerate(test_groups):
    group_colors[group] = color_palette[i % len(color_palette)]

def get_node_color(node_id, test_group):
    """獲取節點對應的顏色"""
    return group_colors[test_group]

# 計算 X 軸位置
x = np.arange(len(nodes))
bar_width = 0.35 if len(test_groups) <= 2 else 0.3
group_gap = 0.1

fig, ax = plt.subplots(figsize=(16, 8))

# 為每個測試組別創建堆疊柱狀圖
for i, test_group in enumerate(test_groups):
    # 計算每個測試組別的 X 軸位置
    x_offset = (i - (len(test_groups) - 1) / 2) * (bar_width + group_gap / len(test_groups))
    x_pos = x + x_offset
    
    for j, node in enumerate(nodes):
        # 篩選當前節點、測試組別的資料
        group = df[(df['節點ID'] == node) & (df['測試組別'] == test_group)]
        
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
            base_color = get_node_color(node, test_group)
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
ax.set_title('各節點不同測試組別的平均接收率比較圖', fontsize=14, fontweight='bold')

# 設定 Y 軸
ax.set_ylim(0, max(df.groupby(['節點ID', '測試組別'])['平均接收率'].sum()) * 1.1)
ax.grid(True, axis='y', linestyle='--', alpha=0.3)

# 創建圖例
legend_elements = []
for test_group in test_groups:
    color = group_colors[test_group]
    # 同樓層（深色）
    legend_elements.append(
        plt.Rectangle((0,0),1,1, facecolor=color, edgecolor='white', 
                     alpha=0.9, label=f'{test_group} (同樓層)')
    )
    # 跨樓層（淺色）
    legend_elements.append(
        plt.Rectangle((0,0),1,1, facecolor=color, edgecolor='white', 
                     alpha=0.4, label=f'{test_group} (跨樓層)')
    )

ax.legend(handles=legend_elements, loc='upper right', fontsize=9)

# 動態生成同樓層和跨樓層映射
def generate_mappings():
    same_floor_mapping = {}
    cross_floor_mapping = {}
    
    for node in nodes:
        # 獲取同樓層鄰居（每種測試組別分別計算）
        same_neighbors_all = []
        cross_neighbors_all = []
        
        for test_group in test_groups:
            same_neighbors = get_same_floor_neighbors(node, floors_config, df, test_group)
            cross_neighbors = get_cross_floor_neighbors(node, floors_config, df, test_group)
            
            same_neighbors_all.extend(same_neighbors)
            cross_neighbors_all.extend(cross_neighbors)
        
        # 合併並去重
        same_floor_mapping[node] = list(set(same_neighbors_all))
        cross_floor_mapping[node] = list(set(cross_neighbors_all))
    
    return same_floor_mapping, cross_floor_mapping

same_floor_mapping, cross_floor_mapping = generate_mappings()

# 計算各測試組別的統計數據
stats_text_list = []
y_position = 0.98

for i, test_group in enumerate(test_groups):
    # 建立當前測試組別的跨樓層和同樓層數據
    cross_floor_data = []
    same_floor_data = []
    
    for node_id, cross_neighbors in cross_floor_mapping.items():
        for neighbor_id in cross_neighbors:
            actual_data = df[(df['節點ID'] == node_id) & 
                           (df['鄰居ID'] == neighbor_id) & 
                           (df['測試組別'] == test_group)]
            
            if len(actual_data) > 0:
                cross_floor_data.append(actual_data.iloc[0]['平均接收率'])
    
    for node_id, same_neighbors in same_floor_mapping.items():
        for neighbor_id in same_neighbors:
            actual_data = df[(df['節點ID'] == node_id) & 
                           (df['鄰居ID'] == neighbor_id) & 
                           (df['測試組別'] == test_group)]
            
            if len(actual_data) > 0:
                same_floor_data.append(actual_data.iloc[0]['平均接收率'])
    
    # 計算統計值
    cross_avg = np.mean(cross_floor_data) if cross_floor_data else 0
    same_avg = np.mean(same_floor_data) if same_floor_data else 0
    total_avg = df[df['測試組別'] == test_group]['平均接收率'].mean()
    
    # 選擇統計框的顏色
    box_colors = ['lightyellow', 'lightblue', 'lightgreen', 'lightpink', 'lightgray']
    box_color = box_colors[i % len(box_colors)]
    
    stats_text = f"""{test_group} 統計
同樓層平均: {same_avg:.2f} 次/秒
跨樓層平均: {cross_avg:.2f} 次/秒
總體平均: {total_avg:.2f} 次/秒"""
    
    ax.text(0.02, y_position - i * 0.12, stats_text, transform=ax.transAxes, 
            fontsize=9, verticalalignment='top', 
            bbox=dict(boxstyle='round', facecolor=box_color, alpha=0.9))

# 如果有兩個以上的測試組別，計算改善情況
if len(test_groups) >= 2:
    # 以第一個測試組別為基準，計算其他組別的改善
    base_group = test_groups[0]
    base_avg = df[df['測試組別'] == base_group]['平均接收率'].mean()
    
    improvement_text = f"相對於 {base_group} 的改善:\n"
    
    for test_group in test_groups[1:]:
        current_avg = df[df['測試組別'] == test_group]['平均接收率'].mean()
        improvement = ((current_avg - base_avg) / base_avg) * 100 if base_avg > 0 else 0
        improvement_diff = current_avg - base_avg
        
        improvement_text += f"{test_group}: {improvement_diff:+.2f} 次/秒 ({improvement:+.1f}%)\n"
    
    ax.text(0.02, y_position - (i+1) * 0.12, improvement_text, transform=ax.transAxes, 
            fontsize=9, verticalalignment='top', 
            bbox=dict(boxstyle='round', facecolor='lightcyan', alpha=0.9))

plt.tight_layout()
plt.show()

# 打印調試信息
print("樓層配置:", floors_config)
print("測試組別:", test_groups)
print("同樓層映射:", same_floor_mapping)
print("跨樓層映射:", cross_floor_mapping)