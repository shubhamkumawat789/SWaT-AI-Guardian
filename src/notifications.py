import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# --- SAHI PATH SETTING ---
# Ye line automatic pata lagayegi ki .env kahan hai
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationManager:
    """Manages email alerts for the SWaT System"""

    def __init__(self):
        self.receiver_email = os.getenv("ALERT_RECEIVER_EMAIL")
        self.sender_email = os.getenv("ALERT_SENDER_EMAIL")
        self.sender_password = os.getenv("ALERT_SENDER_PASS")
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        
        # Cooldown management
        self.last_sent_time = None
        self.cooldown_seconds = 300  # 5 Minutes

    def send_email(self, alert_data, ignore_cooldown=False):
        """Sends an email alert if credentials exist"""
        
        if not self.sender_email or not self.sender_password:
            logger.warning("❌ Credentials Missing in .env file!")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = f"SWaT AI Guardian <{self.sender_email}>"
            msg['To'] = self.receiver_email
            msg['Subject'] = f"🚨 SECURITY ALERT: {alert_data.get('Type', 'ALERT')} Detected!"

            body = f"""
            <h3>SWaT AI Guardian Security Alert</h3>
            <p>An anomaly has been detected in the Water Treatment System.</p>
            <ul>
                <li><b>Time:</b> {alert_data.get('Time')}</li>
                <li><b>Type:</b> {alert_data.get('Type')}</li>
                <li><b>Anomaly Score:</b> {alert_data.get('Score')}</li>
                <li><b>Data Label:</b> {alert_data.get('Label')}</li>
            </ul>
            <p>Please check the dashboard immediately.</p>
            """
            msg.attach(MIMEText(body, 'html'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"✅ Email alert sent to {self.receiver_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Email Error: {e}")
            return False