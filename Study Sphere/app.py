# app.py — StudySphere AI
# Complete Final Version

from flask import Flask, render_template, request, session, redirect, url_for
import os
import PyPDF2
import nltk
import random
import sqlite3
from datetime import datetime
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.tag import pos_tag

# =====================
# APP SETUP
# =====================
app = Flask(__name__)
app.secret_key = 'learning123'

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'txt'}


# =====================
# DATABASE SETUP
# =====================
def init_db():
    """Creates all tables if they don't exist"""
    conn   = sqlite3.connect('quiz.db')
    cursor = conn.cursor()

    # Table 1 — Quiz Results
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            filename   TEXT,
            score      INTEGER,
            total      INTEGER,
            percentage REAL,
            timestamp  TEXT
        )
    ''')

    # Table 2 — Viva Questions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS viva_questions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            filename  TEXT,
            question  TEXT,
            answer    TEXT,
            timestamp TEXT
        )
    ''')

    # Table 3 — Calendar Reminders
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT,
            date          TEXT,
            reminder_type TEXT
        )
    ''')

    conn.commit()
    conn.close()


# =====================
# DATABASE HELPERS
# =====================
def save_result(filename, score, total, percentage):
    """Save quiz result to database"""
    conn      = sqlite3.connect('quiz.db')
    cursor    = conn.cursor()
    timestamp = datetime.now().strftime('%d %b %Y, %I:%M %p')
    cursor.execute('''
        INSERT INTO results (filename, score, total, percentage, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (filename, score, total, percentage, timestamp))
    conn.commit()
    conn.close()


def get_all_results():
    """Get all quiz results newest first"""
    conn   = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT filename, score, total, percentage, timestamp
        FROM results ORDER BY id DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [{'filename': r[0], 'score': r[1], 'total': r[2],
             'percentage': r[3], 'timestamp': r[4]} for r in rows]


def get_stats():
    """Calculate performance statistics"""
    conn   = sqlite3.connect('quiz.db')
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM results')
    total_quizzes = cursor.fetchone()[0]

    if total_quizzes == 0:
        conn.close()
        return None

    cursor.execute('SELECT AVG(percentage) FROM results')
    avg_score = round(cursor.fetchone()[0], 1)

    cursor.execute('SELECT MAX(percentage) FROM results')
    best_score = round(cursor.fetchone()[0], 1)

    cursor.execute('SELECT percentage FROM results ORDER BY id DESC LIMIT 1')
    latest_score = round(cursor.fetchone()[0], 1)

    cursor.execute('''
        SELECT percentage, timestamp FROM results
        ORDER BY id DESC LIMIT 7
    ''')
    chart_data = cursor.fetchall()
    chart_data.reverse()

    conn.close()

    return {
        'total_quizzes': total_quizzes,
        'avg_score'    : avg_score,
        'best_score'   : best_score,
        'latest_score' : latest_score,
        'chart_scores' : [r[0] for r in chart_data],
        'chart_labels' : [r[1] for r in chart_data]
    }


# =====================
# HELPER — Check File
# =====================
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# =====================
# HELPER — Extract Text
# =====================
def extract_text(filepath, filename):
    """Extract text from txt or pdf file"""
    text      = ""
    extension = filename.rsplit('.', 1)[1].lower()

    if extension == 'txt':
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

    elif extension == 'pdf':
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    return text


# =====================
# HELPER — Generate MCQs
# =====================
def generate_mcqs(text, num_questions=5):
    """Generate MCQs from extracted text"""
    sentences = sent_tokenize(text)

    good_sentences = []
    for sentence in sentences:
        word_count = len(sentence.split())
        if 8 <= word_count <= 30:
            good_sentences.append(sentence)

    if len(good_sentences) < num_questions:
        num_questions = len(good_sentences)

    if num_questions == 0:
        return []

    selected_sentences = random.sample(good_sentences, num_questions)

    stop_words   = set(stopwords.words('english'))
    all_words    = word_tokenize(text)
    tagged_all   = pos_tag(all_words)
    all_keywords = list(set([
        word for word, tag in tagged_all
        if tag in ['NN', 'NNP', 'NNS', 'NNPS']
        and word.lower() not in stop_words
        and word.isalpha()
        and len(word) > 3
    ]))

    mcqs = []

    for sentence in selected_sentences:
        words    = word_tokenize(sentence)
        tagged   = pos_tag(words)
        keywords = [
            word for word, tag in tagged
            if tag in ['NN', 'NNP', 'NNS', 'NNPS']
            and word.lower() not in stop_words
            and word.isalpha()
            and len(word) > 3
        ]

        if not keywords:
            continue

        answer     = random.choice(keywords)
        question   = sentence.replace(answer, '________')
        wrong_pool = [w for w in all_keywords if w.lower() != answer.lower()]

        if len(wrong_pool) < 3:
            continue

        wrong_options = random.sample(wrong_pool, 3)
        options       = wrong_options + [answer]
        random.shuffle(options)

        mcqs.append({
            'question': question,
            'options' : options,
            'answer'  : answer
        })

    return mcqs


# =====================
# HELPER — Generate Viva
# =====================
def generate_viva(text, num_questions=7):
    """Generate viva questions from text"""
    sentences  = sent_tokenize(text)
    stop_words = set(stopwords.words('english'))

    templates = [
        "What is {}?",
        "What are {}?",
        "Explain the concept of {}.",
        "Why is {} important?",
        "How does {} work?",
        "Define {}.",
        "Describe the role of {}."
    ]

    viva_questions = []
    used_keywords  = set()

    for sentence in sentences:
        if len(viva_questions) >= num_questions:
            break

        words    = word_tokenize(sentence)
        tagged   = pos_tag(words)
        keywords = [
            word for word, tag in tagged
            if tag in ['NN', 'NNP', 'NNS', 'NNPS']
            and word.lower() not in stop_words
            and word.isalpha()
            and len(word) > 4
            and word.lower() not in used_keywords
        ]

        if not keywords:
            continue

        keyword  = keywords[0]
        used_keywords.add(keyword.lower())
        template = random.choice(templates)
        question = template.format(keyword)
        answer   = sentence.strip()

        viva_questions.append({
            'question': question,
            'answer'  : answer
        })

    return viva_questions


# =====================
# ROUTE 1 — Home Page
# =====================
@app.route('/')
def index():
    return render_template('index.html')


# =====================
# ROUTE 2 — Upload File
# =====================
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return render_template('index.html',
                               message='No file selected!',
                               message_type='error')

    file = request.files['file']

    if file.filename == '':
        return render_template('index.html',
                               message='Please choose a file first!',
                               message_type='error')

    if not allowed_file(file.filename):
        return render_template('index.html',
                               message='Only .pdf and .txt files are allowed!',
                               message_type='error')

    filename = file.filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    extracted_text = extract_text(filepath, filename)

    if not extracted_text.strip():
        return render_template('index.html',
                               message='Could not extract text. Try a different file.',
                               message_type='error')

    preview = extracted_text[:1000]

    return render_template('index.html',
                           message=f'✅ File "{filename}" uploaded successfully!',
                           message_type='success',
                           preview=preview,
                           full_text=extracted_text,
                           filename=filename)


# =====================
# ROUTE 3 — Quizzes Page
# =====================
@app.route('/quizzes')
def quizzes():
    return render_template('quizzes.html')


# =====================
# ROUTE 4 — Generate MCQs
# =====================
@app.route('/generate', methods=['POST'])
def generate():
    full_text = request.form.get('full_text', '')
    filename  = request.form.get('filename', 'unknown')

    if not full_text.strip():
        return render_template('index.html',
                               message='No text found. Please upload a file first.',
                               message_type='error')

    mcqs = generate_mcqs(full_text, num_questions=5)

    if not mcqs:
        return render_template('index.html',
                               message='Could not generate MCQs. Try a longer file.',
                               message_type='error')

    session['mcqs']     = mcqs
    session['filename'] = filename

    return render_template('quiz.html', mcqs=mcqs)


# =====================
# ROUTE 5 — Submit Quiz
# =====================
@app.route('/submit', methods=['POST'])
def submit():
    mcqs     = session.get('mcqs', [])
    filename = session.get('filename', 'unknown')

    if not mcqs:
        return render_template('index.html',
                               message='Session expired. Please upload again.',
                               message_type='error')

    score   = 0
    results = []

    for i, mcq in enumerate(mcqs):
        user_answer    = request.form.get(f'answer_{i}', '')
        correct_answer = mcq['answer']
        is_correct     = (user_answer.strip() == correct_answer.strip())

        if is_correct:
            score += 1

        results.append({
            'question'      : mcq['question'],
            'options'       : mcq['options'],
            'user_answer'   : user_answer,
            'correct_answer': correct_answer,
            'is_correct'    : is_correct
        })

    total      = len(mcqs)
    percentage = round((score / total) * 100)

    if percentage >= 80:
        grade = '🌟 Excellent!'
    elif percentage >= 60:
        grade = '👍 Good Job!'
    elif percentage >= 40:
        grade = '📚 Keep Practicing!'
    else:
        grade = "💪 Don't Give Up!"

    save_result(filename, score, total, percentage)

    return render_template('results.html',
                           results=results,
                           score=score,
                           total=total,
                           percentage=percentage,
                           grade=grade)


# =====================
# ROUTE 6 — History
# =====================
@app.route('/history')
def history():
    all_results = get_all_results()
    stats       = get_stats()
    return render_template('history.html',
                           all_results=all_results,
                           stats=stats)


# =====================
# ROUTE 7 — Dashboard
# =====================
@app.route('/dashboard')
def dashboard():
    stats = get_stats()
    return render_template('dashboard.html', stats=stats)


# =====================
# ROUTE 8 — Viva Page
# =====================
@app.route('/viva', methods=['GET', 'POST'])
def viva():
    if request.method == 'GET':
        return render_template('viva.html')

    if 'file' not in request.files:
        return render_template('viva.html',
                               message='No file selected!',
                               message_type='error')

    file = request.files['file']

    if file.filename == '' or not allowed_file(file.filename):
        return render_template('viva.html',
                               message='Please upload a valid .txt or .pdf file!',
                               message_type='error')

    filename = file.filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    text = extract_text(filepath, filename)

    if not text.strip():
        return render_template('viva.html',
                               message='Could not extract text from file.',
                               message_type='error')

    viva_qs = generate_viva(text, num_questions=7)

    if not viva_qs:
        return render_template('viva.html',
                               message='Could not generate viva questions. Try a longer file.',
                               message_type='error')

    return render_template('viva.html',
                           viva_questions=viva_qs,
                           filename=filename)


# =====================
# ROUTE 9 — Calendar
# =====================
@app.route('/calendar')
def calendar():
    """Show all reminders"""
    conn   = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, date, reminder_type
        FROM reminders
        ORDER BY date ASC
    ''')
    rows = cursor.fetchall()
    conn.close()

    reminders = [{'id': r[0], 'title': r[1],
                  'date': r[2], 'reminder_type': r[3]} for r in rows]

    return render_template('calendar.html', reminders=reminders)


# =====================
# ROUTE 10 — Add Reminder
# =====================
@app.route('/calendar/add', methods=['POST'])
def add_reminder():
    """Save new reminder to database"""
    title         = request.form.get('title', '')
    date          = request.form.get('date', '')
    reminder_type = request.form.get('reminder_type', 'other')

    if title and date:
        conn   = sqlite3.connect('quiz.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reminders (title, date, reminder_type)
            VALUES (?, ?, ?)
        ''', (title, date, reminder_type))
        conn.commit()
        conn.close()

    return redirect(url_for('calendar'))


# =====================
# ROUTE 11 — Delete Reminder
# =====================
@app.route('/calendar/delete/<int:id>', methods=['POST'])
def delete_reminder(id):
    """Delete a reminder by id"""
    conn   = sqlite3.connect('quiz.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM reminders WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('calendar'))


# =====================
# RUN THE APP
# =====================
if __name__ == '__main__':
    init_db()           # Create all tables on startup
    app.run(debug=True)