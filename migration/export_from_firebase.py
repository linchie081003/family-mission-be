"""
Export data Family Mission dari Firestore ke JSON lokal.

Prasyarat:
1. Buka https://console.firebase.google.com/project/family-mission-61cfd
2. Project Settings -> Service accounts -> Generate new private key
3. Simpan file unduhan sebagai migration/serviceAccountKey.json

Jalankan dari folder new/backend:

  pip install firebase-admin
  python migration/export_from_firebase.py

Output:
  migration/exported_config.json
  migration/exported_logs.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    print("Library 'firebase-admin' belum terpasang. Jalankan dulu:")
    print("  pip install firebase-admin")
    sys.exit(1)

MIGRATION_DIR = Path(__file__).resolve().parent
KEY_FILE = MIGRATION_DIR / "serviceAccountKey.json"
OUT_CONFIG = MIGRATION_DIR / "exported_config.json"
OUT_LOGS = MIGRATION_DIR / "exported_logs.json"

COLLECTION = "familyMission"
CONFIG_DOC = "config"
LOGS_DOC = "logs"


def main() -> None:
    if not KEY_FILE.exists():
        print(f"File {KEY_FILE.name} tidak ditemukan di {MIGRATION_DIR}")
        print()
        print("Cara mendapatkannya:")
        print("  1. Firebase Console -> family-mission-61cfd -> Project Settings")
        print("  2. Tab Service accounts -> Generate new private key")
        print(f"  3. Simpan sebagai {KEY_FILE}")
        sys.exit(1)

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(KEY_FILE))
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    print(f"Mengambil {COLLECTION}/{CONFIG_DOC}...")
    config_snapshot = db.collection(COLLECTION).document(CONFIG_DOC).get()
    if not config_snapshot.exists:
        print("  Dokumen config tidak ditemukan.")
        print("  Pastikan project Firebase benar (family-mission-61cfd).")
        sys.exit(1)
    config_data = config_snapshot.to_dict() or {}

    print(f"Mengambil {COLLECTION}/{LOGS_DOC}...")
    logs_snapshot = db.collection(COLLECTION).document(LOGS_DOC).get()
    logs_data = logs_snapshot.to_dict() if logs_snapshot.exists else {"items": []}
    if logs_data is None:
        logs_data = {"items": []}

    OUT_CONFIG.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    OUT_LOGS.write_text(
        json.dumps(logs_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    log_items = logs_data.get("items") or []
    print()
    print("Export selesai!")
    print(f"  {OUT_CONFIG.name}")
    print(f"    - {len(config_data.get('children', []))} anak")
    print(f"    - {len(config_data.get('missions', []))} misi")
    print(f"    - {len(config_data.get('punishments', []))} punishment")
    print(f"    - {len(config_data.get('rewards', []))} reward")
    print(f"    - {len(config_data.get('ruleHistory', []))} riwayat aturan")
    print(f"  {OUT_LOGS.name}")
    print(f"    - {len(log_items)} baris riwayat poin")
    print()
    print("Simpan kedua file JSON sebagai cadangan.")
    print("Langkah berikutnya: python migration/import_to_postgres.py")


if __name__ == "__main__":
    main()
