import sqlite3
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.execute('PRAGMA journal_mode=WAL;')
        return conn

    def init_database(self):
        """Initializes the database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS raw_log (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS device_reception_data (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_device_id TEXT, receiver_device_id TEXT, reception_rate REAL, timestamp DATETIME, test_group TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS average_reception_rates (id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT, neighbor_id TEXT, average_reception_rate REAL, test_group TEXT, UNIQUE(node_id, neighbor_id, test_group))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS test_group_mapping (id INTEGER PRIMARY KEY AUTOINCREMENT, app_test_id TEXT UNIQUE, display_name TEXT)''')
            conn.commit()
            logger.info("Database initialized successfully.")
    def save_to_database(self, parsed_data, test_group: str):
        """Saves parsed data to the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for device in parsed_data.devices:
                    cursor.execute('''INSERT INTO device_reception_data (sender_device_id, receiver_device_id, reception_rate, timestamp, test_group) VALUES (?, ?, ?, ?, ?)''', 
                                   (parsed_data.sender_device_id, device.device_id, device.reception_rate, device.timestamp, test_group))
                conn.commit()
                logger.info(f"Data saved successfully for sender {parsed_data.sender_device_id}, test group '{test_group}'.")
                self._update_average_rates()
        except Exception as e:
            logger.error(f"Error saving data to database: {e}", exc_info=True)
    
    def save_raw_log(self, payload: str):
        """Saves the raw MQTT payload to the log."""
        try:
            with self._get_connection() as conn:
                conn.cursor().execute("INSERT INTO raw_log (payload) VALUES (?)", (payload,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving raw log: {e}", exc_info=True)

    def get_all_test_groups(self):
        """Retrieves a list of all unique test group display names."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT test_group FROM average_reception_rates ORDER BY test_group")
                results = cursor.fetchall()
                return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Error getting test groups: {e}", exc_info=True)
            return []
        
    def get_all_data(self):
        """Retrieves all data from the device reception data table."""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM device_reception_data", conn)
                return df.to_dict(orient='records')
        except Exception as e:
            logger.error(f"Error retrieving all data: {e}", exc_info=True)
            return []
        
    def get_all_average_rates_data(self):
        """Retrieves all average reception rates data."""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM average_reception_rates", conn)
                return df.to_dict(orient='records')
        except Exception as e:
            logger.error(f"Error retrieving average rates data: {e}", exc_info=True)
            return []
        
    def get_all_raw_logs(self):
        """Retrieves all raw logs."""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query("SELECT * FROM raw_log", conn)
                return df.to_dict(orient='records')
        except Exception as e:
            logger.error(f"Error retrieving raw logs: {e}", exc_info=True)
            return []
        
    def get_or_create_display_name(self, app_test_id: str) -> str:
        """Gets or creates a human-readable display name for a given test ID."""
        with self._get_connection() as conn:
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

    def _update_average_rates(self):
        """Updates the average reception rates table."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''SELECT sender_device_id, receiver_device_id, AVG(reception_rate), test_group FROM device_reception_data GROUP BY sender_device_id, receiver_device_id, test_group''')
                results = cursor.fetchall()
                for row in results:
                    cursor.execute('''INSERT OR REPLACE INTO average_reception_rates (node_id, neighbor_id, average_reception_rate, test_group) VALUES (?, ?, ?, ?)''', row)
                conn.commit()
                logger.info(f"Average reception rates updated for {len(results)} combinations.")
        except Exception as e:
            logger.error(f"Error updating average rates: {e}", exc_info=True)

    def clear_all_data(self):
        """Clears all relevant data tables."""
        try:
            with self._get_connection() as conn:
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
        
    def delete_test_group_data(self, display_name: str):
        """Deletes all data associated with a specific test group display name."""
        try:
            with self._get_connection() as conn:
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
        
    def get_average_rates_as_dataframe(self):
        """Retrieves average reception rates as a pandas DataFrame."""
        try:
            with self._get_connection() as conn:
                df = pd.read_sql_query('''
                    SELECT 
                        node_id as "Node ID", 
                        neighbor_id as "Neighbor ID", 
                        average_reception_rate as "Average Reception Rate", 
                        test_group as "Test Group" 
                    FROM average_reception_rates 
                    ORDER BY "Test Group", CAST("Node ID" AS INTEGER), CAST("Neighbor ID" AS INTEGER)
                ''', conn)
                return df
        except Exception as e:
            logger.error(f"Error retrieving data as DataFrame: {e}", exc_info=True)
            return pd.DataFrame()
        
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