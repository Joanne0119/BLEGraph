import json
import matplotlib
matplotlib.use('Agg')
from datetime import datetime
import threading
import time
import os
from dataclasses import dataclass
from typing import List
import logging
from flask import Flask
from flask_cors import CORS

from DatabaseManager import DatabaseManager 
from MQTTClient import MQTTClient
from ChartGenerator import ChartGenerator
from BLEParser import BLEParser
from api_server import create_api_blueprint

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
    def __init__(self, db_manager: DatabaseManager, mqtt_client: MQTTClient, chart_generator: ChartGenerator):
        
        self.db_manager = db_manager
        self.mqtt_client = mqtt_client
        self.chart_generator = chart_generator
        
        self.mqtt_client.on_message_callback = self._on_message_callback

        ble_parser = BLEParser()
        self.ble_parser = ble_parser
    
    def _on_message_callback(self, topic, payload): 
        try:
            self.db_manager.save_raw_log(payload)
            self._process_ble_log_message(payload)
                
        except Exception as e:
            logger.error(f"Error processing MQTT message payload: {e}", exc_info=True)


    def start(self):
        self.mqtt_client.start()

    def stop(self):
        self.mqtt_client.stop()

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

                    # display_test_group = self.db_manager.get_or_create_display_name(app_test_id)

                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError as e:
                        logger.error(f"Timestamp parsing failed: {timestamp_str} - {e}")
                        continue
                    
                    parsed_data = self.ble_parser.parse_ble_raw_data(raw_data_hex, timestamp)
                    if parsed_data:
                        self.db_manager.save_to_database(parsed_data, app_test_id)
                    else:
                        logger.warning(f"Failed to parse raw data: {raw_data_hex}")
                        
        except Exception as e:
            logger.error(f"Error in _process_ble_log_message: {e}", exc_info=True)

def scheduled_chart_update(db_manager: DatabaseManager, chart_generator: ChartGenerator, interval_seconds=60):

    logger.info(f"every {interval_seconds} seconds, chart will be updated.")
    while True:
        try:
            time.sleep(interval_seconds)
            
            logger.info("exporting to csv...")
            
            csv_path = db_manager.export_to_csv()
            
            if csv_path:
                chart_generator.generate_chart(csv_path)
            else:
                logger.warning("csv data not available to generate chart.")
                
        except Exception as e:
            logger.error(f"Error in scheduled_chart_update: {e}", exc_info=True)

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

    db_manager = DatabaseManager(db_path=config['database']['path'])
    db_manager.init_database()

    chart_generator = ChartGenerator(db_path=config['database']['path'])

    mqtt_client = MQTTClient(
        mqtt_host=config['mqtt']['host'],
        mqtt_port=config['mqtt']['port'],
        mqtt_username=config['mqtt']['username'],
        mqtt_password=config['mqtt']['password'],
        topic="log/scanner/upload",
        on_message_callback=None 
    )

    processor = MQTTBLEDataProcessor(
        db_manager=db_manager,
        mqtt_client=mqtt_client,
        chart_generator=chart_generator
    )

    app = Flask(__name__)
    CORS(app)
    api_routes = create_api_blueprint(db_manager, processor, chart_generator)
    app.register_blueprint(api_routes)

    web_server_port = config['web_server']['port']
    web_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=web_server_port, debug=False),
        daemon=True
    )
    web_thread.start()
    logger.info(f"Web API server started at http://0.0.0.0:{web_server_port}")

    chart_update_interval = config.get('chart_generator', {}).get('update_interval_seconds', 60)
    
    chart_thread = threading.Thread(
        target=scheduled_chart_update,
        args=(db_manager, chart_generator, chart_update_interval), 
        daemon=True  
    )
    chart_thread.start()
    
    processor.start()