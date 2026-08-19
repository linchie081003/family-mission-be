LEVELS = [
    ("bronze", 0, "🥉"),
    ("silver", 500, "🥈"),
    ("gold", 1500, "🥇"),
    ("platinum", 3000, "💎"),
]

DEFAULT_BADGES = [
    ("first_mission", "Misi Pertama", "Selesaikan misi pertama", "🎯", 0),
    ("streak_7", "Streak 7 Hari", "Aktif 7 hari berturut-turut", "🔥", 0),
    ("streak_30", "Streak 30 Hari", "Aktif 30 hari berturut-turut", "⚡", 0),
    ("points_100", "Kolektor 100", "Kumpulkan 100 lifetime points", "⭐", 100),
    ("points_500", "Kolektor 500", "Kumpulkan 500 lifetime points", "🌟", 500),
    ("points_1000", "Kolektor 1000", "Kumpulkan 1000 lifetime points", "✨", 1000),
    ("points_3000", "Legenda", "Kumpulkan 3000 lifetime points", "👑", 3000),
]

DEFAULT_MISSIONS = [
    ("Bangun pagi tepat waktu", "regular", 5, "easy"),
    ("Merapikan tempat tidur", "regular", 3, "easy"),
    ("Mengerjakan PR", "regular", 10, "medium"),
    ("Membantu membersihkan rumah", "regular", 8, "medium"),
    ("Shalat 5 waktu", "ibadah", 0, "easy"),
    ("Membaca Al-Quran", "ibadah", 0, "medium"),
    ("Menghafal doa harian", "ibadah", 0, "easy"),
    ("Bantu adik tanpa diminta", "additional", 10, "medium"),
    ("Menjaga kejujuran", "additional", 15, "hard"),
]

DEFAULT_PUNISHMENTS = [
    ("Bohong", 10),
    ("Tidak patuh", 5),
    ("Berantem dengan adik", 8),
]

DEFAULT_REWARDS = [
    ("Extra screen time 30 menit", "Tambahan waktu layar 30 menit", 50),
    ("Jajan favorit", "Beli jajan pilihan sendiri", 100),
    ("Main di taman", "Jalan-jalan ke taman", 150),
]


def get_level(lifetime_points: int) -> str:
    level = "bronze"
    for name, threshold, _ in LEVELS:
        if lifetime_points >= threshold:
            level = name
    return level


def get_level_icon(level: str) -> str:
    for name, _, icon in LEVELS:
        if name == level:
            return icon
    return "🥉"


def get_level_progress(lifetime_points: int) -> tuple[str, str, float]:
    current = "bronze"
    next_level = "silver"
    current_threshold = 0
    next_threshold = 500

    for i, (name, threshold, _) in enumerate(LEVELS):
        if lifetime_points >= threshold:
            current = name
            if i + 1 < len(LEVELS):
                next_level = LEVELS[i + 1][0]
                current_threshold = threshold
                next_threshold = LEVELS[i + 1][1]
            else:
                return current, current, 1.0

    if next_threshold == current_threshold:
        return current, current, 1.0
    progress = (lifetime_points - current_threshold) / (next_threshold - current_threshold)
    return current, next_level, min(max(progress, 0), 1.0)
