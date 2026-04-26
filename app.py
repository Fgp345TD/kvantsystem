from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key'


def init_db():
    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    # Проверяем столбцы
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]

    # Создаём таблицы
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'ученик',
        theme TEXT DEFAULT 'dark'
    )''')

    if 'age' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN age INTEGER")
    if 'birth_date' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN birth_date TEXT")
    if 'phone' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if 'email' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")

    if 'requested_role' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN requested_role TEXT")

    c.execute('''CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        creator_id INTEGER NOT NULL,
        max_attempts INTEGER DEFAULT 1,
        is_public BOOLEAN DEFAULT 1,
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

    c.execute('''CREATE TABLE IF NOT EXISTS user_test_attempts_override (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        test_id INTEGER NOT NULL,
        extra_attempts INTEGER DEFAULT 0,
        UNIQUE(user_id, test_id)
    )''')

    # Новая таблица: сохранение ответов пользователя
    c.execute('''CREATE TABLE IF NOT EXISTS user_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        result_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        answer_id INTEGER,
        FOREIGN KEY (result_id) REFERENCES test_results (id),
        FOREIGN KEY (question_id) REFERENCES questions (id),
        FOREIGN KEY (answer_id) REFERENCES answers (id)
    )''')

    # Создаём админа
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, role) VALUES ('admin', '258456', 'администратор')")

    conn.commit()
    conn.close()


def get_user_theme():
    if 'user_id' in session:
        conn = sqlite3.connect('quiz.db')
        c = conn.cursor()
        c.execute("SELECT theme FROM users WHERE id = ?", (session['user_id'],))
        result = c.fetchone()
        conn.close()
        if result:
            return result[0]
    return 'dark'


def has_permission(required_role):
    if 'user_id' not in session:
        return False
    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],))
    user_role = c.fetchone()
    conn.close()
    if not user_role:
        return False
    role = user_role[0]
    if required_role == 'ученик':
        return True
    elif required_role == 'учитель':
        return role in ['учитель', 'модератор', 'администратор']
    elif required_role == 'модератор':
        return role in ['модератор', 'администратор']
    elif required_role == 'администратор':
        return role == 'администратор'
    return False


# === РЕЖИМЫ РАБОТЫ СЕРВЕРА ===
MAINTENANCE_FILE = 'maintenance_mode.txt'

def get_maintenance_mode():
    try:
        with open(MAINTENANCE_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        with open(MAINTENANCE_FILE, 'w') as f:
            f.write('none')
        return 'none'

def set_maintenance_mode(mode):
    with open(MAINTENANCE_FILE, 'w') as f:
        f.write(mode)

@app.context_processor
def inject_maintenance():
    return {'maintenance_mode': get_maintenance_mode()}

@app.before_request
def check_maintenance():
    mode = get_maintenance_mode()
    if mode in ['isolate', 'maintenance'] and request.endpoint not in ['login', 'register', 'logout', 'static']:
        if 'user_id' not in session:
            return render_template('maintenance.html', mode=mode)
        else:
            conn = sqlite3.connect('quiz.db')
            c = conn.cursor()
            c.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],))
            user_role = c.fetchone()
            conn.close()
            if user_role and user_role[0] != 'администратор':
                return render_template('maintenance.html', mode=mode)


# === МАРШРУТЫ ===

@app.route('/')
def index():
    theme = get_user_theme()
    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("""
        SELECT t.id, t.name, t.description, u.username, t.max_attempts, t.is_public, COUNT(q.id) as q_count
        FROM tests t
        JOIN users u ON t.creator_id = u.id
        LEFT JOIN questions q ON t.id = q.test_id
        WHERE t.is_public = 1
        GROUP BY t.id, t.name, t.description, u.username, t.max_attempts, t.is_public
        ORDER BY t.id DESC
    """)
    tests = c.fetchall()
    conn.close()
    return render_template('index.html', tests=tests, theme=theme)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('quiz.db')
        c = conn.cursor()
        c.execute("SELECT id, username, role FROM users WHERE username = ? AND password = ?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[2]
            flash('Вы успешно вошли!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'error')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = 'ученик'
        conn = sqlite3.connect('quiz.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
            conn.commit()
            flash('Регистрация успешна!', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Пользователь с таким именем уже существует', 'error')
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


@app.route('/create_test', methods=['GET', 'POST'])
def create_test():
    if not has_permission('учитель'):
        flash('У вас нет прав для создания тестов', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        max_attempts = int(request.form.get('max_attempts', 1))
        is_public = 1 if request.form.get('is_public') else 0

        conn = sqlite3.connect('quiz.db')
        c = conn.cursor()
        c.execute("INSERT INTO tests (name, description, creator_id, max_attempts, is_public) VALUES (?, ?, ?, ?, ?)",
                  (name, description, session['user_id'], max_attempts, is_public))
        test_id = c.lastrowid

        q_num = 1
        while f'question_{q_num}' in request.form:
            question_text = request.form[f'question_{q_num}']
            if question_text.strip():
                c.execute("INSERT INTO questions (test_id, question) VALUES (?, ?)", (test_id, question_text))
                question_id = c.lastrowid

                a_num = 1
                while f'answer_{q_num}_{a_num}' in request.form:
                    answer_text = request.form[f'answer_{q_num}_{a_num}']
                    is_correct = f'correct_{q_num}_{a_num}' in request.form
                    if answer_text.strip():
                        c.execute("INSERT INTO answers (question_id, answer_text, is_correct) VALUES (?, ?, ?)",
                                  (question_id, answer_text, is_correct))
                    a_num += 1
            q_num += 1

        conn.commit()
        conn.close()
        flash('Тест успешно создан!', 'success')
        return redirect(url_for('my_tests'))

    return render_template('create_test.html')


@app.route('/my_tests')
def my_tests():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT * FROM tests WHERE creator_id = ?", (session['user_id'],))
    tests = c.fetchall()
    conn.close()

    theme = get_user_theme()
    return render_template('my_tests.html', tests=tests, theme=theme)


@app.route('/edit_test/<int:test_id>', methods=['GET', 'POST'])
def edit_test(test_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT * FROM tests WHERE id = ? AND creator_id = ?", (test_id, session['user_id']))
    test = c.fetchone()

    if not test:
        conn.close()
        flash('Тест не найден или доступ запрещён', 'error')
        return redirect(url_for('my_tests'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        max_attempts = int(request.form.get('max_attempts', 1))
        is_public = 1 if request.form.get('is_public') else 0

        c.execute("UPDATE tests SET name = ?, description = ?, max_attempts = ?, is_public = ? WHERE id = ?",
                  (name, description, max_attempts, is_public, test_id))

        c.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE test_id = ?)", (test_id,))
        c.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))

        q_num = 1
        while f'question_{q_num}' in request.form:
            question_text = request.form[f'question_{q_num}']
            if question_text.strip():
                c.execute("INSERT INTO questions (test_id, question) VALUES (?, ?)", (test_id, question_text))
                question_id = c.lastrowid

                a_num = 1
                while f'answer_{q_num}_{a_num}' in request.form:
                    answer_text = request.form[f'answer_{q_num}_{a_num}']
                    is_correct = f'correct_{q_num}_{a_num}' in request.form
                    if answer_text.strip():
                        c.execute("INSERT INTO answers (question_id, answer_text, is_correct) VALUES (?, ?, ?)",
                                  (question_id, answer_text, is_correct))
                    a_num += 1
            q_num += 1

        conn.commit()
        conn.close()
        flash('Тест обновлён', 'success')
        return redirect(url_for('my_tests'))

    c.execute("SELECT * FROM questions WHERE test_id = ?", (test_id,))
    questions = c.fetchall()
    question_answers = {}
    for q in questions:
        c.execute("SELECT * FROM answers WHERE question_id = ?", (q[0],))
        question_answers[q[0]] = c.fetchall()

    conn.close()
    theme = get_user_theme()
    return render_template('edit_test.html', test=test, questions=questions, question_answers=question_answers, theme=theme)


@app.route('/delete_test/<int:test_id>', methods=['POST'])
def delete_test(test_id):
    if 'user_id' not in session:
        flash('Вы должны войти', 'error')
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT creator_id FROM tests WHERE id = ?", (test_id,))
    creator_row = c.fetchone()
    if not creator_row:
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('my_tests'))
    creator_id = creator_row[0]

    if session['user_id'] != creator_id and not has_permission('администратор'):
        conn.close()
        flash('Доступ запрещён', 'error')
        return redirect(url_for('my_tests'))

    c.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE test_id = ?)", (test_id,))
    c.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))
    c.execute("DELETE FROM test_results WHERE test_id = ?", (test_id,))
    c.execute("DELETE FROM tests WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()

    flash('Тест успешно удалён', 'success')
    return redirect(url_for('my_tests'))


@app.route('/update_test_status/<int:test_id>', methods=['POST'])
def update_test_status(test_id):
    if 'user_id' not in session:
        flash('Вы должны войти', 'error')
        return redirect(url_for('login'))

    is_public = request.form.get('is_public') == '1'

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT creator_id FROM tests WHERE id = ?", (test_id,))
    creator_row = c.fetchone()
    if not creator_row:
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('my_tests'))
    creator_id = creator_row[0]

    if session['user_id'] != creator_id and not has_permission('администратор'):
        conn.close()
        flash('Доступ запрещён', 'error')
        return redirect(url_for('my_tests'))

    c.execute("UPDATE tests SET is_public = ? WHERE id = ?", (1 if is_public else 0, test_id))
    conn.commit()
    conn.close()
    flash('Статус обновлён', 'success')
    return redirect(url_for('my_tests'))


@app.route('/test/<int:test_id>')
def take_test(test_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT id, creator_id, max_attempts, name, is_public FROM tests WHERE id = ?", (test_id,))
    test_data = c.fetchone()
    if not test_data:
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('index'))

    test_id, creator_id, max_attempts, test_name, is_public = test_data
    is_creator = (creator_id == session['user_id'])
    is_admin_or_moder = has_permission('модератор')

    if not is_public and not is_creator and not is_admin_or_moder:
        conn.close()
        flash('Тест недоступен', 'error')
        return redirect(url_for('index'))

    if not is_creator:
        c.execute("SELECT COUNT(*) FROM test_results WHERE test_id = ? AND user_id = ?", (test_id, session['user_id']))
        attempts_count = c.fetchone()[0]

        c.execute("SELECT extra_attempts FROM user_test_attempts_override WHERE test_id = ? AND user_id = ?", (test_id, session['user_id']))
        extra_row = c.fetchone()
        extra_attempts = extra_row[0] if extra_row else 0

        total_allowed_attempts = max_attempts + extra_attempts

        if attempts_count >= total_allowed_attempts:
            conn.close()
            flash(f'Вы исчерпали количество попыток ({total_allowed_attempts}) для этого теста', 'error')
            return redirect(url_for('index'))

    c.execute("SELECT * FROM questions WHERE test_id = ?", (test_id,))
    questions = c.fetchall()

    question_answers = {}
    for q in questions:
        c.execute("SELECT * FROM answers WHERE question_id = ?", (q[0],))
        question_answers[q[0]] = c.fetchall()

    conn.close()
    theme = get_user_theme()
    return render_template('take_test.html',
                           test_id=test_id,
                           questions=questions,
                           question_answers=question_answers,
                           theme=theme,
                           test_name=test_name)


@app.route('/submit_test/<int:test_id>', methods=['POST'])
def submit_test(test_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT id, creator_id, max_attempts FROM tests WHERE id = ?", (test_id,))
    test = c.fetchone()
    if not test:
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('index'))

    creator_id, max_attempts = test[1], test[2]
    is_creator = (creator_id == session['user_id'])

    if not is_creator:
        c.execute("SELECT COUNT(*) FROM test_results WHERE test_id = ? AND user_id = ?", (test_id, session['user_id']))
        attempts_count = c.fetchone()[0]

        c.execute("SELECT extra_attempts FROM user_test_attempts_override WHERE test_id = ? AND user_id = ?", (test_id, session['user_id']))
        extra_row = c.fetchone()
        extra_attempts = extra_row[0] if extra_row else 0

        total_allowed_attempts = max_attempts + extra_attempts

        if attempts_count >= total_allowed_attempts:
            conn.close()
            flash(f'Вы исчерпали количество попыток ({total_allowed_attempts}) для этого теста', 'error')
            return redirect(url_for('index'))

    c.execute("SELECT id FROM questions WHERE test_id = ?", (test_id,))
    question_ids = [row[0] for row in c.fetchall()]

    score = 0
    total_questions = len(question_ids)

    # Сохраняем результат
    c.execute("INSERT INTO test_results (test_id, user_id, score, total_questions) VALUES (?, ?, ?, ?)",
              (test_id, session['user_id'], score, total_questions))
    result_id = c.lastrowid

    # Обрабатываем ответы
    for q_id in question_ids:
        user_answer_id = request.form.get(f'question_{q_id}')
        if user_answer_id:
            user_answer_id = int(user_answer_id)
            c.execute("SELECT is_correct FROM answers WHERE id = ? AND question_id = ?", (user_answer_id, q_id))
            correct = c.fetchone()
            is_correct = bool(correct[0]) if correct else False
            if is_correct:
                score += 1

            # Сохраняем ответ
            c.execute("INSERT INTO user_answers (result_id, question_id, answer_id) VALUES (?, ?, ?)",
                      (result_id, q_id, user_answer_id))

    # Обновляем баллы
    c.execute("UPDATE test_results SET score = ? WHERE id = ?", (score, result_id))
    conn.commit()

    # Сохраняем в сессию для /result
    session['test_results_details'] = []
    for q_id, user_answer_id, is_correct, in []:
        pass
    session['test_id'] = test_id
    session['result_id'] = result_id

    conn.close()

    return redirect(url_for('result', test_id=test_id, score=score, total=total_questions))

@app.route('/admin/stats')
def admin_stats():
    if not has_permission('модератор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('index'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM tests")
    total_tests = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE role = 'ученик'")
    students = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE role = 'учитель'")
    teachers = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE role = 'модератор'")
    moderators = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE role = 'администратор'")
    admins = c.fetchone()[0]

    conn.close()
    theme = get_user_theme()
    return render_template('admin_stats.html',
                           total_users=total_users,
                           total_tests=total_tests,
                           students=students,
                           teachers=teachers,
                           moderators=moderators,
                           admins=admins,
                           theme=theme)

@app.route('/result')
def result():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    test_id = request.args.get('test_id')
    score = request.args.get('score')
    total = request.args.get('total')

    if not all([test_id, score, total]):
        flash('Ошибка: данные результата недоступны', 'error')
        return redirect(url_for('index'))

    test_id, score, total = int(test_id), int(score), int(total)

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT creator_id FROM tests WHERE id = ?", (test_id,))
    creator = c.fetchone()
    is_creator = creator and creator[0] == session['user_id']

    c.execute("SELECT id FROM test_results WHERE test_id = ? AND user_id = ?", (test_id, session['user_id']))
    user_result = c.fetchone()

    if not is_creator and not user_result:
        conn.close()
        flash('Доступ к результату запрещён', 'error')
        return redirect(url_for('index'))

    # Получаем детали из сессии
    result_id = session.get('result_id')
    details = []
    if result_id:
        c.execute("""
            SELECT q.question, a.answer_text, a.is_correct
            FROM user_answers ua
            JOIN questions q ON ua.question_id = q.id
            LEFT JOIN answers a ON ua.answer_id = a.id
            WHERE ua.result_id = ?
            ORDER BY q.id
        """, (result_id,))
        rows = c.fetchall()
        for row in rows:
            details.append({
                'question': row[0],
                'user_answer': row[1] or 'Не отвечено',
                'is_correct': row[2]
            })

    conn.close()

    theme = get_user_theme()
    return render_template('result.html', score=score, total=total, theme=theme, question_details=details)


@app.route('/test_history')
def test_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("""
        SELECT tr.id, t.name, tr.score, tr.total_questions 
        FROM test_results tr 
        JOIN tests t ON tr.test_id = t.id 
        WHERE tr.user_id = ?
        ORDER BY tr.id DESC
    """, (session['user_id'],))
    taken_test_results = c.fetchall()
    conn.close()

    theme = get_user_theme()
    return render_template('test_history.html', taken_test_results=taken_test_results, theme=theme)


@app.route('/view_result/<int:result_id>')
def view_result(result_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT tr.test_id, tr.score, tr.total_questions, tr.user_id FROM test_results tr WHERE tr.id = ?", (result_id,))
    result_row = c.fetchone()
    if not result_row:
        conn.close()
        flash('Результат не найден', 'error')
        return redirect(url_for('test_history'))

    test_id, score, total_questions, user_id = result_row
    if user_id != session['user_id']:
        conn.close()
        flash('Доступ запрещён', 'error')
        return redirect(url_for('test_history'))

    c.execute("""
        SELECT q.question, a.answer_text, a.is_correct
        FROM user_answers ua
        JOIN questions q ON ua.question_id = q.id
        LEFT JOIN answers a ON ua.answer_id = a.id
        WHERE ua.result_id = ?
        ORDER BY q.id
    """, (result_id,))
    rows = c.fetchall()

    conn.close()

    theme = get_user_theme()
    return render_template('view_result.html', score=score, total=total_questions, rows=rows, theme=theme)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT role, requested_role, password FROM users WHERE id = ?", (session['user_id'],))
    user_role, requested_role, current_password_db = c.fetchone()
    conn.close()

    if request.method == 'POST':
        current_password_form = request.form.get('current_password')
        new_password_form = request.form.get('new_password')

        if current_password_form and new_password_form:
            if current_password_form == current_password_db:
                conn = sqlite3.connect('quiz.db')
                c = conn.cursor()
                c.execute("UPDATE users SET password = ? WHERE id = ?", (new_password_form, session['user_id']))
                conn.commit()
                conn.close()
                flash('Пароль успешно изменён', 'success')
                return redirect(url_for('settings'))
            else:
                flash('Неверный текущий пароль', 'error')
                return redirect(url_for('settings'))

        theme = request.form.get('theme', 'dark')
        request_teacher = request.form.get('request_teacher')
        request_moderator = request.form.get('request_moderator')

        conn = sqlite3.connect('quiz.db')
        c = conn.cursor()
        c.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, session['user_id']))

        if request_teacher and user_role != 'учитель' and requested_role != 'учитель':
            c.execute("UPDATE users SET requested_role = 'учитель' WHERE id = ?", (session['user_id'],))
            flash('Запрос на роль учителя отправлен', 'success')
        elif request_teacher and requested_role == 'учитель':
            flash('Запрос уже отправлен', 'info')

        if request_moderator and user_role != 'модератор' and requested_role != 'модератор':
            c.execute("UPDATE users SET requested_role = 'модератор' WHERE id = ?", (session['user_id'],))
            flash('Запрос на роль модератора отправлен', 'success')
        elif request_moderator and requested_role == 'модератор':
            flash('Запрос уже отправлен', 'info')

        conn.commit()
        conn.close()
        flash('Настройки сохранены', 'success')
        return redirect(url_for('settings'))

    theme = get_user_theme()
    return render_template('settings.html', theme=theme, user_role=user_role, requested_role=requested_role)


@app.route('/admin')
def admin_panel():
    if not has_permission('администратор'):
        flash('У вас нет прав для доступа к админке', 'error')
        return redirect(url_for('index'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT id, username, role, requested_role FROM users")
    users = c.fetchall()
    conn.close()

    theme = get_user_theme()
    return render_template('admin.html', users=users, theme=theme)


@app.route('/admin/users')
def admin_users():
    if not has_permission('модератор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('index'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT id, username, role, requested_role FROM users ORDER BY id")
    users = c.fetchall()
    conn.close()

    theme = get_user_theme()
    return render_template('admin_users.html', users=users, theme=theme)


@app.route('/admin/tests')
def admin_tests():
    if not has_permission('модератор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('index'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("""
        SELECT t.id, t.name, u.username, u.role, t.is_public, COUNT(q.id) as q_count,
               (SELECT COUNT(*) FROM test_results WHERE test_id = t.id) as attempts
        FROM tests t
        JOIN users u ON t.creator_id = u.id
        LEFT JOIN questions q ON t.id = q.test_id
        GROUP BY t.id, t.name, u.username, u.role, t.is_public
        ORDER BY t.id DESC
    """)
    tests = c.fetchall()
    conn.close()

    theme = get_user_theme()
    return render_template('admin_tests.html', tests=tests, theme=theme)


@app.route('/admin/edit_test/<int:test_id>', methods=['GET', 'POST'])
def admin_edit_test(test_id):
    if not has_permission('администратор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('admin_tests'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
    test = c.fetchone()

    if not test:
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('admin_tests'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        max_attempts = int(request.form.get('max_attempts', 1))
        is_public = 1 if request.form.get('is_public') else 0

        c.execute("UPDATE tests SET name = ?, description = ?, max_attempts = ?, is_public = ? WHERE id = ?",
                  (name, description, max_attempts, is_public, test_id))

        c.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE test_id = ?)", (test_id,))
        c.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))

        q_num = 1
        while f'question_{q_num}' in request.form:
            question_text = request.form[f'question_{q_num}']
            if question_text.strip():
                c.execute("INSERT INTO questions (test_id, question) VALUES (?, ?)", (test_id, question_text))
                question_id = c.lastrowid

                a_num = 1
                while f'answer_{q_num}_{a_num}' in request.form:
                    answer_text = request.form[f'answer_{q_num}_{a_num}']
                    is_correct = f'correct_{q_num}_{a_num}' in request.form
                    if answer_text.strip():
                        c.execute("INSERT INTO answers (question_id, answer_text, is_correct) VALUES (?, ?, ?)",
                                  (question_id, answer_text, is_correct))
                    a_num += 1
            q_num += 1

        conn.commit()
        conn.close()
        flash('Тест обновлён', 'success')
        return redirect(url_for('admin_tests'))

    c.execute("SELECT * FROM questions WHERE test_id = ?", (test_id,))
    questions = c.fetchall()
    question_answers = {}
    for q in questions:
        c.execute("SELECT * FROM answers WHERE question_id = ?", (q[0],))
        question_answers[q[0]] = c.fetchall()

    conn.close()
    theme = get_user_theme()
    return render_template('admin_edit_test.html', test=test, questions=questions, question_answers=question_answers, theme=theme)


@app.route('/admin/delete_test/<int:test_id>', methods=['POST'])
def admin_delete_test(test_id):
    if not has_permission('администратор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('admin_tests'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT id FROM tests WHERE id = ?", (test_id,))
    if not c.fetchone():
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('admin_tests'))

    c.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE test_id = ?)", (test_id,))
    c.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))
    c.execute("DELETE FROM test_results WHERE test_id = ?", (test_id,))
    c.execute("DELETE FROM tests WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()

    flash('Тест успешно удалён', 'success')
    return redirect(url_for('admin_tests'))


@app.route('/admin/requests')
def admin_requests():
    if not has_permission('модератор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('index'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.role, u.requested_role
        FROM users u
        WHERE u.requested_role IS NOT NULL
        ORDER BY u.id
    """)
    requests = c.fetchall()
    conn.close()

    theme = get_user_theme()
    return render_template('admin_requests.html', requests=requests, theme=theme)


@app.route('/admin/grant_requested_role/<int:user_id>')
def grant_requested_role(user_id):
    if not has_permission('модератор'):
        flash('У вас нет прав для подтверждения роли', 'error')
        return redirect(url_for('index'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT requested_role FROM users WHERE id = ?", (user_id,))
    requested = c.fetchone()
    if not requested or not requested[0]:
        conn.close()
        flash('Нет активного запроса', 'error')
        return redirect(url_for('admin_requests'))

    requested_role = requested[0]

    current_username = session.get('username')
    if requested_role == 'администратор' and current_username != 'admin':
        conn.close()
        flash('Только пользователь admin может выдавать роль администратор', 'error')
        return redirect(url_for('admin_requests'))

    c.execute("UPDATE users SET role = ?, requested_role = NULL WHERE id = ?", (requested_role, user_id))
    conn.commit()
    conn.close()
    flash(f'Роль {requested_role} подтверждена', 'success')
    return redirect(url_for('admin_requests'))


@app.route('/admin/reject_request/<int:user_id>')
def reject_request(user_id):
    if not has_permission('модератор'):
        flash('У вас нет прав для отклонения запросов', 'error')
        return redirect(url_for('admin_requests'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("UPDATE users SET requested_role = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    flash('Запрос отклонён', 'success')
    return redirect(url_for('admin_requests'))


@app.route('/admin/change_role/<int:user_id>', methods=['POST'])
def change_role(user_id):
    if not has_permission('администратор'):
        flash('У вас нет прав для изменения роли', 'error')
        return redirect(url_for('admin_panel'))

    new_role = request.form['new_role']
    if new_role not in ['ученик', 'учитель', 'модератор', 'администратор']:
        flash('Недопустимая роль', 'error')
        return redirect(url_for('admin_panel'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    target_user = c.fetchone()
    if not target_user or target_user[0] == 'admin':
        conn.close()
        flash('Нельзя изменить роль пользователю admin', 'error')
        return redirect(url_for('admin_users'))

    c.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    flash('Роль изменена', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/change_password/<int:user_id>', methods=['POST'])
def change_password(user_id):
    if not has_permission('администратор'):
        flash('У вас нет прав для изменения пароля', 'error')
        return redirect(url_for('admin_panel'))

    new_password = request.form['new_password']

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user_id))
    conn.commit()
    conn.close()
    flash('Пароль изменён', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/delete_user/<int:user_id>')
def delete_user(user_id):
    if not has_permission('администратор'):
        flash('У вас нет прав для удаления пользователя', 'error')
        return redirect(url_for('admin_panel'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    # Удаляем тесты пользователя
    c.execute("SELECT id FROM tests WHERE creator_id = ?", (user_id,))
    test_ids = [row[0] for row in c.fetchall()]

    for test_id in test_ids:
        c.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE test_id = ?)", (test_id,))
        c.execute("DELETE FROM questions WHERE test_id = ?", (test_id,))
        c.execute("DELETE FROM test_results WHERE test_id = ?", (test_id,))

    c.execute("DELETE FROM test_results WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash('Пользователь и все его данные удалены', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if not has_permission('администратор'):
        flash('У вас нет прав для добавления пользователя', 'error')
        return redirect(url_for('admin_panel'))

    username = request.form['username']
    password = request.form['password']
    role = request.form.get('role', 'ученик')

    if role == 'администратор':
        current_username = session.get('username')
        if current_username != 'admin':
            flash('Только пользователь admin может создавать администраторов', 'error')
            return redirect(url_for('admin_users'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, role))
        conn.commit()
        flash('Пользователь добавлен', 'success')
    except sqlite3.IntegrityError:
        flash('Пользователь с таким именем уже существует', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_users'))


@app.route('/admin/logins')
def admin_logins():
    if not has_permission('администратор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('admin_panel'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()
    c.execute("SELECT id, username, password, role, strftime('%d.%m.%Y', datetime('now')) FROM users ORDER BY id ASC")
    users = c.fetchall()
    conn.close()
    return render_template('admin_logins.html', users=users)


@app.route('/admin/set_mode/<mode>')
def set_mode(mode):
    if mode not in ['isolate', 'maintenance', 'normal']:
        return {'error': 'Invalid mode'}, 400
    if not has_permission('администратор'):
        return {'error': 'Forbidden'}, 403

    if mode == 'normal':
        set_maintenance_mode('none')
    else:
        set_maintenance_mode(mode)
    return {'message': f'Режим изменён на: {mode}'}


@app.route('/admin/actions')
def admin_actions():
    if not has_permission('администратор'):
        flash('Доступ запрещён', 'error')
        return redirect(url_for('admin_panel'))

    return render_template('admin_actions.html')


@app.route('/moder')
def moder_panel():
    if not has_permission('модератор'):
        flash('У вас нет прав для доступа', 'error')
        return redirect(url_for('index'))

    theme = get_user_theme()
    return render_template('moder.html', theme=theme)


@app.route('/request_moderator', methods=['POST'])
def request_moderator():
    if 'user_id' not in session:
        return {'error': 'Not logged in'}, 401

    user_id = session['user_id']
    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT requested_role FROM users WHERE id = ?", (user_id,))
    current_request = c.fetchone()
    if current_request and current_request[0] == 'модератор':
        conn.close()
        return {'message': 'Запрос уже отправлен'}, 200

    c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    role = c.fetchone()
    if role and role[0] == 'модератор':
        conn.close()
        return {'message': 'Вы уже модератор'}, 200

    c.execute("UPDATE users SET requested_role = 'модератор' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {'message': 'Запрос на роль модератора отправлен'}


@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return {'error': 'Not logged in'}, 401

    user_id = session['user_id']
    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("DELETE FROM test_results WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM user_answers WHERE result_id IN (SELECT id FROM test_results WHERE user_id = ?)", (user_id,))
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()

    session.clear()
    return {'message': 'Аккаунт удалён'}


@app.route('/give_extra_attempt/<int:test_id>/<int:user_id>', methods=['POST'])
def give_extra_attempt(test_id, user_id):
    if 'user_id' not in session:
        return {'error': 'Not logged in'}, 401

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT creator_id FROM tests WHERE id = ?", (test_id,))
    creator_row = c.fetchone()
    if not creator_row:
        conn.close()
        return {'error': 'Test not found'}, 404
    creator_id = creator_row[0]

    if session['user_id'] != creator_id and not has_permission('администратор'):
        conn.close()
        return {'error': 'Forbidden'}, 403

    c.execute("""
        INSERT INTO user_test_attempts_override (user_id, test_id, extra_attempts)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, test_id) DO UPDATE SET extra_attempts = extra_attempts + 1
    """, (user_id, test_id))
    conn.commit()
    conn.close()

    flash('Дополнительная попытка выдана', 'success')
    return redirect(url_for('test_results', test_id=test_id))


@app.route('/test_results/<int:test_id>')
def test_results(test_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('quiz.db')
    c = conn.cursor()

    c.execute("SELECT creator_id FROM tests WHERE id = ?", (test_id,))
    creator_row = c.fetchone()
    if not creator_row:
        conn.close()
        flash('Тест не найден', 'error')
        return redirect(url_for('my_tests'))
    creator_id = creator_row[0]

    if session['user_id'] != creator_id and not has_permission('администратор'):
        conn.close()
        flash('Доступ запрещён', 'error')
        return redirect(url_for('my_tests'))

    c.execute("""
        SELECT 
            u.id,
            u.username,
            tr.score,
            tr.total_questions
        FROM test_results tr
        JOIN users u ON tr.user_id = u.id
        WHERE tr.test_id = ?
        AND tr.id IN (
            SELECT id FROM test_results t2
            WHERE t2.test_id = tr.test_id AND t2.user_id = tr.user_id
            ORDER BY t2.score DESC, t2.id DESC
            LIMIT 1
        )
        ORDER BY tr.id ASC
    """, (test_id,))
    results = c.fetchall()
    conn.close()

    return render_template('test_results.html', test_id=test_id, results=results)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)