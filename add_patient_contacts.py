import os
import firebase_admin
from firebase_admin import credentials, db

# Setup credentials
cred_path = os.getenv("FIREBASE_CRED_PATH", "firebase_credentials.json")
cred = credentials.Certificate(cred_path)
db_url = os.getenv(
    "FIREBASE_DB_URL",
    "https://cardioguard-ai-v2-default-rtdb.asia-southeast1.firebasedatabase.app"
)
firebase_admin.initialize_app(cred, {
    "databaseURL": db_url
})

# REPLACE WITH YOUR ACTUAL TELEGRAM CHAT ID OR SET TELEGRAM_CHAT_ID ENV VAR
# You can use the same Chat ID for multiple roles during testing.
MY_TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

patients_data = {
    "patient_001": {
        "name": "Patient 001",
        "contacts": {
            "doctor": MY_TELEGRAM_CHAT_ID,
            "family": MY_TELEGRAM_CHAT_ID
        }
    },
    "patient_002": {
        "name": "Patient 002",
        "contacts": {
            "doctor": MY_TELEGRAM_CHAT_ID
        }
    },
    "patient_003": {
        "name": "Patient 003 (Demo)",
        "contacts": {
            "doctor": MY_TELEGRAM_CHAT_ID
        }
    }
}

# Write to Firebase Realtime Database
db.reference("patients").set(patients_data)
print("Patients list and Telegram contacts populated successfully!")
