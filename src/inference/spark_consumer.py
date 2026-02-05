import os
import sys
import json
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, struct, udf, window, timestamp_seconds, to_json
from pyspark.sql.types import StructType, StructField, DoubleType, StringType

# System paths for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import get_kafka_config
from inference.streaming_inference import AnomalyDetector

def create_spark_engine():
    # Phase 3: Spark Structured Streaming setup
    # Get the project root (the directory containing 'src')
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    src_dir = os.path.join(base_dir, "src")
    
    spark = SparkSession.builder \
        .appName("SWaT_Spark_AI_Engine") \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.executorEnv.PYTHONPATH", src_dir) \
        .getOrCreate()
    
    # Also add files to context to be sure
    spark.sparkContext.addPyFile(os.path.join(src_dir, "utils.py"))
    # We can't easily add a whole directory without zipping, but setting PYTHONPATH usually suffices for local runs
    
    spark.sparkContext.setLogLevel("ERROR")
    return spark

# 1. Load Schema from model_columns.json
base_dir = os.path.dirname(os.path.abspath(__file__))
columns_path = os.path.abspath(os.path.join(base_dir, "..", "..", "models", "model_columns.json"))

with open(columns_path, 'r') as f:
    sensor_cols = json.load(f)

# Kafka input schema matching kafka_producer.py
schema = StructType([
    StructField("timestamp", DoubleType()),
    StructField("record_id", DoubleType())
] + [StructField(c, DoubleType()) for c in sensor_cols])

# 2. Global variable for lazy initialization on executors
_detector = None

def get_detector():
    global _detector
    if _detector is None:
        # In Spark workers, we might need to ensure the path is set
        import sys
        import os
        # Add the parent of 'inference' to path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.append(current_dir)
        
        from inference.streaming_inference import AnomalyDetector
        _detector = AnomalyDetector()
    return _detector

# UDF for Ensemble Prediction
def detect_anomaly_udf(sensor_data_json):
    try:
        detector = get_detector()
        data_dict = json.loads(sensor_data_json)
        # Convert to pandas for the existing preprocessor logic
        df_row = pd.DataFrame([data_dict])
        
        # Standardize and Predict using Ensemble Logic
        scaled = detector.preprocess(data_dict) # Pass dict, preprocess handles buffer
        res = detector.predict(scaled) 
        dist = res["mse"]
        is_dl = res["is_anomaly"]
        is_iso = res["is_iso"]
        
        return json.dumps({
            "timestamp": data_dict.get("timestamp"),
            "score": float(dist),
            "dl_anomaly": bool(is_dl),
            "iso_anomaly": bool(is_iso),
            "record_id": data_dict.get("record_id")
        })
    except Exception as e:
        import traceback
        return json.dumps({"status": "ERROR", "message": str(e), "trace": traceback.format_exc()})

predict_call = udf(detect_anomaly_udf, StringType())

def main():
    spark = create_spark_engine()
    kafka_cfg = get_kafka_config()
    
    # 3. Read Stream from Kafka (Windows Broker)
    # WSL connects to Windows via localhost:9092 or Windows LAN IP
    raw_stream = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_cfg.get_bootstrap_servers()) \
        .option("subscribe", kafka_cfg.get_topic("sensor_data")) \
        .option("startingOffsets", "latest") \
        .load()

    # 4. Parse JSON & Feature Engineering (Migration to PySpark)
    parsed_df = raw_stream.selectExpr("CAST(value AS STRING) as json_payload") \
        .select(from_json(col("json_payload"), schema).alias("data")) \
        .select("data.*") \
        .withColumn("event_time", timestamp_seconds(col("timestamp")))

    # 5. Window-based Aggregations (Event-time processing)
    # Windowing logic for rolling feature engineering
    windowed_df = parsed_df \
        .withWatermark("event_time", "10 seconds") \
        .groupBy(window(col("event_time"), "60 seconds", "10 seconds")) \
        .agg({"FIT101": "avg", "LIT101": "max"}) # Example aggregations

    # 6. Inference via Distributed UDF
    # Pass the full record struct to the UDF
    inference_df = parsed_df.withColumn(
        "inference_results", 
        predict_call(to_json(struct([col(c) for c in parsed_df.columns])))
    )

    # 7. Sink Results back to Kafka 'alerts' topic
    query = inference_df.select(col("inference_results").alias("value")) \
        .writeStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_cfg.get_bootstrap_servers()) \
        .option("topic", kafka_cfg.get_topic("alerts")) \
        .option("checkpointLocation", "/tmp/spark_checkpoints") \
        .start()

    print("[*] Spark Structured Streaming Engine is Running on WSL...")
    query.awaitTermination()

if __name__ == "__main__":
    main()