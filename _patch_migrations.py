from pathlib import Path

p = Path(__file__).with_name("app/core/migrations.py")
text = p.read_text(encoding="utf-8")
old = (
    '        "ALTER TABLE children ALTER COLUMN avatar_url TYPE TEXT",\n'
    '        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100)",'
)
new = (
    '        "ALTER TABLE children ALTER COLUMN avatar_url TYPE TEXT",\n'
    '        """\n'
    "        UPDATE children\n"
    "        SET avatar_url = NULL\n"
    "        WHERE avatar_url LIKE '/uploads/%'\n"
    '        """,\n'
    '        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100)",'
)
if old not in text:
    raise SystemExit("pattern not found")
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched")
