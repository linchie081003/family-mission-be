# Migrasi Data: Firebase → PostgreSQL

Panduan memindahkan data dari aplikasi Family Mission lama (Firebase) ke versi baru.

## Langkah 1: Export dari Firebase

```powershell
cd "D:\Lesy\Personal\family project\family app\new\backend"
pip install firebase-admin
python migration/export_from_firebase.py
```

Hasil: `migration/exported_config.json` dan `migration/exported_logs.json`

## Langkah 2: Import ke PostgreSQL

Pastikan database jalan:

```powershell
cd "D:\Lesy\Personal\family project\family app\new"
docker compose up db -d
```

Jalankan import (akan diminta email & password parent baru):

```powershell
cd backend
python migration/import_to_postgres.py
```

Opsi non-interaktif:

```powershell
python migration/import_to_postgres.py `
  --family-name "Keluarga Wijaya" `
  --parent-name "Bapak" `
  --email "email@example.com" `
  --password "password123"
```

## Yang dipindahkan

| Data | Status |
|---|---|
| Profil anak (nama, warna, target, foto, goal) | Ya |
| Misi, punishment, reward | Ya |
| Riwayat misi, redeem, cashout | Ya |
| Riwayat perubahan aturan | Ya |
| PIN anak / PIN admin lama | Tidak |

## Setelah migrasi

1. Login parent dengan email + password yang dibuat
2. Cek dashboard, misi, dan laporan
3. Bagikan **Kode Keluarga** ke anak-anak
4. Anak login → buat PIN baru
5. Simpan file JSON export sebagai backup
6. Hapus `serviceAccountKey.json` dari komputer
