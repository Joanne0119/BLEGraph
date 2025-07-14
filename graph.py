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

# 定義天線類型的顏色（參考您的圖片）
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
                       ha='center', va='center', fontsize=9, color='red',
                       fontweight='bold')
            
            # 在堆疊區塊中央顯示平均接收率（黑色）
            if recv > 0:  
                ax.text(x_pos[j], stack_bottom + recv * 0.2, f'{recv:.1f}',
                       ha='center', va='center', fontsize=8, color='black')
            
            stack_bottom += recv

# 設定 X 軸
ax.set_xticks(x)
ax.set_xticklabels([f'{node:0>2}' for node in nodes])  # 節點ID補零
ax.set_xlabel('節點ID', fontsize=12)
ax.set_ylabel('平均接收率（次/秒）', fontsize=12)
ax.set_title('每節點分天線堆疊平均接收率圖', fontsize=14, fontweight='bold')

# 設定 Y 軸
ax.set_ylim(0, max(df.groupby(['節點ID', '天線類型'])['平均接收率'].sum()) * 1.1)
ax.grid(True, axis='y', linestyle='--', alpha=0.3)

# 添加圖例
legend_elements = [plt.Rectangle((0,0),1,1, facecolor=antenna_colors[antenna], 
                                edgecolor='white', alpha=0.8, label=antenna)
                  for antenna in antenna_types]
ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

# 調整佈局
plt.tight_layout()

# 添加說明文字
ax.text(0.02, 0.98, '測試原始數據', transform=ax.transAxes, 
        fontsize=10, verticalalignment='top', 
        bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

plt.show()