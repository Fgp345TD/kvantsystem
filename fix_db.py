import sqlite3

conn = sqlite3.connect('quiz.db')
c = conn.cursor()

# Создаём таблицу users с ВСЕМИ полями
c.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'ученик',
    theme TEXT DEFAULT 'dark',
    age INTEGER,
    birth_date TEXT,
    phone TEXT,
    email TEXT,
    requested_role TEXT
)''')

# Остальные таблицы
c.execute('''CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    creator_id INTEGER NOT NULL,
    max_attempts INTEGER DEFAULT 1,
    FOREIGN KEY (creator_id) REFERENCES users (id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    FOREIGN KEY (test_id) REFERENCES tests (id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    is_correct BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (question_id) REFERENCES questions (id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    FOREIGN KEY (test_id) REFERENCES tests (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
)''')

# Добавляем админа ТОЛЬКО если его нет
c.execute("SELECT 1 FROM users WHERE username = 'admin'")
if not c.fetchone():
    c.execute("INSERT INTO users (username, password, role) VALUES ('admin', '5682', 'администратор')")

conn.commit()
conn.close()
print("✅ База создана. Теперь запустите app.py")