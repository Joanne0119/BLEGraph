from datetime import datetime
from typing import Optional
import logging
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

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

class BLEParser:
    def __init__(self):
        pass
    def parse_ble_raw_data(self, raw_data_hex: str, timestamp: datetime) -> Optional[ParsedBLEData]:
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
    