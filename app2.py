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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO interview_history (email, role, avg_score, total_questions, date) VALUES (?, ?, ?, ?, ?)",
        (email, role, round(avg_score, 2), total_questions, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

def get_interview_history(email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, avg_score, total_questions, date FROM interview_history WHERE email=? ORDER BY id DESC LIMIT 10",
        (email,)
    )
    rows = c.fetchall()
    conn.close()
    return rows  # list of (role, avg_score, total_questions, date)

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
    return user  # returns (name, email) or None

init_db()

# ---------------- SESSION STATE ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "dashboard"
if "auth_page" not in st.session_state:
    st.session_state.auth_page = "login"
if "total_interviews" not in st.session_state:
    st.session_state.total_interviews = 0
if "history" not in st.session_state:
    st.session_state.history = []
if "conversation" not in st.session_state:
    st.session_state.conversation = []
if "question" not in st.session_state:
    st.session_state.question = ""
if "interview_started" not in st.session_state:
    st.session_state.interview_started = False
if "show_evaluation" not in st.session_state:
    st.session_state.show_evaluation = False
if "max_questions" not in st.session_state:
    st.session_state.max_questions = 10
if "timer_seconds" not in st.session_state:
    st.session_state.timer_seconds = 120
if "timer_start" not in st.session_state:
    st.session_state.timer_start = None

# ---------------- GLOBAL STYLE ----------------
st.markdown("""
<style>
/* ---- Base ---- */
html, body, [class*="css"] {
    font-family: 'Segoe UI', sans-serif;
}

/* ---- Navbar ---- */
.navbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(20,20,20,0.92);
    padding: 0.75rem 2rem;
    border-radius: 14px;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 24px rgba(0,0,0,0.5);
    backdrop-filter: blur(8px);
}
.navbar-brand {
    font-size: 1.4rem;
    font-weight: 800;
    color: white;
    letter-spacing: 0.5px;
}
.navbar-brand span { color: #e50914; }
.navbar-user {
    font-size: 0.95rem;
    color: #cccccc;
}

/* ---- Hero ---- */
.hero {
    text-align: center;
    padding: 3rem 1rem 1.5rem 1rem;
}
.hero h1 {
    font-size: clamp(2rem, 5vw, 3.5rem);
    color: white;
    font-weight: 900;
    margin-bottom: 0.4rem;
}
.hero p {
    color: #bbbbbb;
    font-size: 1.15rem;
}

/* ---- Cards ---- */
.card {
    background: rgba(28,28,28,0.92);
    padding: 2rem;
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.55);
    backdrop-filter: blur(6px);
    margin-bottom: 1rem;
}
.stat-card {
    background: rgba(28,28,28,0.88);
    border: 1px solid rgba(229,9,20,0.25);
    padding: 1.4rem;
    border-radius: 14px;
    text-align: center;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}

/* ---- Buttons ---- */
.stButton > button {
    background: linear-gradient(135deg, #e50914, #b20710);
    color: white !important;
    font-weight: 700;
    border-radius: 10px;
    padding: 0.55rem 1.4rem;
    border: none !important;
    font-size: 0.95rem;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    box-shadow: 0 4px 14px rgba(229,9,20,0.35);
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(229,9,20,0.5);
}
.stButton > button:active {
    transform: translateY(0px);
}

/* ---- Inputs ---- */
.stTextInput > div > input,
.stSelectbox > div,
.stSlider {
    border-radius: 10px !important;
}

/* ---- Metrics ---- */
[data-testid="metric-container"] {
    background: rgba(28,28,28,0.85);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    box-shadow: 0 4px 14px rgba(0,0,0,0.3);
}

/* ---- Divider ---- */
hr { border-color: rgba(255,255,255,0.1) !important; }

/* ---- Question box ---- */
.question-box {
    background: rgba(229,9,20,0.08);
    border-left: 4px solid #e50914;
    padding: 1rem 1.4rem;
    border-radius: 0 12px 12px 0;
    font-size: 1.15rem;
    font-weight: 600;
    color: white;
    margin-bottom: 1rem;
}

/* ---- Timer box ---- */
.timer-box {
    display: inline-block;
    padding: 0.4rem 1.2rem;
    border-radius: 30px;
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
    border: 2px solid currentColor;
}

/* ---- Score bar ---- */
.stProgress > div > div {
    background: linear-gradient(90deg, #e50914, #ff6b35) !important;
    border-radius: 8px !important;
}

/* ---- History table ---- */
.stTable { border-radius: 12px; overflow: hidden; }

/* ---- Mobile ---- */
@media (max-width: 768px) {
    .navbar { flex-direction: column; gap: 0.5rem; text-align: center; }
    .hero h1 { font-size: 2rem; }
}
</style>
""", unsafe_allow_html=True)

# ---------------- BACKGROUND IMAGE ----------------
def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except FileNotFoundError:
        return None

bg_base64 = get_base64_image("image copy.png")
if bg_base64:
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/jpg;base64,{bg_base64}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.35);
            z-index: -1;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ---------------- GROQ CLIENT (via st.secrets) ----------------
client = Groq(api_key="")

# ---------------- FUNCTIONS ----------------

def generate_question(role, mode, question_count, conversation=None):
    if mode == "Friendly":
        tone_instruction = "Generate one friendly, warm and conversational interview question. Keep it supportive and approachable."
    else:
        tone_instruction = "Generate one professional and high-pressure interview question."

    if question_count == 0:
        prompt = f"""
        {tone_instruction}
        You are a professional interviewer.
        Ask the candidate to introduce themselves.
        Return ONLY the question.
        """
    elif question_count == 1:
        prompt = f"""
        {tone_instruction}
        You are a professional interviewer.
        Generate ONE technical interview question for a {role}.
        The question must be relevant to real-world job responsibilities.
        Return ONLY the question.
        """
    else:
        last_entry = conversation[-1]
        previous_question = last_entry["question"]
        previous_answer = last_entry["answer"]
        score = last_entry["score"]

        prompt = f"""
        {tone_instruction}

        Previous Question: {previous_question}
        Candidate Answer: {previous_answer}
        Score: {score}/100

        Rules:
        1. Stay in same topic.
        2. If score > 75 increase difficulty.
        3. If score < 50 simplify.
        4. Do not repeat similar question.
        5. Ask only ONE question.

        IMPORTANT:
        - Do NOT explain reasoning.
        - Do NOT mention score.
        - Do NOT add commentary.
        - Output ONLY the final interview question.
        - The response must be a single question sentence.

        Generate the next question now.
        """

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0.3
    )
    return chat_completion.choices[0].message.content.strip()


def evaluate_answer(question, answer, role):
    try:
        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": f"""
Question:
{question}

Answer:
{answer}

Return strictly:

Relevance: <number>
Clarity: <number>
Depth: <number>
Final: <number>
"""
            }],
            model="llama-3.1-8b-instant",
        )
        response = chat_completion.choices[0].message.content
        relevance = int(re.search(r"Relevance:\s*(\d+)", response).group(1))
        clarity = int(re.search(r"Clarity:\s*(\d+)", response).group(1))
        depth = int(re.search(r"Depth:\s*(\d+)", response).group(1))
        final_score = int(re.search(r"Final:\s*(\d+)", response).group(1))
        return relevance, clarity, depth, final_score
    except:
        return 50, 50, 50, 50


def generate_ai_feedback(question, answer, role, filler_count, sentiment, ai_score):
    try:
        chat_completion = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": f"""
Question: {question}
Answer: {answer}
Score: {ai_score}/100

Give structured feedback.
"""
            }],
            model="llama-3.1-8b-instant",
        )
        return chat_completion.choices[0].message.content
    except:
        return "Feedback generation error"


def generate_pdf_report(role, conversation, history):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(229, 9, 20)
    pdf.cell(0, 12, "AI Interview Analyzer - Report", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Role: {role}", ln=True, align="C")
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
    pdf.ln(6)

    # Summary
    if history:
        avg = round(sum(history) / len(history), 2)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, "Summary", ln=True)
        pdf.set_font("Arial", "", 11)
        pdf.cell(0, 8, f"Total Questions Answered: {len(history)}", ln=True)
        pdf.cell(0, 8, f"Average Score: {avg}/100", ln=True)
        pdf.ln(4)

    # Per-question breakdown
    pdf.set_font("Arial", "B", 13)
    pdf.cell(0, 10, "Question Breakdown", ln=True)
    pdf.ln(2)

    for i, entry in enumerate(conversation):
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 9, f"Q{i+1}: {entry['question'][:100]}{'...' if len(entry['question']) > 100 else ''}", ln=True, fill=True)

        pdf.set_font("Arial", "", 10)
        # Encode to latin-1 safely
        answer_text = entry['answer'].encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 7, f"Answer: {answer_text[:300]}{'...' if len(answer_text) > 300 else ''}")

        pdf.set_font("Arial", "B", 10)
        pdf.cell(40, 7, f"Score: {entry['score']}/100", ln=False)
        pdf.cell(40, 7, f"Relevance: {entry['relevance']}/100", ln=False)
        pdf.cell(40, 7, f"Clarity: {entry['clarity']}/100", ln=False)
        pdf.cell(0, 7, f"Depth: {entry['depth']}/100", ln=True)
        pdf.set_font("Arial", "", 10)
        pdf.cell(50, 7, f"Filler Words: {entry['filler_count']}", ln=False)
        pdf.cell(0, 7, f"Sentiment: {entry['sentiment']}", ln=True)
        pdf.ln(3)

    # Save to temp file and return bytes
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()
    os.unlink(tmp_path)
    return pdf_bytes


# ---------------- NAVBAR ----------------
def render_navbar(show_user=True):
    user_html = ""
    if show_user and st.session_state.user_name:
        user_html = f"<span class='navbar-user'>👤 {st.session_state.user_name}</span>"
    st.markdown(f"""
    <div class='navbar'>
        <div class='navbar-brand'>🎤 AI <span>Interview</span> Analyzer</div>
        {user_html}
    </div>
    """, unsafe_allow_html=True)


# ---------------- LOGIN PAGE ----------------
def login():
    render_navbar(show_user=False)
    col1, col2, col3 = st.columns([2, 3, 2])
    with col2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center; color:white;'>🔐 Welcome Back</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#aaa;'>Practice Smarter. Get Hired Faster.</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        email = st.text_input("📧 Email", key="login_email")
        password = st.text_input("🔑 Password", type="password", key="login_password")
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Sign In →", use_container_width=True):
            if not email or not password:
                st.warning("Please fill in all fields.")
            else:
                with st.spinner("Signing in..."):
                    user = login_user(email, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user_name = user[0]
                    st.session_state.user_email = user[1]
                    st.session_state.current_page = "dashboard"
                    st.rerun()
                else:
                    st.error("❌ Invalid email or password.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#aaa;'>Don't have an account?</p>", unsafe_allow_html=True)
        if st.button("Create Account →", use_container_width=True):
            st.session_state.auth_page = "signup"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------- SIGNUP PAGE ----------------
def signup():
    render_navbar(show_user=False)
    col1, col2, col3 = st.columns([2, 3, 2])
    with col2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align:center; color:white;'>📝 Create Account</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#aaa;'>Join and start practicing today</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        name = st.text_input("👤 Full Name", key="signup_name")
        email = st.text_input("📧 Email", key="signup_email")
        password = st.text_input("🔑 Password", type="password", key="signup_password")
        confirm_password = st.text_input("🔑 Confirm Password", type="password", key="signup_confirm")
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("Create Account", use_container_width=True):
            if not name or not email or not password or not confirm_password:
                st.warning("Please fill in all fields.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with st.spinner("Creating account..."):
                    success, message = register_user(name, email, password)
                if success:
                    st.success("✅ " + message + " Please log in.")
                    st.session_state.auth_page = "login"
                    st.rerun()
                else:
                    st.error("❌ " + message)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:#aaa;'>Already have an account?</p>", unsafe_allow_html=True)
        if st.button("← Back to Login", use_container_width=True):
            st.session_state.auth_page = "login"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ---------------- DASHBOARD PAGE ----------------
def dashboard():
    render_navbar()
    display_name = st.session_state.user_name or st.session_state.user_email
    st.markdown(f"""
    <div class='hero'>
        <h1>Welcome, <span style='color:#e50914;'>{display_name}</span> 👋</h1>
        <p>Your Interview Analytics Dashboard</p>
    </div>
    """, unsafe_allow_html=True)

    # Load persistent stats from DB
    total = get_total_interviews(st.session_state.user_email)
    overall_avg = get_overall_avg(st.session_state.user_email)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Interviews", total)
    with col2:
        st.metric("Overall Avg Score", f"{round(overall_avg, 2)}%")
    with col3:
        if overall_avg >= 80:
            confidence = "🟢 High"
        elif overall_avg >= 60:
            confidence = "🟡 Moderate"
        elif overall_avg > 0:
            confidence = "🔴 Low"
        else:
            confidence = "—"
        st.metric("Confidence Level", confidence)

    # Interview history table
    history_rows = get_interview_history(st.session_state.user_email)
    if history_rows:
        st.markdown("---")
        st.subheader("📋 Recent Interview History")
        history_data = [
            {"Date": r[3], "Role": r[0], "Avg Score": f"{r[1]}/100", "Questions": r[2]}
            for r in history_rows
        ]
        st.table(history_data)
    else:
        st.info("No interview history yet. Start your first interview!")

    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🎤 Start New Interview", use_container_width=True):
            st.session_state.current_page = "interview"
            st.session_state.interview_started = False
            st.session_state.question = ""
            st.session_state.conversation = []
            st.session_state.history = []
            st.session_state.show_evaluation = False
            st.rerun()
    with col_b:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_email = None
            st.session_state.user_name = None
            st.session_state.current_page = "dashboard"
            st.session_state.auth_page = "login"
            st.rerun()


# ---------------- INTERVIEW PAGE ----------------
def interview():
    render_navbar()
    img_base64 = get_base64_image("image.png")

    if not st.session_state.interview_started:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if img_base64:
                st.markdown(f"""
                <div style="text-align:center; margin-bottom:1rem;">
                    <img src="data:image/jpeg;base64,{img_base64}" width="100" style="border-radius:50%; border:3px solid #e50914;">
                </div>
                """, unsafe_allow_html=True)
            st.markdown("""
            <div class='card' style='text-align:center;'>
                <h2 style='color:white;'>🚀 AI Interview Simulation</h2>
                <p style='color:#aaa;'>Adaptive questions • Real-time scoring • Instant feedback</p>
                <ul style='text-align:left; color:#ccc; margin-top:1rem;'>
                    <li>🎙 Answer by voice recording</li>
                    <li>🧠 AI evaluates relevance, clarity & depth</li>
                    <li>⏱ Timed responses to simulate real interviews</li>
                    <li>📥 Download your full PDF report</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🚀 Start Interview", use_container_width=True):
                st.session_state.interview_started = True
                st.rerun()
            if st.button("⬅️ Back to Dashboard", use_container_width=True):
                st.session_state.current_page = "dashboard"
                st.rerun()
        return

    # -------- Interview Settings --------
    settings_col1, settings_col2 = st.columns(2)
    with settings_col1:
        role = st.selectbox("Select Job Role:",
            ["Software Engineer", "Data Analyst", "HR Manager", "Marketing Executive"])
        mode = st.radio("Interview Mode", ["Professional", "Friendly"], horizontal=True)
    with settings_col2:
        st.session_state.max_questions = st.slider(
            "Number of Questions", min_value=3, max_value=15,
            value=st.session_state.max_questions
        )
        st.session_state.timer_seconds = st.select_slider(
            "Answer Time Limit (seconds)",
            options=[30, 60, 90, 120, 180],
            value=st.session_state.timer_seconds
        )

    # -------- Progress Bar --------
    q_count = len(st.session_state.conversation)
    max_q = st.session_state.max_questions
    st.markdown(f"**Question Progress: {q_count} / {max_q}**")
    st.progress(min(q_count / max_q, 1.0))

    # Auto-end when max questions reached
    if q_count >= max_q:
        st.success(f"✅ You've completed all {max_q} questions!")
        if st.button("🏁 Finish & Go to Dashboard"):
            if st.session_state.history:
                avg = sum(st.session_state.history) / len(st.session_state.history)
                save_interview(st.session_state.user_email, role, avg, len(st.session_state.history))
            st.session_state.total_interviews += 1
            st.session_state.interview_started = False
            st.session_state.question = ""
            st.session_state.conversation = []
            st.session_state.history = []
            st.session_state.show_evaluation = False
            st.session_state.timer_start = None
            st.session_state.current_page = "dashboard"
            st.rerun()
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        if not st.session_state.question:
            if st.button("🎯 Generate First Question", key="first_q"):
                with st.spinner("🤖 Generating question..."):
                    st.session_state.question = generate_question(
                        role, mode, len(st.session_state.conversation), st.session_state.conversation
                    )
                st.session_state.timer_start = None
                st.rerun()
        else:
            if st.button("⏭ Next Question", key="next_q"):
                with st.spinner("🤖 Generating next question..."):
                    st.session_state.question = generate_question(
                        role, mode, len(st.session_state.conversation), st.session_state.conversation
                    )
                st.session_state.show_evaluation = False
                st.session_state.timer_start = None
                st.rerun()

        if st.session_state.question:
            st.subheader("AI Generated Question:")
            st.markdown(
                f"<div class='question-box'>{st.session_state.question}</div>",
                unsafe_allow_html=True
            )

            # -------- Countdown Timer --------
            if not st.session_state.show_evaluation:
                if st.session_state.timer_start is None:
                    st.session_state.timer_start = time.time()

                elapsed = int(time.time() - st.session_state.timer_start)
                remaining = max(st.session_state.timer_seconds - elapsed, 0)
                mins, secs = divmod(remaining, 60)

                timer_color = "#e50914" if remaining <= 15 else "#f0a500" if remaining <= 30 else "#00c853"
                st.markdown(
                    f"<div class='timer-box' style='color:{timer_color};'>"
                    f"⏱ {mins:02d}:{secs:02d} remaining</div>",
                    unsafe_allow_html=True
                )
                if remaining <= 0:
                    st.warning("⏰ Time's up! Please submit your answer.")

            audio_file = st.audio_input("🎙 Record your answer")
            if audio_file is not None and not st.session_state.show_evaluation:
                st.audio(audio_file)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                    temp_audio.write(audio_file.read())
                    temp_audio_path = temp_audio.name

                recognizer = sr.Recognizer()
                try:
                    with st.spinner("🎙 Transcribing your answer..."):
                        with sr.AudioFile(temp_audio_path) as source:
                            audio_data = recognizer.record(source)
                            text = recognizer.recognize_google(audio_data)

                    st.subheader("📝 Transcribed Answer:")
                    st.write(text)

                    clean_text = text.lower()
                    filler_words = ["um", "uh", "like", "you know", "actually", "basically"]
                    filler_count = sum(clean_text.count(word) for word in filler_words)

                    blob = TextBlob(text)
                    sentiment_score = blob.sentiment.polarity
                    sentiment = "Positive" if sentiment_score > 0 else "Negative" if sentiment_score < 0 else "Neutral"

                    with st.spinner("🧠 Evaluating your answer..."):
                        relevance, clarity, depth, ai_score = evaluate_answer(
                            st.session_state.question, text, role
                        )

                    st.session_state.history.append(ai_score)
                    st.session_state.conversation.append({
                        "question": st.session_state.question,
                        "answer": text,
                        "score": ai_score,
                        "relevance": relevance,
                        "clarity": clarity,
                        "depth": depth,
                        "filler_count": filler_count,
                        "sentiment": sentiment
                    })
                    st.session_state.show_evaluation = True
                    st.rerun()

                except Exception as e:
                    st.error(f"Speech Recognition Error: {e}")

            if st.session_state.show_evaluation and len(st.session_state.conversation) > 0:
                last = st.session_state.conversation[-1]
                stored_score = last["score"]
                relevance = last["relevance"]
                clarity = last["clarity"]
                depth = last["depth"]
                filler_count = last["filler_count"]
                sentiment = last["sentiment"]

                st.write("---")
                st.subheader("🎯 Detailed Evaluation")

                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Relevance", f"{relevance}/100")
                col2.metric("Clarity", f"{clarity}/100")
                col3.metric("Depth", f"{depth}/100")
                col4.metric("🗣 Filler Words", filler_count)
                sentiment_emoji = "😊" if sentiment == "Positive" else "😐" if sentiment == "Neutral" else "😟"
                col5.metric("Sentiment", f"{sentiment_emoji} {sentiment}")

                st.subheader("🏆 Final Interview Score")
                if stored_score >= 80:
                    st.success(f"Excellent Performance: {stored_score}/100")
                elif stored_score >= 60:
                    st.info(f"Good Performance: {stored_score}/100")
                else:
                    st.error(f"Needs Improvement: {stored_score}/100")

                st.progress(stored_score / 100)

                st.write("---")
                st.subheader("🤖 AI Feedback")

                with st.spinner("💬 Generating AI feedback..."):
                    feedback = generate_ai_feedback(
                        last["question"], last["answer"], role, filler_count, sentiment, stored_score
                    )
                st.info(feedback)

                st.write("---")
                st.subheader("📈 Performance History")
                avg_score = sum(st.session_state.history) / len(st.session_state.history)
                st.write(f"Attempts: {len(st.session_state.history)}")
                st.write(f"Average Score: {round(avg_score, 2)}")
                st.line_chart(st.session_state.history)

                report_text = f"""
Interview Report

Role: {role}
Question:
{last["question"]}

Final Score: {stored_score}/100
Relevance: {relevance}
Clarity: {clarity}
Depth: {depth}
Filler Words: {filler_count}
Sentiment: {sentiment}

Feedback:
{feedback}
"""
                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    st.download_button(
                        "📄 Download TXT Report",
                        report_text,
                        file_name="Interview_Report.txt",
                        mime="text/plain"
                    )
                with dl_col2:
                    with st.spinner("📄 Generating PDF..."):
                        pdf_bytes = generate_pdf_report(role, st.session_state.conversation, st.session_state.history)
                    st.download_button(
                        "📥 Download PDF Report",
                        pdf_bytes,
                        file_name="Interview_Report.pdf",
                        mime="application/pdf"
                    )

    if st.button("🏁 End Interview", key="end_btn"):
        st.success("Interview Completed!")
        st.balloons()
        if st.session_state.history:
            avg = sum(st.session_state.history) / len(st.session_state.history)
            save_interview(st.session_state.user_email, role, avg, len(st.session_state.history))
        st.session_state.total_interviews += 1
        st.session_state.interview_started = False
        st.session_state.question = ""
        st.session_state.conversation = []
        st.session_state.history = []
        st.session_state.show_evaluation = False
        st.session_state.timer_start = None
        st.session_state.current_page = "dashboard"
        st.rerun()


# ---------------- APP FLOW ----------------
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