import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 顯示中文字
plt.rcParams['font.family'] = 'Arial Unicode Ms'  

# 讀取資料
df = pd.read_csv('testData_all.csv')

# 把節點ID、鄰居ID當成字串處理，避免自動變數字
df['節點ID'] = df['節點ID'].astype(str)
df['鄰居ID'] = df['鄰居ID'].astype(str)
df['天線類型'] = df['天線類型'].astype(str)

# 所有節點、天線類型
nodes = sorted(df['節點ID'].unique(), key=lambda x: int(x))  # 按數字順序排序
antenna_types = sorted(df['天線類型'].unique())

# 定義天線類型的顏色
antenna_colors = {
    'PVC窄版天線': '#D4A574',  # 橘棕色
    '外接交棒天線': '#9FD4E8'   # 淺藍色
}

# 計算 X 軸位置
x = np.arange(len(nodes))
bar_width = 0.35  # 增加柱子寬度
group_gap = 0.1   # 組間距離

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
            
            # 使用天線類型顏色，但稍微調整透明度來區分不同鄰居
            color = antenna_colors[antenna]
            
            # 畫堆疊區塊
            bar = ax.bar(x_pos[j], recv, width=bar_width, bottom=stack_bottom,
                        color=color, edgecolor='white', linewidth=0.5,
                        alpha=0.8)
            
            # 在堆疊區塊中央顯示鄰居ID（紅色）
            if recv > 0:  
                ax.text(x_pos[j], stack_bottom + recv * 0.7, neighbor,
                       ha='center', va='center', fontsize=12, color='red',
                       fontweight='bold')
            
            # 在堆疊區塊中央顯示平均接收率（黑色）
            if recv > 0:  
                ax.text(x_pos[j], stack_bottom + recv * 0.2, f'{recv:.1f}',
                       ha='center', va='center', fontsize=12, color='black')
            
            stack_bottom += recv

# 設定 X 軸
ax.set_xticks(x)
ax.set_xticklabels([f'{node:0>2}' for node in nodes])  # 節點ID補零
ax.set_xlabel('節點ID', fontsize=16)
ax.set_ylabel('平均接收率（次/秒）', fontsize=16)
ax.set_title('每節點PVC窄版天線與外接交棒天線平均接收率圖', fontsize=16, fontweight='bold')

# 設定 Y 軸
ax.set_ylim(0, max(df.groupby(['節點ID', '天線類型'])['平均接收率'].sum()) * 1.1)
ax.grid(True, axis='y', linestyle='--', alpha=0.3)

# 添加圖例
legend_elements = [plt.Rectangle((0,0),1,1, facecolor=antenna_colors[antenna], 
                                edgecolor='white', alpha=0.8, label=antenna)
                  for antenna in antenna_types]
ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

# 根據相對位置圖定義每個節點的跨樓層鄰居
cross_floor_mapping = {
    '1': ['6'],          
    '2': ['7'],           
    '3': ['10'],          
    '4': ['8'],           
    '5': ['9'],           
    '6': ['1'],           
    '7': ['2'],           
    '8': ['4'],          
    '9': ['5'],          
    '10': ['3']           
}

# 根據相對位置圖定義每個節點的同樓層鄰居
same_floor_mapping = {
    '1': ['4', '2'],      
    '2': ['1'],   
    '3': ['5'],        
    '4': ['1'],  
    '5': ['3', '8'],         
    '6': ['7'],           
    '7': ['6'],          
    '8': ['5', '9'],      
    '9': ['8', '10'],     
    '10': ['9']           
}

# 建立完整的跨樓層數據，缺失的補0
cross_floor_data_complete = []

for antenna_type in antenna_types:
    for node_id, cross_neighbors in cross_floor_mapping.items():
        for neighbor_id in cross_neighbors:
            # 查找實際數據
            actual_data = df[(df['節點ID'] == node_id) & 
                           (df['鄰居ID'] == neighbor_id) & 
                           (df['天線類型'] == antenna_type)]
            
            if len(actual_data) > 0:
                # 有實際數據
                recv_rate = actual_data.iloc[0]['平均接收率']
            else:
                # 沒有數據，補0
                recv_rate = 0.0
            
            cross_floor_data_complete.append({
                '節點ID': node_id,
                '鄰居ID': neighbor_id,
                '天線類型': antenna_type,
                '平均接收率': recv_rate
            })

# 轉換為DataFrame
cross_floor_df = pd.DataFrame(cross_floor_data_complete)

# 計算每種天線類型的跨樓層平均接收率（包含補0的數據）
pvc_cross_avg = cross_floor_df[cross_floor_df['天線類型'] == 'PVC窄版天線']['平均接收率'].mean()
external_cross_avg = cross_floor_df[cross_floor_df['天線類型'] == '外接交棒天線']['平均接收率'].mean()

# 計算跨樓層提升率和提升幅度
if pvc_cross_avg > 0:
    cross_improvement_rate = ((external_cross_avg - pvc_cross_avg) / pvc_cross_avg) * 100
    cross_improvement_diff = external_cross_avg - pvc_cross_avg
else:
    cross_improvement_rate = float('inf') if external_cross_avg > 0 else 0
    cross_improvement_diff = external_cross_avg - pvc_cross_avg

# 建立完整的同樓層數據，缺失的補0
same_floor_data_complete = []

for antenna_type in antenna_types:
    for node_id, same_neighbors in same_floor_mapping.items():
        for neighbor_id in same_neighbors:
            # 查找實際數據
            actual_data = df[(df['節點ID'] == node_id) & 
                           (df['鄰居ID'] == neighbor_id) & 
                           (df['天線類型'] == antenna_type)]
            
            if len(actual_data) > 0:
                # 有實際數據
                recv_rate = actual_data.iloc[0]['平均接收率']
            else:
                # 沒有數據，補0
                recv_rate = 0.0
            
            same_floor_data_complete.append({
                '節點ID': node_id,
                '鄰居ID': neighbor_id,
                '天線類型': antenna_type,
                '平均接收率': recv_rate
            })

# 轉換為DataFrame
same_floor_df = pd.DataFrame(same_floor_data_complete)

# 計算每種天線類型的同樓層平均接收率（包含補0的數據）
pvc_same_avg = same_floor_df[same_floor_df['天線類型'] == 'PVC窄版天線']['平均接收率'].mean()
external_same_avg = same_floor_df[same_floor_df['天線類型'] == '外接交棒天線']['平均接收率'].mean()

# 計算同樓層提升率和提升幅度
if pvc_same_avg > 0:
    same_improvement_rate = ((external_same_avg - pvc_same_avg) / pvc_same_avg) * 100
    same_improvement_diff = external_same_avg - pvc_same_avg
else:
    same_improvement_rate = float('inf') if external_same_avg > 0 else 0
    same_improvement_diff = external_same_avg - pvc_same_avg

# 計算總體平均接收率
total_pvc_avg = df[df['天線類型'] == 'PVC窄版天線']['平均接收率'].mean()
total_external_avg = df[df['天線類型'] == '外接交棒天線']['平均接收率'].mean()
total_improvement = ((total_external_avg - total_pvc_avg) / total_pvc_avg) * 100 if total_pvc_avg > 0 else 0

# 統計有多少跨樓層連接有實際數據
pvc_cross_non_zero = len(cross_floor_df[(cross_floor_df['天線類型'] == 'PVC窄版天線') & (cross_floor_df['平均接收率'] > 0)])
external_cross_non_zero = len(cross_floor_df[(cross_floor_df['天線類型'] == '外接交棒天線') & (cross_floor_df['平均接收率'] > 0)])

# 統計有多少同樓層連接有實際數據
pvc_same_non_zero = len(same_floor_df[(same_floor_df['天線類型'] == 'PVC窄版天線') & (same_floor_df['平均接收率'] > 0)])
external_same_non_zero = len(same_floor_df[(same_floor_df['天線類型'] == '外接交棒天線') & (same_floor_df['平均接收率'] > 0)])

# 調整佈局
plt.tight_layout()

# 添加跨樓層分析說明文字
stats_cross_text = f"""跨樓層分析
PVC載版天線平均: {pvc_cross_avg:.2f} 次/秒
外接交棒天線平均: {external_cross_avg:.2f} 次/秒
提升幅度: {cross_improvement_diff:.2f} 次/秒
提升率: {cross_improvement_rate:.1f}%"""

ax.text(0.02, 0.98, stats_cross_text, transform=ax.transAxes, 
        fontsize=11, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

# 添加同樓層分析說明文字
stats_same_text = f"""同樓層分析
PVC載版天線平均: {pvc_same_avg:.2f} 次/秒
外接交棒天線平均: {external_same_avg:.2f} 次/秒
提升幅度: {same_improvement_diff:.2f} 次/秒
提升率: {same_improvement_rate:.1f}%"""

ax.text(0.02, 0.84, stats_same_text, transform=ax.transAxes, 
        fontsize=11, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.9))

stats_total_text = f"""總體平均接收率
PVC載版天線平均: {total_pvc_avg:.2f} 次/秒
外接交棒天線平均: {total_external_avg:.2f} 次/秒
總體提升率: {total_improvement:.1f}%"""

ax.text(0.02, 0.70, stats_total_text, transform=ax.transAxes, 
        fontsize=11, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.9))



plt.show()