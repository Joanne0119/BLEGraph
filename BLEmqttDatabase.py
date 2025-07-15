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

# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 資料結構定義 ---
@dataclass
class DeviceInfo:
    device_id: str
    count: int
    reception_rate: float
    timestamp: datetime

@dataclass
class ParsedBLEData:
    sender_device_id: str  # 【修正】新增發送者 ID
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
        self.current_test_group = "第一次測試" # 預設測試組別
        
    def _init_database(self):
        """初始化數據庫表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 原始數據表 (可選，用於追蹤)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 裝置接收數據表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_reception_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_device_id TEXT,
                    receiver_device_id TEXT,
                    reception_rate REAL,
                    timestamp DATETIME,
                    test_group TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 平均接收率表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS average_reception_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT,
                    neighbor_id TEXT,
                    average_reception_rate REAL,
                    test_group TEXT,
                    UNIQUE(node_id, neighbor_id, test_group)
                )
            ''')
            conn.commit()
            logger.info("數據庫初始化完成")
    
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT 連接回調"""
        if rc == 0:
            logger.info("MQTT 連接成功")
            client.subscribe("log/scanner/upload")
            logger.info("已訂閱主題: log/scanner/upload")
        else:
            logger.error(f"MQTT 連接失敗，返回碼: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT 訊息處理 - 增強除錯版"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.info(f"收到 MQTT 訊息 - 主題: {topic}")
            logger.info(f"原始 payload: {payload}")
            
            # 將收到的原始日誌存檔備查
            with sqlite3.connect(self.db_path) as conn:
                conn.cursor().execute("INSERT INTO raw_log (payload) VALUES (?)", (payload,))
                conn.commit()

            self._process_ble_log_message(payload)
                
        except Exception as e:
            logger.error(f"處理 MQTT 訊息時發生嚴重錯誤: {e}", exc_info=True)

    def _process_ble_log_message(self, payload):
        """處理 BLE 日誌訊息 - 增強除錯版"""
        try:
            logger.info(f"開始處理 payload: {payload}")
            
            components = payload.split(',')
            logger.info(f"分割後的組件數量: {len(components)}")
            logger.info(f"組件內容: {components}")
            
            if len(components) < 3:
                logger.warning(f"無效的 BLE 日誌格式 (元件不足): {payload}")
                return
            
            # 處理可能的多筆資料，每3個一組
            for i in range(0, len(components), 3):
                if i + 2 < len(components):
                    raw_data_hex = components[i].strip()
                    rssi = components[i+1].strip()
                    timestamp_str = components[i+2].strip()
                    
                    logger.info(f"處理第 {i//3 + 1} 組數據:")
                    logger.info(f"  - raw_data_hex: {raw_data_hex}")
                    logger.info(f"  - rssi: {rssi}")
                    logger.info(f"  - timestamp_str: {timestamp_str}")
                    
                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        logger.info(f"  - 時間戳解析成功: {timestamp}")
                    except ValueError as e:
                        logger.error(f"  - 時間戳解析失敗: {e}")
                        continue
                    
                    parsed_data = self._parse_ble_raw_data(raw_data_hex, timestamp)
                    if parsed_data:
                        logger.info(f"  - 數據解析成功，發送者ID: {parsed_data.sender_device_id}")
                        logger.info(f"  - 裝置數量: {len(parsed_data.devices)}")
                        self._save_to_database(parsed_data)
                    else:
                        logger.warning(f"  - 數據解析失敗")
                        
        except Exception as e:
            logger.error(f"處理 BLE 日誌訊息時發生錯誤: {e}", exc_info=True)

    def _parse_ble_raw_data(self, raw_data_hex: str, timestamp: datetime) -> Optional[ParsedBLEData]:
        """解析 BLE 原始數據 - 增強除錯版"""
        try:
            logger.info(f"開始解析原始數據: {raw_data_hex}")
            
            cleaned_data = raw_data_hex.replace(' ', '')
            logger.info(f"清理後的數據: {cleaned_data}")
            logger.info(f"數據長度: {len(cleaned_data)} 字符")
            
            if len(cleaned_data) % 2 != 0:
                logger.warning(f"無效的十六進制數據 (長度非偶數): {raw_data_hex}")
                return None
            
            bytes_data = bytes.fromhex(cleaned_data)
            logger.info(f"轉換為字節後長度: {len(bytes_data)} 字節")
            logger.info(f"字節數據: {bytes_data.hex()}")
            
            # 根據實際數據長度調整解析邏輯
            if len(bytes_data) == 15:
                # 如果是純15字節數據（Swift格式）
                logger.info("檢測到15字節格式，使用Swift兼容解析")
                return self._parse_15_byte_format(bytes_data, timestamp)
            elif len(bytes_data) >= 29:
                # 如果是29字節格式（原Python格式）
                logger.info("檢測到29字節格式，使用原始解析")
                return self._parse_29_byte_format(bytes_data, timestamp)
            else:
                logger.warning(f"不支援的數據長度: {len(bytes_data)} 字節")
                return None
                
        except Exception as e:
            logger.error(f"解析 BLE 數據 '{raw_data_hex}' 時發生錯誤: {e}", exc_info=True)
            return None

    def _parse_15_byte_format(self, bytes_data: bytes, timestamp: datetime) -> Optional[ParsedBLEData]:
        """解析15字節格式的數據（Swift兼容）"""
        try:
            logger.info("使用15字節格式解析")
            
            temperature = int(bytes_data[0])
            logger.info(f"溫度: {temperature}")
            
            pressure_bytes = bytes_data[1:4]
            atmospheric_pressure = int.from_bytes(pressure_bytes, byteorder='big') / 100.0
            logger.info(f"大氣壓力: {atmospheric_pressure}")
            
            seconds = int(bytes_data[4])
            logger.info(f"秒數: {seconds}")
            
            devices = []
            for i in range(5):
                device_block_start_index = 5 + (i * 2)
                
                if device_block_start_index + 1 < len(bytes_data):
                    device_id = str(bytes_data[device_block_start_index])
                    count = int(bytes_data[device_block_start_index + 1])
                    
                    if device_id != "0":  # 忽略ID為0的裝置
                        reception_rate = count / seconds if seconds > 0 else 0
                        devices.append(DeviceInfo(
                            device_id=device_id,
                            count=count,
                            reception_rate=reception_rate,
                            timestamp=timestamp
                        ))
                        logger.info(f"裝置 {i+1}: ID={device_id}, count={count}, rate={reception_rate}")
            
            has_reached_target = any(d.count >= 100 for d in devices)
            
            # 15字節格式沒有sender_id，使用"unknown"或從其他地方獲取
            sender_id = "unknown"
            
            return ParsedBLEData(
                sender_device_id=sender_id,
                temperature=temperature,
                atmospheric_pressure=atmospheric_pressure,
                seconds=seconds,
                devices=devices,
                has_reached_target=has_reached_target,
                raw_timestamp=timestamp
            )
            
        except Exception as e:
            logger.error(f"解析15字節格式時發生錯誤: {e}", exc_info=True)
            return None

    def _parse_29_byte_format(self, bytes_data: bytes, timestamp: datetime) -> Optional[ParsedBLEData]:
        """解析29字節格式的數據（原始格式）"""
        # 原始的解析邏輯
        data_bytes = bytes_data[13:28]
        sender_id = str(bytes_data[-1])
        
        temperature = int(data_bytes[0])
        pressure_bytes = data_bytes[1:4]
        atmospheric_pressure = int.from_bytes(pressure_bytes, byteorder='big') / 100.0
        seconds = int(data_bytes[4])
        
        devices = []
        for i in range(5):
            device_block_start_index = 5 + (i * 2)
            
            if device_block_start_index + 1 < len(data_bytes):
                device_id = str(data_bytes[device_block_start_index])
                count = int(data_bytes[device_block_start_index + 1])
                
                reception_rate = count / seconds if seconds > 0 else 0
                devices.append(DeviceInfo(
                    device_id=device_id,
                    count=count,
                    reception_rate=reception_rate,
                    timestamp=timestamp
                ))
        
        has_reached_target = any(d.count >= 100 for d in devices)
        
        return ParsedBLEData(
            sender_device_id=sender_id,
            temperature=temperature,
            atmospheric_pressure=atmospheric_pressure,
            seconds=seconds,
            devices=devices,
            has_reached_target=has_reached_target,
            raw_timestamp=timestamp
        )
    def _save_to_database(self, parsed_data: ParsedBLEData):
        """ 儲存解析後的數據到數據庫"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for device in parsed_data.devices:
                    cursor.execute('''
                        INSERT INTO device_reception_data 
                        (sender_device_id, receiver_device_id, reception_rate, timestamp, test_group)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        parsed_data.sender_device_id, # 【修正】使用解析出的發送者 ID
                        device.device_id,
                        device.reception_rate,
                        device.timestamp,
                        self.current_test_group
                    ))
                
                conn.commit()
                logger.info(f"數據儲存成功 - 發送者: {parsed_data.sender_device_id}, 鄰居數量: {len(parsed_data.devices)}")
                
                # 每次儲存後都觸發一次平均值更新
                self._update_average_rates()

        except Exception as e:
            logger.error(f"儲存數據時發生錯誤: {e}", exc_info=True)
    
    def _update_average_rates(self):
        """更新平均接收率"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        sender_device_id as node_id,
                        receiver_device_id as neighbor_id,
                        AVG(reception_rate) as avg_rate,
                        test_group
                    FROM device_reception_data
                    GROUP BY sender_device_id, receiver_device_id, test_group
                ''')
                results = cursor.fetchall()
                
                for row in results:
                    node_id, neighbor_id, avg_rate, test_group = row
                    cursor.execute('''
                        INSERT OR REPLACE INTO average_reception_rates
                        (node_id, neighbor_id, average_reception_rate, test_group)
                        VALUES (?, ?, ?, ?)
                    ''', (node_id, neighbor_id, avg_rate, test_group))
                
                conn.commit()
                logger.info(f"平均接收率更新完成，共處理 {len(results)} 筆組合。")
                
        except Exception as e:
            logger.error(f"更新平均接收率時發生錯誤: {e}", exc_info=True)
    
    def export_to_csv(self, output_path="data_all.csv"):
        """匯出平均接收率到 CSV"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query('''
                    SELECT 
                        node_id as '節點ID',
                        neighbor_id as '鄰居ID', 
                        average_reception_rate as '平均接收率',
                        test_group as '測試組別'
                    FROM average_reception_rates
                    ORDER BY test_group, CAST(node_id AS INTEGER), CAST(neighbor_id AS INTEGER)
                ''', conn)
                
                df.to_csv(output_path, index=False, encoding='utf-8-sig')
                logger.info(f"CSV 匯出成功: {output_path}")
                return output_path
        except Exception as e:
            logger.error(f"匯出 CSV 時發生錯誤: {e}", exc_info=True)
            return None
            
    def start(self):
        """啟動 MQTT 處理器"""
        try:
            self.running = True
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.auto_update_thread = threading.Thread(target=self._auto_update_task)
            self.auto_update_thread.daemon = True
            self.auto_update_thread.start()
            self.mqtt_client.loop_forever()
        except Exception as e:
            logger.error(f"啟動 MQTT 處理器時發生錯誤: {e}", exc_info=True)

    def stop(self):
        """停止 MQTT 處理器"""
        self.running = False
        if self.mqtt_client.is_connected():
            self.mqtt_client.disconnect()
        logger.info("MQTT 處理器已停止")
    
    def _auto_update_task(self):
        """自動更新 CSV 和圖表的背景任務"""
        while self.running:
            time.sleep(60) # 每 60 秒執行一次
            logger.info("執行自動更新任務...")
            csv_path = self.export_to_csv()
            if csv_path:
                self.chart_generator.generate_chart(csv_path)

# ChartGenerator 和 WebAPIServer 類別可以保持不變，此處為簡化版
class ChartGenerator:
    def __init__(self, db_path):
        self.db_path = db_path
        try:
            plt.rcParams['font.family'] = 'Microsoft JhengHei'  # Windows
        except:
            try:
                plt.rcParams['font.family'] = 'PingFang TC'  # macOS
            except:
                try:
                    plt.rcParams['font.family'] = 'SimHei'  # 簡體中文
                except:
                    plt.rcParams['font.family'] = 'DejaVu Sans'  # 備用字體

    
    def generate_chart(self, csv_path="testData_all.csv", output_path="chart.png"):
        # (此處省略詳細的繪圖邏輯，可直接使用您原有的程式碼)
        try:
            if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
                logger.warning(f"CSV 檔案不存在或為空: {csv_path}，跳過圖表生成。")
                return None
            df = pd.read_csv(csv_path)
            if df.empty:
                logger.warning("CSV 檔案內容為空，跳過圖表生成。")
                return None
            
            fig, ax = plt.subplots(figsize=(10, 6))
            df_grouped = df.groupby('節點ID')['平均接收率'].sum()
            if not df_grouped.empty:
                df_grouped.plot(kind='bar', ax=ax)
                ax.set_title('各節點總平均接收率')
                ax.set_ylabel('總平均接收率')
                plt.tight_layout()
                plt.savefig(output_path)
            plt.close(fig)
            logger.info(f"圖表生成成功: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"生成圖表時發生錯誤: {e}", exc_info=True)
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
            return "<h1>BLE 數據後端服務 (RawData)</h1><p><a href='/api/chart'>查看圖表</a></p><p><a href='/api/data'>下載 CSV</a></p>"
        @self.app.route('/api/chart')
        def get_chart():
            if not os.path.exists("chart.png"): return jsonify({'error': '圖表檔案尚未生成'}), 404
            return send_file("chart.png", mimetype='image/png')
        @self.app.route('/api/data')
        def get_data():
            csv_path = self.processor.export_to_csv()
            if not csv_path: return jsonify({'error': '無法匯出 CSV'}), 500
            return send_file(csv_path, mimetype='text/csv')
        @self.app.route('/api/test_group', methods=['POST'])
        def set_test_group():
            data = request.json
            test_group = data.get('test_group')
            if not test_group: return jsonify({'error': 'test_group is required'}), 400
            self.processor.current_test_group = test_group
            logger.info(f"測試組別已透過 API 設定為: {test_group}")
            return jsonify({'message': f'Test group set to {test_group}'})

    def start(self):
        self.app.run(host='0.0.0.0', port=self.port, debug=False)

# --- 主程式 ---
if __name__ == "__main__":
    # 讀取 config.json 設定檔
    try:
        with open('bleConfig.json', 'r') as f:
            config = json.load(f)
        logger.info("成功讀取 bleConfig.json 設定檔")
    except FileNotFoundError:
        logger.error("錯誤：找不到 bleConfig.json 檔案！")
        exit() # 如果找不到設定檔，就結束程式
    except json.JSONDecodeError:
        logger.error("錯誤：bleConfig.json 檔案格式不正確！")
        exit()

    # 從設定檔中獲取參數並實例化處理器
    # 【重要】將讀取到的設定傳入 class 中
    processor = MQTTBLEDataProcessor(
        mqtt_host=config['mqtt']['host'],
        mqtt_port=config['mqtt']['port'],
        mqtt_username=config['mqtt']['username'],
        mqtt_password=config['mqtt']['password'],
        db_path=config['database']['path']
    )
    
    # 從設定檔獲取 Web 伺服器端口
    web_server_port = config['web_server']['port']
    web_server = WebAPIServer(processor, port=web_server_port)
    
    web_thread = threading.Thread(target=web_server.start, daemon=True)
    web_thread.start()
    logger.info(f"Web API 伺服器啟動在 http://0.0.0.0:{web_server_port}")
    
    try:
        processor.start()
    except KeyboardInterrupt:
        logger.info("收到中斷信號，正在停止...")
        processor.stop()
