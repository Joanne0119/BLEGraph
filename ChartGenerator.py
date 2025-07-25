import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import logging

logger = logging.getLogger(__name__)

class ChartGenerator:
    def __init__(self, db_path):
        self.db_path = db_path
        # No longer need to set Chinese fonts. Matplotlib will use its default.
        plt.rcParams['axes.unicode_minus'] = False
        logger.info("ChartGenerator initialized.")
        
        self.floors_config = self.load_config()
        self.color_palette = ['#D4A574', '#9FD4E8', '#E8A5A5', '#A5E8A5', '#E8C5E8', '#E8E8A5', '#C5E8E8', '#E8C5A5']

    def load_config(self, config_path='bleConfig.json'):
        """Loads floor configuration from a JSON file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('floors', {})
        except FileNotFoundError:
            logger.warning(f"Config file not found at '{config_path}'. Using default floor config.")
            return {'floor1': [1, 2, 3, 4, 5], 'floor2': [6, 7, 8, 9, 10]}

    def get_node_floor(self, node_id, floors_config):
        """Gets the floor for a given node ID."""
        try:
            node_int = int(node_id)
            for floor_name, nodes in floors_config.items():
                if node_int in nodes:
                    return floor_name
        except ValueError: pass
        return None

    def get_same_floor_neighbors(self, node_id, floors_config, df, test_group):
        node_floor = self.get_node_floor(node_id, floors_config)
        if not node_floor: return []
        same_floor_nodes = [str(n) for n in floors_config[node_floor] if str(n) != node_id]
        connections = df[(df['Node ID'] == node_id) & (df['Neighbor ID'].isin(same_floor_nodes)) & (df['Test Group'] == test_group)]
        return connections.nlargest(2, 'Average Reception Rate')['Neighbor ID'].tolist()

    def get_cross_floor_neighbors(self, node_id, floors_config, df, test_group):
        node_floor = self.get_node_floor(node_id, floors_config)
        if not node_floor: return []
        other_floor_nodes = []
        for floor_name, nodes in floors_config.items():
            if floor_name != node_floor:
                other_floor_nodes.extend([str(n) for n in nodes])
        connections = df[(df['Node ID'] == node_id) & (df['Neighbor ID'].isin(other_floor_nodes)) & (df['Test Group'] == test_group)]
        return connections.nlargest(2, 'Average Reception Rate')['Neighbor ID'].tolist()

    def generate_mappings(self, nodes, test_groups, df):
        same_floor_mapping, cross_floor_mapping = {}, {}
        for node in nodes:
            same_neighbors_all, cross_neighbors_all = [], []
            for test_group in test_groups:
                same_neighbors_all.extend(self.get_same_floor_neighbors(node, self.floors_config, df, test_group))
                cross_neighbors_all.extend(self.get_cross_floor_neighbors(node, self.floors_config, df, test_group))
            same_floor_mapping[node] = list(set(same_neighbors_all))
            cross_floor_mapping[node] = list(set(cross_neighbors_all))
        return same_floor_mapping, cross_floor_mapping

    def generate_chart(self, csv_path="data_all.csv", output_path="chart.png"):
        """Generates a stacked bar chart from the CSV data."""
        try:
            if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
                logger.warning(f"CSV file '{csv_path}' not found or is empty. Skipping chart generation.")
                return None
            
            df = pd.read_csv(csv_path)
            if df.empty:
                logger.warning("CSV file is empty. Skipping chart generation.")
                return None
            
            df['Node ID'] = df['Node ID'].astype(str)
            df['Neighbor ID'] = df['Neighbor ID'].astype(str)
            df['Test Group'] = df['Test Group'].astype(str)
            
            nodes = sorted(df['Node ID'].unique(), key=lambda x: int(x))
            test_groups = sorted(df['Test Group'].unique())
            group_colors = {group: self.color_palette[i % len(self.color_palette)] for i, group in enumerate(test_groups)}
            
            x = np.arange(len(nodes))
            bar_width = 0.35 if len(test_groups) <= 2 else 0.3
            group_gap = 0.1
            fig, ax = plt.subplots(figsize=(16, 8))
            
            for i, test_group in enumerate(test_groups):
                x_offset = (i - (len(test_groups) - 1) / 2) * (bar_width + group_gap / len(test_groups))
                x_pos = x + x_offset
                for j, node in enumerate(nodes):
                    group = df[(df['Node ID'] == node) & (df['Test Group'] == test_group)]
                    if len(group) == 0: continue
                    stack_bottom = 0
                    group = group.sort_values('Average Reception Rate', ascending=False)
                    for _, row in group.iterrows():
                        recv, neighbor = row['Average Reception Rate'], row['Neighbor ID']
                        node_floor, neighbor_floor = self.get_node_floor(node, self.floors_config), self.get_node_floor(neighbor, self.floors_config)
                        alpha = 0.9 if node_floor == neighbor_floor else 0.4
                        ax.bar(x_pos[j], recv, width=bar_width, bottom=stack_bottom, color=group_colors[test_group], edgecolor='white', linewidth=0.5, alpha=alpha)
                        if recv > 0:
                            ax.text(x_pos[j], stack_bottom + recv * 0.7, neighbor, ha='center', va='center', fontsize=9, color='red', fontweight='bold')
                            ax.text(x_pos[j], stack_bottom + recv * 0.2, f'{recv:.1f}', ha='center', va='center', fontsize=8, color='black')
                        stack_bottom += recv
            
            ax.set_xticks(x)
            ax.set_xticklabels([f'{node:0>2}' for node in nodes])
            ax.set_xlabel('Node ID', fontsize=12)
            ax.set_ylabel('Average Reception Rate (packets/sec)', fontsize=12)
            ax.set_title('Node Reception Rate Comparison by Test Group', fontsize=14, fontweight='bold')
            
            y_max = df.groupby(['Node ID', 'Test Group'])['Average Reception Rate'].sum().max()
            ax.set_ylim(0, y_max * 1.5 if pd.notna(y_max) and y_max > 0 else 1)
            ax.grid(True, axis='y', linestyle='--', alpha=0.3)
            
            legend_elements = [plt.Rectangle((0,0),1,1, facecolor=group_colors[group], alpha=0.9, label=f'{group} (Same Floor)') for group in test_groups]
            legend_elements += [plt.Rectangle((0,0),1,1, facecolor=group_colors[group], alpha=0.4, label=f'{group} (Cross-Floor)') for group in test_groups]
            ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
            
            same_floor_mapping, cross_floor_mapping = self.generate_mappings(nodes, test_groups, df)
            y_position, box_colors = 0.98, ['lightyellow', 'lightblue', 'lightgreen', 'lightpink', 'lightgray']
            
            for i, test_group in enumerate(test_groups):
                cross_floor_data = [df[(df['Node ID'] == n) & (df['Neighbor ID'] == nb) & (df['Test Group'] == test_group)]['Average Reception Rate'].iloc[0] for n, nbs in cross_floor_mapping.items() for nb in nbs if not df[(df['Node ID'] == n) & (df['Neighbor ID'] == nb) & (df['Test Group'] == test_group)].empty]
                same_floor_data = [df[(df['Node ID'] == n) & (df['Neighbor ID'] == nb) & (df['Test Group'] == test_group)]['Average Reception Rate'].iloc[0] for n, nbs in same_floor_mapping.items() for nb in nbs if not df[(df['Node ID'] == n) & (df['Neighbor ID'] == nb) & (df['Test Group'] == test_group)].empty]
                
                cross_avg, same_avg = np.mean(cross_floor_data) if cross_floor_data else 0, np.mean(same_floor_data) if same_floor_data else 0
                total_avg = df[df['Test Group'] == test_group]['Average Reception Rate'].mean()
                
                stats_text = f"""{test_group} Statistics
Same-Floor Avg: {same_avg:.2f} pkts/sec
Cross-Floor Avg: {cross_avg:.2f} pkts/sec
Overall Avg: {total_avg:.2f} pkts/sec"""
                ax.text(0.02, y_position - i * 0.12, stats_text, transform=ax.transAxes, fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', facecolor=box_colors[i % len(box_colors)], alpha=0.9))
            
            if len(test_groups) >= 2:
                base_group, base_avg = test_groups[0], df[df['Test Group'] == test_groups[0]]['Average Reception Rate'].mean()
                improvement_text = f"Improvement vs {base_group}:\n"
                for test_group in test_groups[1:]:
                    current_avg = df[df['Test Group'] == test_group]['Average Reception Rate'].mean()
                    improvement = ((current_avg - base_avg) / base_avg) * 100 if base_avg > 0 else 0
                    improvement_text += f"{test_group}: {current_avg - base_avg:+.2f} pkts/sec ({improvement:+.1f}%)\n"
                ax.text(0.02, y_position - len(test_groups) * 0.12, improvement_text, transform=ax.transAxes, fontsize=9, verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightcyan', alpha=0.9))
            
            plt.tight_layout()
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            
            logger.info(f"Chart generated successfully: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating chart: {e}", exc_info=True)
            return None
        
    def get_chart_data(self, df: pd.DataFrame):
        """
        處理 DataFrame 並回傳一個可用於前端圖表的字典 (JSON)。
        """
        df = df[df['Average Reception Rate'] > 0].copy()

        if df.empty:
            logger.warning("DataFrame is empty. Cannot generate chart data.")
            return {"nodes": [], "data_points": [], "statistics": {}}

        df['Node ID'] = df['Node ID'].astype(str)
        df['Neighbor ID'] = df['Neighbor ID'].astype(str)
        df['Test Group'] = df['Test Group'].astype(str)

        df.sort_values(by=['Test Group', 'Average Reception Rate'], ascending=[True, False], inplace=True)
        nodes = sorted(df['Node ID'].unique(), key=lambda x: int(x))
        test_groups = sorted(df['Test Group'].unique())
        
        chart_json = {
            "nodes": nodes,         # 提供 X 軸的標籤
            "data_points": [],      # 提供詳細的數據點
            "statistics": {}        # 提供額外的統計數據
        }

        for _, row in df.iterrows():
            node_id = str(row['Node ID'])
            neighbor_id = str(row['Neighbor ID'])
            
            # 判斷樓層類型
            node_floor = self.get_node_floor(node_id, self.floors_config)
            neighbor_floor = self.get_node_floor(neighbor_id, self.floors_config)
            floor_type = "same-floor" if node_floor == neighbor_floor else "cross-floor"
            
            chart_json["data_points"].append({
                "node_id": node_id,
                "neighbor_id": neighbor_id,
                "reception_rate": row['Average Reception Rate'],
                "test_group": row['Test Group'],
                "floor_type": floor_type
            })

        for test_group in test_groups:
            group_df = df[df['Test Group'] == test_group]
            
            # 計算同樓層和跨樓層的平均值
            same_floor_sum = 0
            same_floor_count = 0
            cross_floor_sum = 0
            cross_floor_count = 0

            for _, row in group_df.iterrows():
                node_floor = self.get_node_floor(str(row['Node ID']), self.floors_config)
                neighbor_floor = self.get_node_floor(str(row['Neighbor ID']), self.floors_config)
                rate = row['Average Reception Rate']
                
                if node_floor == neighbor_floor:
                    same_floor_sum += rate
                    same_floor_count += 1
                else:
                    cross_floor_sum += rate
                    cross_floor_count += 1

            
            same_avg = same_floor_sum / same_floor_count if same_floor_count > 0 else 0
            cross_avg = cross_floor_sum / cross_floor_count if cross_floor_count > 0 else 0
            total_avg = group_df['Average Reception Rate'].mean()

            chart_json["statistics"][test_group] = {
                "overall_avg": round(total_avg, 2) if pd.notna(total_avg) else 0,
                "cross_floor_avg": round(cross_avg, 2),
                "same_floor_avg": round(same_avg, 2)
            }
        
        if len(test_groups) >= 2:
            base_group = test_groups[0]
            base_avg = chart_json["statistics"][base_group]["overall_avg"]
            improvements = {}
            for test_group in test_groups[1:]:
                current_avg = chart_json["statistics"][test_group]["overall_avg"]
                diff = current_avg - base_avg
                percent = (diff / base_avg) * 100 if base_avg > 0 else 0
                improvements[test_group] = {
                    "diff": f"{diff:+.2f}",
                    "percent": f"{percent:+.1f}%"
                }
            chart_json["statistics"]["improvements"] = improvements

        return chart_json
    def _adjust_color_alpha(self, hex_color, alpha):
        """ HEX color to RGBA"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return f'rgba({r}, {g}, {b}, {alpha})'