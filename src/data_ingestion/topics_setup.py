from kafka.admin import KafkaAdminClient, NewTopic
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import get_kafka_config

def setup_topics():
    config = get_kafka_config()
    bootstrap = config.get_bootstrap_servers()
    
    print(f"[*] Connecting to Kafka at {bootstrap}...")
    
    import time
    retries = 5
    admin = None
    for i in range(retries):
        try:
            admin = KafkaAdminClient(bootstrap_servers=bootstrap, client_id='swat-admin', request_timeout_ms=5000)
            print(" Connected to Kafka Admin.")
            break
        except Exception as e:
            if i < retries - 1:
                print(f"    [!] Broker not ready (attempt {i+1}/{retries}). Retrying in 5s...")
                time.sleep(5)
            else:
                print(f"  Failed to connect to Kafka: {e}")
                return

    if not admin: return
    
    topics = [
        NewTopic(name=config.get_topic("sensor_data"), num_partitions=1, replication_factor=1),
        NewTopic(name=config.get_topic("anomalies"), num_partitions=1, replication_factor=1),
        NewTopic(name=config.get_topic("alerts"), num_partitions=1, replication_factor=1),
        NewTopic(name="swat-processed-features", num_partitions=1, replication_factor=1)
    ]
    
    print("[*] Creating Topics...")
    existing = admin.list_topics()
    
    for t in topics:
        if t.name not in existing:
            try:
                admin.create_topics([t])
                print(f"    Topic '{t.name}' created.")
            except Exception as e:
                print(f"    Error creating {t.name}: {e}")
        else:
            print(f"    Topic '{t.name}' exists.")

if __name__ == "__main__":
    setup_topics()
