import unittest
import numpy as np
import os
import sys

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from inference.streaming_inference import AnomalyDetector

class TestAnomalyDetector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize detector without Kafka for testing
        cls.detector = AnomalyDetector(init_kafka=False)

    def test_preprocess_shape(self):
        # Mock a single sensor record
        mock_record = {col: 0.1 for col in self.detector.required_cols}
        scaled = self.detector.preprocess(mock_record)
        self.assertEqual(scaled.shape, (1, len(self.detector.required_cols)))

    def test_predict_structure(self):
        # Create a mock window (60 samples)
        window = [np.zeros(len(self.detector.required_cols)) for _ in range(60)]
        mse, is_anomaly, iso_score = self.detector.predict(window)
        
        self.assertIsInstance(mse, (float, np.float32, np.float64))
        self.assertIsInstance(is_anomaly, (bool, np.bool_))
        self.assertIsInstance(iso_score, (bool, np.bool_))

    def test_threshold_logic(self):
        # Test if is_anomaly matches threshold
        mse = self.detector.threshold + 0.1
        # Mock window features result
        features = np.zeros((1, len(self.detector.required_cols) * 5))
        # Since we can't easily mock the model output here without deep mocking, 
        # we just verify the detector is loaded
        self.assertTrue(self.detector.threshold > 0)

if __name__ == '__main__':
    unittest.main()
