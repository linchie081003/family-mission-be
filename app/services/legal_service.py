from app.core.config import settings


PRIVACY_POLICY = """
# Kebijakan Privasi Family Mission

**Versi:** {version}

## 1. Data yang Kami Kumpulkan
- Data orang tua/wali: nama, email, password (terenkripsi)
- Data anak: nama, foto profil, aktivitas misi, poin, dan pencapaian
- Data keluarga: pengaturan poin, riwayat transaksi poin, redemption

## 2. Tujuan Pengumpulan
Platform gamifikasi keluarga untuk membangun kebiasaan baik anak, dengan persetujuan orang tua/wali.

## 3. Perlindungan Data Anak
Data anak hanya diproses dengan persetujuan orang tua/wali. **Data anak tidak akan digunakan dan disebarluaskan di media manapun** — termasuk media sosial, iklan, publikasi, atau platform pihak ketiga.

Apabila data anak terbukti tersebar karena kelalaian platform, operator **bersedia menutup aplikasi** dan **bertanggung jawab sepenuhnya** kepada pengguna yang terdampak.

## 4. Keamanan
Kami menerapkan enkripsi password, HTTPS, dan kontrol akses terbatas.

## 5. Hak Subjek Data
Anda berhak mengakses, memperbaiki, dan meminta penghapusan data. Hubungi: {contact}

## 6. Cookie & Sesi
Kami menggunakan token sesi JWT untuk autentikasi.

## 7. Hukum
Kebijakan ini tunduk pada UU Pelindungan Data Pribadi (UU PDP) Indonesia.
"""

TERMS_OF_SERVICE = """
# Syarat & Ketentuan Family Mission

**Versi:** {version}

## 1. Layanan
Family Mission adalah platform gamifikasi keluarga untuk misi, poin, dan reward.

## 2. Kewajiban Pengguna
Orang tua/wali bertanggung jawab penuh atas akun anak dan aktivitas di dalam keluarga.

## 3. Perlindungan Data Anak
Data anak tidak digunakan/disebarluaskan di media manapun. Pelanggaran → operator menutup aplikasi dan bertanggung jawab sepenuhnya.

## 4. Redemption Tunai
Mode saat ini: **{redemption_mode}**
{redemption_text}

## 5. Pembatasan
Platform tidak bertanggung jawab atas kesalahan input pengguna di luar kendali wajar sistem.

## 6. Penghentian
Platform berhak menangguhkan akun yang melanggar ketentuan.

## 7. Hukum
Syarat ini tunduk pada hukum Republik Indonesia.
"""


def _redemption_text() -> str:
    if settings.redemption_mode == "real":
        return (
            "Poin dapat dikonversi ke uang tunai nyata antar anggota keluarga. "
            "Platform hanya mencatat — transaksi uang riil adalah tanggung jawab orang tua. "
            "Family Mission bukan lembaga keuangan."
        )
    return (
        "Poin dan redemption bersifat simbolis/reward keluarga internal. "
        "Tidak ada transfer uang riil melalui platform."
    )


def get_privacy_document() -> dict:
    return {
        "version": settings.legal_doc_version,
        "title": "Kebijakan Privasi",
        "content": PRIVACY_POLICY.format(
            version=settings.legal_doc_version,
            contact=settings.platform_admin_email,
        ).strip(),
        "redemption_mode": settings.redemption_mode,
    }


def get_terms_document() -> dict:
    return {
        "version": settings.legal_doc_version,
        "title": "Syarat & Ketentuan",
        "content": TERMS_OF_SERVICE.format(
            version=settings.legal_doc_version,
            redemption_mode=settings.redemption_mode,
            redemption_text=_redemption_text(),
        ).strip(),
        "redemption_mode": settings.redemption_mode,
    }
