import paho.mqtt.client as mqtt
import os
import logging

logger = logging.getLogger(__name__)

class MQTTClient:
    def __init__(self, mqtt_host="localhost", mqtt_port=1883,
                 mqtt_username="root", mqtt_password="password",
                 topics: list = None, on_message_callback=None):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.topics = topics if topics is not None else []
        self.on_message_callback = on_message_callback
        
        self.client = mqtt.Client(client_id=f"backend-processor-{os.getpid()}")
        self.client.username_pw_set(self.mqtt_username, self.mqtt_password)
        self.client.on_connect = self._on_mqtt_connect
        self.client.on_message = self._on_mqtt_message

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT on_connect callback."""
        if rc == 0:
            logger.info("MQTT connection successful.")

            if not self.topics:
                logger.warning("No topics provided to subscribe to.")
                return
            
            for topic in self.topics:
                client.subscribe(topic)
                logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"MQTT connection failed with code: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """MQTT on_message callback."""
        try:
            payload = msg.payload.decode('utf-8')

            if self.on_message_callback:
                self.on_message_callback(msg.topic, payload)
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}", exc_info=True)
    
    def start(self):
        """Starts the MQTT processor."""
        self.running = True
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_forever()

    def stop(self):
        """Stops the MQTT processor."""
        self.running = False
        if self.client.is_connected():
            self.client.disconnect()
        logger.info("MQTT processor stopped.")