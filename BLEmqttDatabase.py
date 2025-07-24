import paho.mqtt.client as mqtt
import sqlite3
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import threading
import time
import os
from dataclasses import dataclass
from typing import List, Optional
import logging
from flask import Flask, jsonify, send_file, request

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Data Structures ---
@dataclass
class DeviceInfo:
    device_id: str
    count: int
    reception_rate: float
    timestamp: datetime

@dataclass
class ParsedBLEData:
    sender_device_id: str
    temperature: int
    atmospheric_pressure: float
    seconds: int
    devices: List[DeviceInfo]
    has_reached_target: bool
    raw_timestamp: datetime

class MQTTBLEDataProcessor:
    def __init__(self, mqtt_host="localhost", mqtt_port=1883,
                 mqtt_username="root", mqtt_password="password",
                 db_path="db.db"):
        
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.db_path = db_path
        
        self.mqtt_client = mqtt.Client(client_id=f"backend-processor-{os.getpid()}")
        self.mqtt_client.username_pw_set(mqtt_username, mqtt_password)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        
        self._init_database()
        self.chart_generator = ChartGenerator(self.db_path)
        
        self.running = False
        self.auto_update_thread = None
        
    def _init_database(self):
        """Initializes the database tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS raw_log (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS device_reception_data (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_device_id TEXT, receiver_device_id TEXT, reception_rate REAL, timestamp DATETIME, test_group TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS average_reception_rates (id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT, neighbor_id TEXT, average_reception_rate REAL, test_group TEXT, UNIQUE(node_id, neighbor_id, test_group))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS test_group_mapping (id INTEGER PRIMARY KEY AUTOINCREMENT, app_test_id TEXT UNIQUE, display_name TEXT)''')
            conn.commit()
            logger.info("Database initialized successfully.")
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT on_connect callback."""
        if rc == 0:
            logger.info("MQTT connection successful.")
            client.subscribe("log/scanner/upload")
            logger.info("Subscribed to topic: log/scanner/upload")
        else:
            logger.error(f"MQTT connection failed with code: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT on_message callback."""
        try:
            payload = msg.payload.decode('utf-8')
            logger.info(f"Received MQTT message on topic '{msg.topic}': {payload[:100]}...")
            
            with sqlite3.connect(self.db_path) as conn:
                conn.cursor().execute("INSERT INTO raw_log (payload) VALUES (?)", (payload,))
                conn.commit()

            self._process_ble_log_message(payload)
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}", exc_info=True)

    def _process_ble_log_message(self, payload):
        """Processes the BLE log message payload."""
        try:
            components = payload.split(',')
            if len(components) % 4 != 0:
                logger.warning(f"Invalid BLE log format (number of components is not a multiple of 4): {payload}")
                return

            for i in range(0, len(components), 4):
                if i + 3 < len(components):
                    raw_data_hex = components[i].strip()
                    rssi = components[i+1].strip()
                    timestamp_str = components[i+2].strip()
                    app_test_id = components[i+3].strip()
                    
                    display_test_group = self._get_or_create_display_name(app_test_id)

                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError as e:
                        logger.error(f"Timestamp parsing failed: {timestamp_str} - {e}")
                        continue
                    
                    parsed_data = self._parse_ble_raw_data(raw_data_hex, timestamp)
                    if parsed_data:
                        self._save_to_database(parsed_data, display_test_group)
                    else:
                        logger.warning(f"Failed to parse raw data: {raw_data_hex}")
                        
        except Exception as e:
            logger.error(f"Error in _process_ble_log_message: {e}", exc_info=True)

    def _parse_ble_raw_data(self, raw_data_hex: str, timestamp: datetime) -> Optional[ParsedBLEData]:
        """Parses the raw BLE data string."""
        try:
            cleaned_data = raw_data_hex.replace(' ', '')
            bytes_data = bytes.fromhex(cleaned_data)
            
            if len(bytes_data) == 15:
                return self._parse_15_byte_format(bytes_data, timestamp)
            elif len(bytes_data) >= 29:
                return self._parse_29_byte_format(bytes_data, timestamp)
            else:
                logger.warning(f"Unsupported data length: {len(bytes_data)} bytes")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing BLE data hex '{raw_data_hex}': {e}", exc_info=True)
            return None

    def _parse_15_byte_format(self, bytes_data: bytes, timestamp: datetime) -> Optional[ParsedBLEData]:
        """Parses the 15-byte format (Swift compatible)."""
        try:
            temperature = int(bytes_data[0])
            atmospheric_pressure = int.from_bytes(bytes_data[1:4], byteorder='big') / 100.0
            seconds = int(bytes_data[4])
            devices = []
            for i in range(5):
                idx = 5 + (i * 2)
                device_id, count = str(bytes_data[idx]), int(bytes_data[idx + 1])
                if device_id != "0":
                    reception_rate = count / seconds if seconds > 0 else 0
                    devices.append(DeviceInfo(device_id, count, reception_rate, timestamp))
            
            has_reached_target = any(d.count >= 100 for d in devices)
            sender_id = "swift_device"
            
            return ParsedBLEData(sender_id, temperature, atmospheric_pressure, seconds, devices, has_reached_target, timestamp)
            
        except Exception as e:
            logger.error(f"Error parsing 15-byte format: {e}", exc_info=True)
            return None

    def _parse_29_byte_format(self, bytes_data: bytes, timestamp: datetime) -> Optional[ParsedBLEData]:
        """Parses the 29-byte format (original)."""
        data_bytes = bytes_data[13:28]
        sender_id = str(bytes_data[-1])
        temperature = int(data_bytes[0])
        atmospheric_pressure = int.from_bytes(data_bytes[1:4], byteorder='big') / 100.0
        seconds = int(data_bytes[4])
        devices = []
        for i in range(5):
            idx = 5 + (i * 2)
            device_id, count = str(data_bytes[idx]), int(data_bytes[idx + 1])
            reception_rate = count / seconds if seconds > 0 else 0
            devices.append(DeviceInfo(device_id, count, reception_rate, timestamp))
        
        has_reached_target = any(d.count >= 100 for d in devices)
        return ParsedBLEData(sender_id, temperature, atmospheric_pressure, seconds, devices, has_reached_target, timestamp)

    def _save_to_database(self, parsed_data: ParsedBLEData, test_group: str):
        """Saves parsed data to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for device in parsed_data.devices:
                    cursor.execute('''INSERT INTO device_reception_data (sender_device_id, receiver_device_id, reception_rate, timestamp, test_group) VALUES (?, ?, ?, ?, ?)''', 
                                   (parsed_data.sender_device_id, device.device_id, device.reception_rate, device.timestamp, test_group))
                conn.commit()
                logger.info(f"Data saved successfully for sender {parsed_data.sender_device_id}, test group '{test_group}'.")
                self._update_average_rates()
        except Exception as e:
            logger.error(f"Error saving data to database: {e}", exc_info=True)
    
    def _update_average_rates(self):
        """Updates the average reception rates table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''SELECT sender_device_id, receiver_device_id, AVG(reception_rate), test_group FROM device_reception_data GROUP BY sender_device_id, receiver_device_id, test_group''')
                results = cursor.fetchall()
                for row in results:
                    cursor.execute('''INSERT OR REPLACE INTO average_reception_rates (node_id, neighbor_id, average_reception_rate, test_group) VALUES (?, ?, ?, ?)''', row)
                conn.commit()
                logger.info(f"Average reception rates updated for {len(results)} combinations.")
        except Exception as e:
            logger.error(f"Error updating average rates: {e}", exc_info=True)
    
    def export_to_csv(self, output_path="data_all.csv"):
        """Exports average reception rates to a CSV file."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query('''SELECT node_id as 'Node ID', neighbor_id as 'Neighbor ID', average_reception_rate as 'Average Reception Rate', test_group as 'Test Group' FROM average_reception_rates ORDER BY test_group, CAST(node_id AS INTEGER), CAST(neighbor_id AS INTEGER)''', conn)
                df.to_csv(output_path, index=False, encoding='utf-8-sig')
                logger.info(f"CSV exported successfully: {output_path}")
                return output_path
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}", exc_info=True)
            return None
            
    def start(self):
        """Starts the MQTT processor."""
        self.running = True
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.auto_update_thread = threading.Thread(target=self._auto_update_task, daemon=True)
        self.auto_update_thread.start()
        self.mqtt_client.loop_forever()

    def stop(self):
        """Stops the MQTT processor."""
        self.running = False
        if self.mqtt_client.is_connected():
            self.mqtt_client.disconnect()
        logger.info("MQTT processor stopped.")
    
    def _auto_update_task(self):
        """Background task to automatically update CSV and charts."""
        while self.running:
            time.sleep(60)
            logger.info("Running scheduled update task...")
            csv_path = self.export_to_csv()
            if csv_path:
                self.chart_generator.generate_chart(csv_path)

    def _get_or_create_display_name(self, app_test_id: str) -> str:
        """Gets or creates a human-readable display name for a given test ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT display_name FROM test_group_mapping WHERE app_test_id = ?", (app_test_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            else:
                cursor.execute("SELECT count(id) FROM test_group_mapping")
                count = cursor.fetchone()[0]
                new_display_name = f"Test #{count + 1}"
                cursor.execute("INSERT INTO test_group_mapping (app_test_id, display_name) VALUES (?, ?)", (app_test_id, new_display_name))
                conn.commit()
                logger.info(f"New test ID '{app_test_id}' detected. Assigned name: '{new_display_name}'")
                return new_display_name
            
    def get_all_test_groups(self):
        """Retrieves a list of all unique test group display names."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT display_name FROM test_group_mapping ORDER BY display_name")
                results = cursor.fetchall()
                return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Error getting test groups: {e}", exc_info=True)
            return []

    def delete_test_group_data(self, display_name: str):
        """Deletes all data associated with a specific test group display name."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                logger.warning(f"!!! Attempting to delete all data for test group: '{display_name}' !!!")
                cursor.execute("DELETE FROM device_reception_data WHERE test_group = ?", (display_name,))
                logger.info(f"Deleted from device_reception_data for group '{display_name}'.")
                cursor.execute("DELETE FROM average_reception_rates WHERE test_group = ?", (display_name,))
                logger.info(f"Deleted from average_reception_rates for group '{display_name}'.")
                cursor.execute("DELETE FROM test_group_mapping WHERE display_name = ?", (display_name,))
                logger.info(f"Deleted from test_group_mapping for group '{display_name}'.")

                # can't delete from raw_log as it's a permanent audit log without a direct test_group link.

                conn.commit()
                logger.warning(f"Successfully deleted all data for test group: '{display_name}'.")
                return True
        except Exception as e:
            logger.error(f"Error deleting test group '{display_name}': {e}", exc_info=True)
            return False
            
    def clear_all_data(self):
        """Clears all relevant data tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                logger.warning("!!! Clearing all database tables !!!")
                tables = ['device_reception_data', 'average_reception_rates', 'raw_log', 'test_group_mapping']
                for table in tables:
                    cursor.execute(f"DELETE FROM {table}")
                    logger.info(f"Cleared table: {table}")
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({','.join('?'*len(tables))})", tables)
                logger.info("Reset ID counters.")
                conn.commit()
                logger.warning("Database cleared successfully!")
                return True
        except Exception as e:
            logger.error(f"Error clearing database: {e}", exc_info=True)
            return False

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

class WebAPIServer:
    def __init__(self, processor: MQTTBLEDataProcessor, port=5000):
        self.processor = processor
        self.app = Flask(__name__)
        self.port = port
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/')
        def index():
            return "<h1>BLE Data Backend Service</h1><p><a href='/api/chart'>View Chart</a></p><p><a href='/api/data'>Download CSV</a></p>"
        @self.app.route('/api/chart')
        def get_chart():
            if not os.path.exists("chart.png"): return jsonify({'error': 'Chart file not yet generated.'}), 404
            return send_file("chart.png", mimetype='image/png')
        @self.app.route('/api/data')
        def get_data():
            csv_path = self.processor.export_to_csv()
            if not csv_path: return jsonify({'error': 'Failed to export CSV.'}), 500
            return send_file(csv_path, mimetype='text/csv')
        @self.app.route('/api/clear_database', methods=['POST'])
        def clear_database():
            data = request.json
            if not data or data.get('confirm') != 'yes':
                return jsonify({'error': 'Dangerous operation. Please include {"confirm": "yes"} in the JSON body to confirm.'}), 400
            if self.processor.clear_all_data():
                return jsonify({'message': 'Database cleared successfully.'}), 200
            else:
                return jsonify({'error': 'Internal error while clearing the database.'}), 500
        @self.app.route('/api/test_groups', methods=['GET'])
        def get_test_groups():
            groups = self.processor.get_all_test_groups()
            return jsonify(groups)

        @self.app.route('/api/delete_test', methods=['POST'])
        def delete_test_group():
            data = request.json
            display_name = data.get('display_name') if data else None

            if not display_name:
                return jsonify({'error': 'Missing "display_name" in request body.'}), 400
            
            # Check if test group exists before attempting deletion
            existing_groups = self.processor.get_all_test_groups()
            if display_name not in existing_groups:
                 return jsonify({'error': f"Test group '{display_name}' not found."}), 404

            if self.processor.delete_test_group_data(display_name):
                # After deletion, regenerate CSV and Chart
                csv_path = self.processor.export_to_csv()
                if csv_path:
                    self.processor.chart_generator.generate_chart(csv_path)
                return jsonify({'message': f"Successfully deleted all data for test group '{display_name}'."}), 200
            else:
                return jsonify({'error': f"An internal error occurred while deleting test group '{display_name}'."}), 500
        

    def start(self):
        self.app.run(host='0.0.0.0', port=self.port, debug=False)

if __name__ == "__main__":
    try:
        with open('bleConfig.json', 'r') as f:
            config = json.load(f)
        logger.info("Configuration file 'bleConfig.json' loaded successfully.")
    except FileNotFoundError:
        logger.error("Error: Configuration file 'bleConfig.json' not found!")
        exit()
    except json.JSONDecodeError:
        logger.error("Error: Configuration file 'bleConfig.json' is not valid JSON.")
        exit()

    processor = MQTTBLEDataProcessor(
        mqtt_host=config['mqtt']['host'],
        mqtt_port=config['mqtt']['port'],
        mqtt_username=config['mqtt']['username'],
        mqtt_password=config['mqtt']['password'],
        db_path=config['database']['path']
    )
    
    web_server_port = config['web_server']['port']
    web_server = WebAPIServer(processor, port=web_server_port)
    
    web_thread = threading.Thread(target=web_server.start, daemon=True)
    web_thread.start()
    logger.info(f"Web API server started at http://0.0.0.0:{web_server_port}")
    
    try:
        processor.start()
    except KeyboardInterrupt:
        logger.info("Interrupt signal received, stopping...")
        processor.stop()