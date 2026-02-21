import streamlit as st
import speech_recognition as sr
import tempfile
from textblob import TextBlob
from groq import Groq
import re
import base64
import hashlib
import sqlite3
import os
import time
from datetime import datetime
from fpdf import FPDF
# ---------------- CONFIG ----------------
st.set_page_config(page_title="AI Interview Analyzer", layout="wide")
from dotenv import load_dotenv
load_dotenv()


# ---------------- DATABASE SETUP ----------------
DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS interview_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            avg_score REAL NOT NULL,
            total_questions INTEGER NOT NULL,
            date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_interview(email, role, avg_score, total_questions):
    try:
        if not email:
            return False
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO interview_history (email, role, avg_score, total_questions, date) VALUES (?, ?, ?, ?, ?)",
            (email, role, round(avg_score, 1), total_questions, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Could not save interview: {e}")
        return False

def get_interview_history(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, avg_score, total_questions, date FROM interview_history WHERE email=? ORDER BY id DESC LIMIT 10",
        (email,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_total_interviews(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM interview_history WHERE email=?", (email,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_overall_avg(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT AVG(avg_score) FROM interview_history WHERE email=?", (email,))
    avg = c.fetchone()[0]
    conn.close()
    return avg or 0

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(name, email, password):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                  (name, email, hash_password(password)))
        conn.commit()
        conn.close()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Email already registered."
    except Exception as e:
        return False, str(e)

def login_user(email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, email FROM users WHERE email=? AND password=?",
              (email, hash_password(password)))
    user = c.fetchone()
    conn.close()
    return user

init_db()

# ---------------- SESSION STATE ----------------
defaults = {
    "logged_in": False,
    "user_email": None,
    "user_name": None,
    "current_page": "dashboard",
    "auth_page": "login",
    "total_interviews": 0,
    "history": [],
    "conversation": [],
    "question": "",
    "interview_started": False,
    "show_evaluation": False,
    "max_questions": 10,
    "timer_seconds": 120,
    "timer_start": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------- GROQ CLIENT ----------------
import os
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------- HELPERS ----------------
def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except FileNotFoundError:
        return None

def set_bg(image_file, opacity=0.35):
    try:
        with open(image_file, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        st.markdown(f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,{opacity});
            z-index: -1;
        }}
        </style>
        """, unsafe_allow_html=True)
    except:
        pass

# ---------------- GLOBAL STYLE ----------------
st.markdown("""
<style>
html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }
.hero { text-align: center; padding: 3.5rem 1rem 1.5rem 1rem; }
.hero h1 {
    font-size: clamp(2rem, 5vw, 3.5rem);
    color: white; font-weight: 900;
    margin-bottom: 0.4rem; margin-top: 0;
}
.hero span { color: #e50914; }
.hero p { color: #bbbbbb; font-size: 1.2rem; }
.card {
    background: #1c1c1c; padding: 2rem;
    border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.6);
    margin-bottom: 1rem;
}
.question-box {
    background: rgba(229,9,20,0.08);
    border-left: 4px solid #e50914;
    padding: 1rem 1.4rem;
    border-radius: 0 12px 12px 0;
    font-size: 1.15rem; font-weight: 600;
    color: white; margin-bottom: 1rem;
}
.timer-box {
    display: inline-block; padding: 0.4rem 1.2rem;
    border-radius: 30px; font-size: 1.2rem;
    font-weight: 700; margin-bottom: 0.8rem;
    border: 2px solid currentColor;
}
.score-card {
    background: #1c1c1c; border-radius: 14px;
    padding: 1.2rem; text-align: center;
    box-shadow: 0 4px 14px rgba(0,0,0,0.4);
}
.score-number { font-size: 2.6rem; font-weight: 900; line-height: 1; }
.score-label  { font-size: 0.82rem; color: #aaa; margin-top: 0.3rem; }
.stButton > button {
    background-color: #e50914 !important;
    color: white !important; font-weight: bold;
    border-radius: 8px; padding: 10px 25px;
    border: none !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 4px 14px rgba(229,9,20,0.35);
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(229,9,20,0.5);
}
.stButton > button:active { transform: translateY(0px); }
[data-testid="metric-container"] {
    background: #1c1c1c;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 1rem 1.2rem;
    box-shadow: 0 4px 14px rgba(0,0,0,0.3);
}
.stProgress > div > div {
    background: linear-gradient(90deg, #e50914, #ff6b35) !important;
    border-radius: 8px !important;
}
hr { border-color: rgba(255,255,255,0.1) !important; }
h1, h2, h3, h4 { color: white !important; }
label { color: white !important; font-weight: 600 !important; }
p { color: #e8e8e8 !important; }
/* Download buttons — white bg so text must be dark */
[data-testid="stDownloadButton"] > button {
    background-color: white !important;
    color: #111111 !important;
    border: 2px solid #e50914 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15) !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background-color: #f5f5f5 !important;
    color: #111111 !important;
    box-shadow: 0 4px 14px rgba(229,9,20,0.3) !important;
}
@media (max-width: 768px) { .hero h1 { font-size: 2rem; } }
</style>
""", unsafe_allow_html=True)


# ================================================================
#  AI FUNCTIONS
# ================================================================

def generate_question(role, mode, question_count, conversation=None):
    if mode == "Friendly":
        tone_instruction = "Generate one friendly, warm and conversational interview question. Keep it supportive and approachable."
    else:
        tone_instruction = "Generate one professional and direct interview question."

    if question_count == 0:
        prompt = (f"{tone_instruction}\nYou are a professional interviewer.\n"
                  "Ask the candidate to briefly introduce themselves and their background.\n"
                  "Return ONLY the question, nothing else.")
    elif question_count == 1:
        prompt = (f"{tone_instruction}\nYou are a professional interviewer.\n"
                  f"Generate ONE core technical or behavioural interview question for a {role}.\n"
                  "Make it practical and relevant to real-world responsibilities.\n"
                  "Return ONLY the question, nothing else.")
    else:
        last = conversation[-1]
        prompt = f"""
{tone_instruction}
You are a professional interviewer conducting an adaptive interview for a {role} role.

Previous Question: {last["question"]}
Candidate's Answer: {last["answer"]}
Score received: {last["score"]}/10

Based on the score, adapt the next question:
- Score 8-10: Ask a harder follow-up or a new advanced question on the same topic.
- Score 6-7: Ask a moderately challenging follow-up on the same topic.
- Score 4-5: Ask a simpler clarifying question on the same topic.
- Score below 4: Ask a basic foundational question on the same topic.

Rules:
1. Do NOT repeat or rephrase the same question.
2. Do NOT mention the score or your reasoning.
3. Output ONLY the next interview question — a single sentence ending with a question mark.
"""
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0.3
    )
    return chat_completion.choices[0].message.content.strip()


def evaluate_answer(question, answer, role):
    word_count = len(answer.strip().split())

    if word_count < 4:
        return 2.0, 2.0, 2.0, 2.0

    lines_prompt = [
        "You are a professional interview evaluator for a " + str(role) + " role.",
        "",
        "Question: " + str(question),
        "Answer: " + str(answer),
        "",
        "Score the answer on three dimensions out of 10.",
        "Use the full 1-10 range based on quality:",
        "  10=perfect  8-9=excellent  6-7=good  4-5=average  2-3=weak  1=very poor",
        "",
        "A detailed relevant answer = 7-9. A decent answer = 5-6. A vague answer = 3-4.",
        "",
        "Reply in EXACTLY this format with no extra text:",
        "Relevance: X",
        "Clarity: X",
        "Depth: X"
    ]
    prompt = "\n".join(lines_prompt)

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.1,
            max_tokens=30
        ).choices[0].message.content.strip()

        def extract(label):
            m = re.search(label + r":\s*([0-9]+(?:\.[0-9]+)?)", response, re.IGNORECASE)
            return float(m.group(1)) if m else None

        relevance = extract("Relevance")
        clarity   = extract("Clarity")
        depth     = extract("Depth")

        if None in (relevance, clarity, depth):
            base = round(min(4.5 + word_count / 30.0, 8.0), 1)
            return base, base, base, base

        relevance = round(min(max(relevance, 1.0), 10.0), 1)
        clarity   = round(min(max(clarity,   1.0), 10.0), 1)
        depth     = round(min(max(depth,     1.0), 10.0), 1)

        # Minimum 3/10 guaranteed if answer is relevant (relevance >= 4)
        # This ensures a genuine, on-topic answer is never unfairly crushed
        if relevance >= 4.0:
            clarity   = max(clarity,   3.0)
            depth     = max(depth,     3.0)
            relevance = max(relevance, 3.0)

        final = round(min(max(relevance * 0.4 + clarity * 0.3 + depth * 0.3, 1.0), 10.0), 1)

        # Extra safety: long answer scored unfairly low -> blend with word-count heuristic
        if word_count > 20 and final < 3.0:
            heuristic = round(min(4.5 + word_count / 30.0, 7.0), 1)
            relevance = round((relevance + heuristic) / 2, 1)
            clarity   = round((clarity   + heuristic) / 2, 1)
            depth     = round((depth     + heuristic) / 2, 1)
            final     = round(relevance * 0.4 + clarity * 0.3 + depth * 0.3, 1)

        # Ensure final also reflects the minimum when answer is relevant
        if relevance >= 4.0:
            final = max(final, 3.0)

        return relevance, clarity, depth, final

    except Exception:
        base = round(min(4.5 + word_count / 30.0, 8.0), 1)
        return base, base, base, base


def generate_ai_feedback(question, answer, role, filler_count, sentiment, ai_score):
    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": f"""
You are a supportive, experienced interview coach giving feedback to a student practising for a {role} interview.

Question asked: {question}
Candidate's answer: {answer}
Score given: {ai_score}/10
Filler words detected: {filler_count}
Answer tone/sentiment: {sentiment}

Write structured, encouraging feedback with exactly these three sections:

Strengths:
(What did the candidate do well? Be specific and genuine.)

Areas to Improve:
(Give 2-3 concrete, actionable suggestions — not vague advice.)

💡 Pro Tip:
(One quick, practical tip to immediately improve their next answer.)

Keep it concise, warm, and motivating. Do not repeat the question text or the score number.
"""}],
            model="llama-3.1-8b-instant",
            temperature=0.4
        )
        return chat_completion.choices[0].message.content
    except:
        return "Feedback generation error. Please try again."


def generate_pdf_report(role, conversation, history):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(229, 9, 20)
    pdf.cell(0, 12, "AI Interview Analyzer - Full Report", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Role: {role}", ln=True, align="C")
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
    pdf.ln(6)

    # Summary
    if history:
        avg = round(sum(history) / len(history), 1)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, "Summary", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, f"Total Questions Answered: {len(history)}", ln=True)
        pdf.cell(0, 8, f"Average Score: {avg} / 10", ln=True)
        pdf.ln(4)

    # Per-question breakdown
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 10, "Question Breakdown", ln=True)
    pdf.ln(2)

    for i, entry in enumerate(conversation):
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(240, 240, 240)
        q = entry['question'][:100] + ('...' if len(entry['question']) > 100 else '')
        pdf.cell(0, 9, f"Q{i+1}: {q}", ln=True, fill=True)

        pdf.set_font("Arial", "", 10)
        ans = entry['answer'].encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 7, f"Answer: {ans[:300]}{'...' if len(ans) > 300 else ''}")

        pdf.set_font("Arial", "B", 10)
        pdf.cell(45, 7, f"Score: {entry['score']} / 10",             ln=False)
        pdf.cell(45, 7, f"Relevance: {entry.get('relevance','-')}/10", ln=False)
        pdf.cell(45, 7, f"Clarity: {entry.get('clarity','-')}/10",    ln=False)
        pdf.cell(0,  7, f"Depth: {entry.get('depth','-')}/10",        ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(50, 7, f"Filler Words: {entry.get('filler_count', 0)}", ln=False)
        pdf.cell(0,  7, f"Sentiment: {entry.get('sentiment', 'N/A')}",   ln=True)
        pdf.ln(3)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()
    os.unlink(tmp_path)
    return pdf_bytes


# ================================================================
#  PAGES
# ================================================================

def login():
    set_bg("image copy 2.png", 0.15)
    st.markdown("<style>section[data-testid='stSidebar']{display:none;}</style>",
                unsafe_allow_html=True)

    _, col, _ = st.columns([1, 3, 1])
    with col:
        img = get_base64_image("image.png")
        if img:
            st.markdown(f"""
            <div style="text-align:center; margin-bottom:0.5rem;">
                <img src="data:image/jpeg;base64,{img}" width="80"
                     style="border-radius:50%; border:3px solid #e50914;">
            </div>""", unsafe_allow_html=True)

        st.markdown("<h1 style='text-align:center;'> AI Interview Analyzer</h1>",
                    unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;'>Practice Smarter. Get Hired Faster.</p>",
                    unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center;'> Welcome Back</h2>",
                    unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        email    = st.text_input(" Email",    key="login_email")
        password = st.text_input(" Password", type="password", key="login_password")
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Sign In →", use_container_width=True):
            if not email or not password:
                st.warning("Please fill in all fields.")
            else:
                with st.spinner("Signing in..."):
                    user = login_user(email, password)
                if user:
                    st.session_state.logged_in    = True
                    st.session_state.user_name    = user[0]
                    st.session_state.user_email   = user[1]
                    st.session_state.current_page = "dashboard"
                    st.rerun()
                else:
                    st.error("❌ Invalid email or password.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;'>Don't have an account?</p>",
                    unsafe_allow_html=True)
        if st.button("Create Account →", use_container_width=True):
            st.session_state.auth_page = "signup"
            st.rerun()


def signup():
    set_bg("image copy 2.png", 0.15)
    st.markdown("<style>section[data-testid='stSidebar']{display:none;}</style>",
                unsafe_allow_html=True)

    _, col, _ = st.columns([1, 3, 1])
    with col:
        st.markdown("<h1 style='text-align:center;'>🎤 AI Interview Analyzer</h1>",
                    unsafe_allow_html=True)
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center;'> Create Account</h2>",
                    unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;'>Join and start practising today</p>",
                    unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        name     = st.text_input(" Full Name",        key="signup_name")
        email    = st.text_input(" Email",            key="signup_email")
        pwd      = st.text_input(" Password",         type="password", key="signup_password")
        cpwd     = st.text_input(" Confirm Password", type="password", key="signup_confirm")
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Create Account", use_container_width=True):
            if not name or not email or not pwd or not cpwd:
                st.warning("Please fill in all fields.")
            elif pwd != cpwd:
                st.error("Passwords do not match.")
            elif len(pwd) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with st.spinner("Creating account..."):
                    ok, msg = register_user(name, email, pwd)
                if ok:
                    st.success("✅ " + msg + " Please log in.")
                    st.session_state.auth_page = "login"
                    st.rerun()
                else:
                    st.error("❌ " + msg)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;'>Already have an account?</p>",
                    unsafe_allow_html=True)
        if st.button("← Back to Login", use_container_width=True):
            st.session_state.auth_page = "login"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def dashboard():
    set_bg("bg12.jpg", 0.45)

    name = st.session_state.user_name or st.session_state.user_email
    st.markdown(f"""
    <div class='hero'>
        <h1>Welcome, <span style='color:#e50914;'>{name}</span> </h1>
        <p>Your Interview Analytics Dashboard</p>
    </div>""", unsafe_allow_html=True)

    total       = get_total_interviews(st.session_state.user_email)
    overall_avg = get_overall_avg(st.session_state.user_email)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Interviews",  total)
    c2.metric("Overall Avg Score", f"{round(overall_avg, 1)} / 10")
    with c3:
        if   overall_avg >= 8: conf = "🟢 High"
        elif overall_avg >= 6: conf = "🟡 Moderate"
        elif overall_avg > 0:  conf = "🔴 Needs Work"
        else:                  conf = "—"
        st.metric("Confidence Level", conf)

    rows = get_interview_history(st.session_state.user_email)
    if rows:
        st.markdown("---")
        st.subheader("Recent Interview History")
        st.table([
            {"Date": r[3], "Role": r[0], "Avg Score": f"{r[1]} / 10", "Questions": r[2]}
            for r in rows
        ])
    else:
        st.info("No interview history yet. Start your first interview!")

    st.markdown("<br>", unsafe_allow_html=True)
    ca, cb, cc = st.columns([7, 1, 1])
    with ca:
        if st.button("🎤 Start New Interview", use_container_width=True):
            st.session_state.update({
                "current_page": "interview", "interview_started": False,
                "question": "", "conversation": [], "history": [],
                "show_evaluation": False
            })
            st.rerun()
    with cb:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    with cc:
        if st.button("Logout", use_container_width=True):
            st.session_state.update({
                "logged_in": False, "user_email": None,
                "user_name": None, "auth_page": "login",
                "current_page": "dashboard"
            })
            st.rerun()


def interview():
    set_bg("bg12.jpg", 0.45)

    img = get_base64_image("image.png")
    if img:
        st.markdown(f"""
        <div style="display:flex; justify-content:center; margin-top:0;">
            <img src="data:image/jpeg;base64,{img}" width="90"
                 style="border-radius:50%; border:3px solid #e50914;">
        </div>""", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center;'>🎤 AI Interview Analyzer</h1>",
                unsafe_allow_html=True)

    # ---------- Start Screen ----------
    if not st.session_state.interview_started:
        st.markdown("""
        <div style="background:rgba(28,28,28,0.92); padding:30px; border-radius:20px;
                    text-align:center; width:60%; margin:auto;
                    box-shadow:0 6px 18px rgba(0,0,0,0.5); color:white;">
            <h3>AI-Powered Interview Simulation</h3>
            <p>Real-time AI evaluation — scored fairly out of 10.</p>
            <ul style='text-align:left; color:#ccc; margin-top:1rem;'>
                <li> Answer by voice recording</li>
                <li> AI scores Relevance, Clarity &amp; Depth out of 10</li>
                <li> Countdown timer per question</li>
                <li> Filler word &amp; sentiment tracking</li>
                <li> Download PDF &amp; TXT reports</li>
            </ul>
        </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        _, mid, _ = st.columns([2, 1, 2])
        with mid:
            if st.button(" Start Interview", use_container_width=True):
                st.session_state.interview_started = True
                st.rerun()
        if st.button("⬅️ Back to Dashboard"):
            st.session_state.current_page = "dashboard"
            st.rerun()
        return

    # ---------- Settings ----------
    s1, s2 = st.columns(2)
    with s1:
        role = st.selectbox("Select Job Role:",
            ["Software Engineer", "Data Analyst", "HR Manager", "Marketing Executive"],
            key="selected_role")
        mode = st.radio("Interview Mode", ["Professional", "Friendly"], horizontal=True)
    with s2:
        st.session_state.max_questions = st.slider(
            "Number of Questions", 3, 15, value=st.session_state.max_questions)
        st.session_state.timer_seconds = st.select_slider(
            "Answer Time Limit (seconds)",
            options=[30, 60, 90, 120, 180], value=st.session_state.timer_seconds)

    # ---------- Progress ----------
    q_count = len(st.session_state.conversation)
    max_q   = st.session_state.max_questions
    st.markdown(f"**Question Progress: {q_count} / {max_q}**")
    st.progress(min(q_count / max_q, 1.0))

    if q_count >= max_q:
        st.success(f"✅ You've completed all {max_q} questions! Click below to save and return.")

    # Always visible finish bar — shown once at least 1 question is answered
    if q_count > 0:
        st.markdown("---")
        fc1, fc2 = st.columns([3, 1])
        with fc1:
            st.markdown(
                f"<div style='padding:0.6rem 1rem; background:rgba(229,9,20,0.1); "
                f"border-left:4px solid #e50914; border-radius:0 8px 8px 0; color:white;'>"
                f"<b>Questions answered: {q_count} / {max_q}</b> — "
                f"You can finish anytime and your progress will be saved.</div>",
                unsafe_allow_html=True
            )
        with fc2:
            if st.button(" Finish & Return to Dashboard", use_container_width=True, key="finish_top"):
                if st.session_state.history and st.session_state.user_email:
                    avg = sum(st.session_state.history) / len(st.session_state.history)
                    saved_role = st.session_state.get("selected_role", "General")
                    save_interview(st.session_state.user_email, saved_role, avg, len(st.session_state.history))
                st.session_state.update({
                    "total_interviews": st.session_state.total_interviews + 1,
                    "interview_started": False, "question": "",
                    "conversation": [], "history": [],
                    "show_evaluation": False, "timer_start": None,
                    "current_page": "dashboard"
                })
                st.rerun()
        st.markdown("---")

    if q_count >= max_q:
        return

    # ---------- Question ----------
    col1, _ = st.columns([3, 1])
    with col1:
        if not st.session_state.question:
            if st.button(" Generate First Question", key="first_q"):
                with st.spinner(" Generating question..."):
                    st.session_state.question = generate_question(role, mode, 0, [])
                st.session_state.timer_start = None
                st.rerun()
        else:
            if st.button("⏭ Next Question", key="next_q"):
                with st.spinner(" Generating next question..."):
                    st.session_state.question = generate_question(
                        role, mode,
                        len(st.session_state.conversation),
                        st.session_state.conversation)
                st.session_state.show_evaluation = False
                st.session_state.timer_start     = None
                st.rerun()

        if st.session_state.question:
            st.subheader("AI Generated Question:")
            st.markdown(f"<div class='question-box'>{st.session_state.question}</div>",
                        unsafe_allow_html=True)

            # Timer — live countdown using st.empty + loop rerun
            if not st.session_state.show_evaluation:
                if st.session_state.timer_start is None:
                    st.session_state.timer_start = time.time()

                elapsed   = int(time.time() - st.session_state.timer_start)
                remaining = max(st.session_state.timer_seconds - elapsed, 0)
                m, s = divmod(remaining, 60)
                color = "#e50914" if remaining <= 15 else "#f0a500" if remaining <= 30 else "#00c853"

                timer_slot = st.empty()
                timer_slot.markdown(
                    f"<div class='timer-box' style='color:{color};'>⏱ {m:02d}:{s:02d} remaining</div>",
                    unsafe_allow_html=True)

                if remaining <= 0:
                    st.warning(" Time's up! Please submit your answer.")
                else:
                    # Auto-rerun every second so the timer actually ticks live
                    time.sleep(1)
                    st.rerun()

            # Audio
            audio_file = st.audio_input("🎙 Record your answer")
            if audio_file is not None and not st.session_state.show_evaluation:
                st.audio(audio_file)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp.write(audio_file.read())
                    tmp_path = tmp.name

                recognizer = sr.Recognizer()
                try:
                    with st.spinner("🎙 Transcribing..."):
                        with sr.AudioFile(tmp_path) as src:
                            audio_data = recognizer.record(src)
                            text = recognizer.recognize_google(audio_data)

                    st.subheader(" Transcribed Answer:")
                    st.write(text)

                    fillers      = ["um", "uh", "like", "you know", "actually", "basically"]
                    filler_count = sum(text.lower().count(w) for w in fillers)
                    polarity     = TextBlob(text).sentiment.polarity
                    sentiment    = "Positive" if polarity > 0 else "Negative" if polarity < 0 else "Neutral"

                    with st.spinner(" Evaluating your answer..."):
                        relevance, clarity, depth, ai_score = evaluate_answer(
                            st.session_state.question, text, role)

                    st.session_state.history.append(ai_score)
                    st.session_state.conversation.append({
                        "question": st.session_state.question, "answer": text,
                        "score": ai_score, "relevance": relevance,
                        "clarity": clarity, "depth": depth,
                        "filler_count": filler_count, "sentiment": sentiment
                    })
                    st.session_state.show_evaluation = True
                    st.rerun()

                except Exception as e:
                    st.error(f"Speech Recognition Error: {e}")

            # Evaluation results
            if st.session_state.show_evaluation and st.session_state.conversation:
                last         = st.session_state.conversation[-1]
                score        = last["score"]
                relevance    = last["relevance"]
                clarity      = last["clarity"]
                depth        = last["depth"]
                filler_count = last["filler_count"]
                sentiment    = last["sentiment"]

                st.write("---")
                st.subheader(" Detailed Evaluation")

                def sc(v):
                    return "#00c853" if v >= 7.5 else "#f0a500" if v >= 5.5 else "#e50914"

                c1, c2, c3, c4, c5 = st.columns(5)
                for col, lbl, val in [(c1,"Relevance",relevance),(c2,"Clarity",clarity),(c3,"Depth",depth)]:
                    col.markdown(f"""
                    <div class='score-card'>
                        <div class='score-number' style='color:{sc(val)};'>{val}</div>
                        <div class='score-label'>{lbl} / 10</div>
                    </div>""", unsafe_allow_html=True)

                c4.markdown(f"""
                <div class='score-card'>
                    <div class='score-number' style='color:#aaa;'>{filler_count}</div>
                    <div class='score-label'>🗣 Filler Words</div>
                </div>""", unsafe_allow_html=True)

                emoji = "😊" if sentiment=="Positive" else "😐" if sentiment=="Neutral" else "😟"
                c5.markdown(f"""
                <div class='score-card'>
                    <div class='score-number' style='font-size:2rem;'>{emoji}</div>
                    <div class='score-label'>{sentiment}</div>
                </div>""", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                st.subheader(" Final Score")
                if   score >= 8:  st.success(f" Excellent Performance: **{score} / 10**")
                elif score >= 6:  st.info(   f" Good Performance: **{score} / 10**")
                elif score >= 4:  st.warning(f" Fair — Keep Practising: **{score} / 10**")
                else:             st.error(  f" Needs Improvement: **{score} / 10**")
                st.progress(score / 10)

                st.write("---")
                st.subheader(" AI Feedback")
                with st.spinner(" Generating feedback..."):
                    feedback = generate_ai_feedback(
                        last["question"], last["answer"],
                        role, filler_count, sentiment, score)
                st.info(feedback)

                st.write("---")
                st.subheader("Performance History")
                run_avg = round(sum(st.session_state.history) / len(st.session_state.history), 1)
                st.write(f"Attempts: **{len(st.session_state.history)}**  |  "
                         f"Running Average: **{run_avg} / 10**")
                st.line_chart(st.session_state.history)

                report_txt = (
                    f"AI Interview Report\nRole: {role}\n"
                    f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"Question: {last['question']}\n\n"
                    f"Final Score : {score} / 10\n"
                    f"Relevance   : {relevance} / 10\n"
                    f"Clarity     : {clarity} / 10\n"
                    f"Depth       : {depth} / 10\n"
                    f"Filler Words: {filler_count}\n"
                    f"Sentiment   : {sentiment}\n\n"
                    f"Feedback:\n{feedback}\n"
                )
                # Build full analysis TXT across all answers
                analysis_lines = [
                    "AI Interview - Full Analysis Report",
                    "Role: " + str(role),
                    "Date: " + datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Total Questions Answered: " + str(len(st.session_state.conversation)),
                    "Running Average Score: " + str(run_avg) + " / 10",
                    "",
                    "=" * 50,
                    "",
                ]
                for idx, entry in enumerate(st.session_state.conversation):
                    analysis_lines += [
                        "Q" + str(idx + 1) + ": " + entry["question"],
                        "Answer     : " + entry["answer"],
                        "Score      : " + str(entry["score"]) + " / 10",
                        "Relevance  : " + str(entry.get("relevance", "-")) + " / 10",
                        "Clarity    : " + str(entry.get("clarity", "-")) + " / 10",
                        "Depth      : " + str(entry.get("depth", "-")) + " / 10",
                        "Filler Words: " + str(entry.get("filler_count", 0)),
                        "Sentiment  : " + str(entry.get("sentiment", "N/A")),
                        "",
                        "-" * 50,
                        "",
                    ]
                analysis_txt = "\n".join(analysis_lines)

                st.write("---")
                st.subheader("📥 Download Reports")
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.download_button(
                        " Feedback (TXT)",
                        report_txt,
                        file_name="Interview_Feedback.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                with d2:
                    st.download_button(
                        "📊 Full Analysis (TXT)",
                        analysis_txt,
                        file_name="Interview_Analysis.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                with d3:
                    with st.spinner(" Generating PDF..."):
                        pdf_b = generate_pdf_report(
                            role, st.session_state.conversation, st.session_state.history)
                    st.download_button(
                        "📥 PDF Report",
                        pdf_b,
                        file_name="Interview_Report.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

    # ---------- End Interview ----------
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(" End Interview", key="end_btn"):
        st.success("Interview Completed!")
        st.balloons()
        if st.session_state.history and st.session_state.user_email:
            avg = sum(st.session_state.history) / len(st.session_state.history)
            saved_role = st.session_state.get("selected_role", "General")
            result = save_interview(st.session_state.user_email, saved_role, avg, len(st.session_state.history))
            if result:
                st.success(f"✅ Interview saved to your account! Avg Score: {round(avg,1)}/10")
        st.session_state.update({
            "total_interviews": st.session_state.total_interviews + 1,
            "interview_started": False, "question": "",
            "conversation": [], "history": [],
            "show_evaluation": False, "timer_start": None,
            "current_page": "dashboard"
        })
        st.rerun()

#  APP FLOW
if not st.session_state.logged_in:
    if st.session_state.auth_page == "signup":
        signup()
    else:
        login()
else:
    if st.session_state.current_page == "dashboard":
        dashboard()
    elif st.session_state.current_page == "interview":
        interview()