"""
Smart Attendance System — Python Middleware (Appwrite Edition)
Reads RFID UIDs from Arduino via Serial, processes them, and logs to Appwrite.

Features:
- Real-time attendance logging
- Student lookup by RFID UID
- Clone detection & logging
- Error handling & logging
- Debounce protection
- Card cloning support

Requirements:
    pip install -r requirements.txt

Setup:
    1. Create .env file with Appwrite credentials
    2. Connect Arduino via USB
    3. Run: python middleware_appwrite.py
"""

import serial
import time
import sys
import logging
import os
from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID
from datetime import datetime, timezone

# ─── LOAD ENVIRONMENT VARIABLES ──────────────────────────────────
load_dotenv()

APPWRITE_ENDPOINT = os.getenv("APPWRITE_ENDPOINT")
APPWRITE_PROJECT = os.getenv("APPWRITE_PROJECT_ID")
APPWRITE_API_KEY = os.getenv("APPWRITE_API_KEY")
APPWRITE_DATABASE = os.getenv("APPWRITE_DATABASE_ID")

SERIAL_PORT = os.getenv("SERIAL_PORT", "COM3")
BAUD_RATE = int(os.getenv("BAUD_RATE", "9600"))
DEBOUNCE_SEC = int(os.getenv("DEBOUNCE_SEC", "60"))
CLONE_DETECTION_SEC = int(os.getenv("CLONE_DETECTION_SEC", "10"))

# ─── LOGGING SETUP ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("attendance.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


class AppwriteMiddleware:
    """Handles all Appwrite database operations."""
    
    def __init__(self):
        """Initialize Appwrite client."""
        try:
            self.client = Client()
            self.client.set_endpoint(APPWRITE_ENDPOINT)
            self.client.set_project(APPWRITE_PROJECT)
            self.client.set_key(APPWRITE_API_KEY)
            
            self.databases = Databases(self.client)
            log.info("✅ Appwrite initialized successfully")
        except Exception as e:
            log.error(f"❌ Failed to initialize Appwrite: {e}")
            sys.exit(1)
    
    def lookup_student(self, uid: str) -> dict | None:
        """
        Look up a student by RFID UID.
        
        Args:
            uid: RFID card UID (uppercase string)
            
        Returns:
            Student document or None if not found
        """
        try:
            result = self.databases.list_documents(
                database_id=APPWRITE_DATABASE,
                collection_id="students",
                queries=[Query.equal("rfid_uid", uid)]
            )
            
            if result.get("documents") and len(result["documents"]) > 0:
                student = result["documents"][0]
                log.debug(f"✓ Found student: {student.get('name')}")
                return student
            
            log.warning(f"⚠️  No student found with UID: {uid}")
            return None
            
        except Exception as e:
            log.error(f"❌ Database lookup error: {e}")
            return None
    
    def log_attendance(self, uid: str, student: dict | None, is_clone: bool = False) -> str:
        """
        Log an attendance record to the database.
        
        Args:
            uid: RFID card UID
            student: Student document (or None if unknown)
            is_clone: Whether this is a suspected clone scan
            
        Returns:
            Document ID of created record
        """
        try:
            now = datetime.now(timezone.utc)
            
            record = {
                "rfid_uid": uid,
                "timestamp": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "status": "present",
                "valid": student is not None,
                "is_clone_suspected": is_clone,
            }
            
            if student:
                record["student_id"] = student.get("$id")
                record["student_name"] = student.get("name", "Unknown")
                record["class_id"] = student.get("class_id", "")
            else:
                record["student_name"] = "Unknown"
            
            doc = self.databases.create_document(
                database_id=APPWRITE_DATABASE,
                collection_id="attendance_logs",
                document_id=ID.unique(),
                data=record
            )
            
            if is_clone:
                log.warning(f"🚨 POSSIBLE CLONE: {uid} (student: {record['student_name']})")
            else:
                log.info(f"✅ Attendance logged: {record['student_name']} ({uid})")
            
            return doc.get("$id")
            
        except Exception as e:
            log.error(f"❌ Failed to log attendance: {e}")
            return None
    
    def log_clone_operation(self, original_uid: str, cloned_uid: str, success: bool = True) -> str:
        """
        Log a card cloning operation.
        
        Args:
            original_uid: Source card UID
            cloned_uid: Target card UID (now contains source data)
            success: Whether cloning was successful
            
        Returns:
            Document ID of clone record
        """
        try:
            record = {
                "original_uid": original_uid,
                "cloned_uid": cloned_uid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success" if success else "failed",
                "operation_type": "clone_write",
                "notes": "Card successfully cloned" if success else "Clone operation failed"
            }
            
            doc = self.databases.create_document(
                database_id=APPWRITE_DATABASE,
                collection_id="rfid_clone_records",
                document_id=ID.unique(),
                data=record
            )
            
            log.warning(f"🔐 CLONE OPERATION: {original_uid} → {cloned_uid}")
            return doc.get("$id")
            
        except Exception as e:
            log.error(f"❌ Failed to log clone: {e}")
            return None
    
    def check_clone_fraud(self, uid: str) -> bool:
        """
        Detect if this UID appears to be a clone (rapid rescan).
        
        Args:
            uid: RFID card UID to check
            
        Returns:
            True if suspicious (likely clone), False otherwise
        """
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            result = self.databases.list_documents(
                database_id=APPWRITE_DATABASE,
                collection_id="attendance_logs",
                queries=[
                    Query.equal("rfid_uid", uid),
                    Query.equal("date", today),
                    Query.order_desc("timestamp"),
                    Query.limit(2)
                ]
            )
            
            docs = result.get("documents", [])
            if len(docs) >= 2:
                time1 = datetime.fromisoformat(docs[0]["timestamp"].replace("Z", "+00:00"))
                time2 = datetime.fromisoformat(docs[1]["timestamp"].replace("Z", "+00:00"))
                
                time_diff = (time1 - time2).total_seconds()
                
                if time_diff < CLONE_DETECTION_SEC:
                    log.warning(f"⚠️  CLONE ALERT: {uid} scanned {time_diff:.1f}s apart!")
                    return True
            
            return False
            
        except Exception as e:
            log.debug(f"Clone check error: {e}")
            return False


class SerialReader:
    """Handles Arduino serial communication."""
    
    def __init__(self, port: str, baud: int):
        """
        Initialize serial connection to Arduino.
        
        Args:
            port: Serial port (e.g., "COM3", "/dev/ttyUSB0")
            baud: Baud rate (9600)
        """
        try:
            self.ser = serial.Serial(port, baud, timeout=2)
            time.sleep(2)
            log.info(f"✅ Serial port {port} opened at {baud} baud")
        except serial.SerialException as e:
            log.error(f"❌ Cannot open serial port {port}: {e}")
            log.error("Run: python -m serial.tools.list_ports")
            sys.exit(1)
    
    def read_uid(self) -> str | None:
        """
        Read one UID from the serial port.
        
        Returns:
            UID string (uppercase) or None if no data
        """
        try:
            if self.ser.in_waiting > 0:
                line = self.ser.readline()
                uid = line.decode("utf-8", errors="ignore").strip().upper()
                
                if uid and uid != "READY":
                    return uid
        except Exception as e:
            log.error(f"Serial read error: {e}")
        
        return None
    
    def close(self):
        """Close the serial connection."""
        self.ser.close()
        log.info("Serial port closed")


class AttendanceProcessor:
    """Main processor that ties everything together."""
    
    def __init__(self):
        """Initialize the processor."""
        self.appwrite = AppwriteMiddleware()
        self.serial_reader = SerialReader(SERIAL_PORT, BAUD_RATE)
        self.last_scan_time = {}
    
    def run(self):
        """Main loop - read from Arduino and process."""
        log.info("="*60)
        log.info("🎯 Attendance + Cloning System Started")
        log.info(f"Listening on {SERIAL_PORT} at {BAUD_RATE} baud")
        log.info(f"Debounce: {DEBOUNCE_SEC}s, Clone detection: {CLONE_DETECTION_SEC}s")
        log.info("="*60)
        log.info("Waiting for RFID scans... (Press Ctrl+C to stop)")
        
        try:
            while True:
                uid = self.serial_reader.read_uid()
                if not uid:
                    continue
                
                # ─── HANDLE CLONE OPERATIONS ──────────────────────
                if uid.startswith("[CLONE_OP]"):
                    parts = uid.split(" -> ")
                    if len(parts) == 2:
                        original = parts[0].replace("[CLONE_OP] ", "")
                        cloned = parts[1]
                        
                        log.warning(f"🔐 Clone detected from Arduino!")
                        log.warning(f"   Source: {original}")
                        log.warning(f"   Clone:  {cloned}")
                        
                        self.appwrite.log_clone_operation(original, cloned, success=True)
                        continue
                
                # ─── HANDLE NORMAL ATTENDANCE ─────────────────────
                log.info(f"📱 Card scanned: {uid}")
                
                now = datetime.now(timezone.utc)
                
                # Debounce check
                if uid in self.last_scan_time:
                    elapsed = (now - self.last_scan_time[uid]).total_seconds()
                    
                    if elapsed < DEBOUNCE_SEC:
                        log.debug(f"⏭️  Debounced {uid} ({elapsed:.1f}s ago)")
                        continue
                
                self.last_scan_time[uid] = now
                
                # Clone detection (rapid rescan)
                is_clone = self.appwrite.check_clone_fraud(uid)
                
                if is_clone:
                    self.appwrite.log_clone_operation(uid, uid, success=True)
                
                # Student lookup
                student = self.appwrite.lookup_student(uid)
                
                # Log attendance
                self.appwrite.log_attendance(uid, student, is_clone=is_clone)
                
                # Display summary
                if student:
                    print(f"✅ {student.get('name')} - Present")
                else:
                    print(f"⚠️  Unknown UID: {uid}")
                
                if is_clone:
                    print(f"🚨 WARNING: Possible clone detected!")
                
                print()
        
        except KeyboardInterrupt:
            log.info("\n⏹️  Stopped by user (Ctrl+C)")
        except Exception as e:
            log.error(f"❌ Fatal error: {e}")
        finally:
            self.serial_reader.close()
            log.info("Middleware shutdown complete")


def main():
    """Entry point."""
    processor = AttendanceProcessor()
    processor.run()


if __name__ == "__main__":
    main()
