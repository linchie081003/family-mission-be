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

## Langkah 3: Sync ke Supabase (opsional)

Jika data sudah di PostgreSQL lokal dan ingin dipindah ke Supabase:

```powershell
# 1. Buat migration/.env.supabase dari .env.supabase.example
# 2. Isi TARGET_DATABASE_URL (URI Supabase Session pooler)

python migration/sync_local_to_supabase.py `
  --family-email parent@keluarga-mission.id `
  --init-target `
  --replace
```

Opsi `--init-target` membuat schema + seed plan di Supabase (jika belum pernah deploy backend).
Opsi `--replace` menimpa keluarga dengan email yang sama di Supabase.

Alternatif cepat (tanpa sync dari lokal): jalankan ulang import langsung ke Supabase:

```powershell
$env:DATABASE_URL="postgresql+asyncpg://...@...supabase.com:6543/postgres"
python migration/import_to_postgres.py --email ... --password ...
```
