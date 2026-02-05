"""
SWaT System Utilities
General purpose utility functions and classes
"""
import yaml
import os
import logging
from typing import Dict, Any

import json
from datetime import datetime

# Configure logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_structured_logging(level=logging.INFO):
    """Setup JSON logging for the entire system"""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)
    
    # Also log to file
    os.makedirs('logs', exist_ok=True)
    file_handler = logging.FileHandler('logs/system.log')
    file_handler.setFormatter(JsonFormatter())
    root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

class KafkaConfigLoader:
    """Load and manage Kafka configuration"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize configuration loader
        
        Args:
            config_path: Path to kafka_config.yaml file
        """
        if config_path is None:
            # Look for config directory in the parent of src/
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(os.path.dirname(base_dir), 'config', 'kafka_config.yaml')
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            logger.warning(f"Kafka config file not found: {self.config_path}. Using defaults.")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing Kafka config: {e}")
            return {}
    
    @property
    def bootstrap_servers(self) -> str:
        """Get Kafka bootstrap servers as a property"""
        return self.get_bootstrap_servers()

    def get_bootstrap_servers(self) -> str:
        """Get Kafka bootstrap servers"""
        # Prioritize environment variable (Docker), then config file, then localhost
        return os.environ.get('KAFKA_BOOTSTRAP_SERVERS', self.config.get('bootstrap_servers', 'localhost:9092'))
    
    def get_topic(self, topic_key: str) -> str:
        topics = self.config.get('topics', {})
        defaults = {
            'sensor_data': 'swat-sensor-data',
            'anomalies': 'swat-anomalies',
            'alerts': 'swat-alerts',
            'processed_features': 'swat-processed-features'
        }
        return topics.get(topic_key, defaults.get(topic_key, f"swat-{topic_key}"))
    
    def get_producer_config(self) -> Dict[str, Any]:
        """Get producer configuration"""
        producer_config = self.config.get('producer', {})
        return {
            'bootstrap_servers': self.get_bootstrap_servers(),
            'acks': producer_config.get('acks', 'all'),
            'compression_type': producer_config.get('compression_type', 'gzip'),
            'batch_size': producer_config.get('batch_size', 16384),
            'linger_ms': producer_config.get('linger_ms', 10),
            'max_in_flight_requests_per_connection': producer_config.get('max_in_flight_requests_per_connection', 5),
            'retries': producer_config.get('retries', 3),
        }
    
    def get_consumer_config(self) -> Dict[str, Any]:
        """Get consumer configuration"""
        consumer_config = self.config.get('consumer', {})
        return {
            'bootstrap_servers': self.get_bootstrap_servers(),
            'group_id': consumer_config.get('group_id', 'swat-consumer-group'),
            'auto_offset_reset': consumer_config.get('auto_offset_reset', 'earliest'),
            'enable_auto_commit': consumer_config.get('enable_auto_commit', True),
            'auto_commit_interval_ms': consumer_config.get('auto_commit_interval_ms', 5000),
            'max_poll_records': consumer_config.get('max_poll_records', 500),
            'session_timeout_ms': consumer_config.get('session_timeout_ms', 30000),
            'heartbeat_interval_ms': consumer_config.get('heartbeat_interval_ms', 10000),
        }
    
    def get_topic_config(self) -> Dict[str, Any]:
        """Get topic configuration for creation"""
        topic_config = self.config.get('topic_config', {})
        return {
            'num_partitions': topic_config.get('num_partitions', 3),
            'replication_factor': topic_config.get('replication_factor', 1),
        }

# Singleton instance
_config_loader = None

def get_kafka_config() -> KafkaConfigLoader:
    """Get singleton Kafka configuration loader"""
    global _config_loader
    if _config_loader is None:
        _config_loader = KafkaConfigLoader()
    return _config_loader

def get_system_state() -> Dict[str, Any]:
    """Get the full global system state (mode, speed, run status)."""
    status_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "system_state.json")
    default_state = {
        "run_system": True,
        "simulation_speed": 1.0,
        "data_mode": "Normal",
        "last_updated": datetime.now().isoformat()
    }
    try:
        if os.path.exists(status_file):
            with open(status_file, 'r') as f:
                data = json.load(f)
                # Merge with defaults to handle missing keys
                return {**default_state, **data}
    except:
        pass
    return default_state

def get_system_status() -> bool:
    """Check if the system is globally set to RUN or STOP."""
    return get_system_state().get("run_system", True)

def set_system_status(run: bool = None, speed: float = None, mode: str = None):
    """Set the global system state. None values will preserve existing state."""
    status_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "system_state.json")
    os.makedirs(os.path.dirname(status_file), exist_ok=True)
    
    current_state = get_system_state()
    
    new_state = {
        "run_system": run if run is not None else current_state["run_system"],
        "simulation_speed": speed if speed is not None else current_state["simulation_speed"],
        "data_mode": mode if mode is not None else current_state["data_mode"],
        "last_updated": datetime.now().isoformat()
    }
    
    try:
        with open(status_file, 'w') as f:
            json.dump(new_state, f)
    except Exception as e:
        logger.error(f"Failed to set system state: {e}")
