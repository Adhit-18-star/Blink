from fastapi import FastAPI, Request, Form
from fastapi import File, UploadFile
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import base64
import uuid
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print("DATABASE_URL =", DATABASE_URL)

def get_conn():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL not found in .env")
    return psycopg2.connect(DATABASE_URL)

app = FastAPI(debug=True)

os.makedirs("uploads", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key="blink-secret-key")

templates = Jinja2Templates(directory="templates")


 # ---------------- DB ----------------
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # ---------------- USERS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    # Add new columns if they don't exist
    try:
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS blinks INTEGER DEFAULT 0
        """)
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS gems INTEGER DEFAULT 0
        """)
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS coins INTEGER DEFAULT 0
        """)
    except:
        conn.rollback()

    # ---------------- FRIENDS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friends(
            id SERIAL PRIMARY KEY,
            sender TEXT,
            receiver TEXT,
            status TEXT
        )
    """)

    # ---------------- MESSAGES ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages(
            id SERIAL PRIMARY KEY,
            sender TEXT,
            receiver TEXT,
            message TEXT,
            timestamp TEXT
        )
    """)

    try:
        cur.execute("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS timestamp TEXT
        """)
    except:
        conn.rollback()

    # ---------------- DETECTIVE CASES ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS detective_cases(
            id SERIAL PRIMARY KEY,
            title TEXT,
            story TEXT,
            clues TEXT,
            suspects TEXT,
            culprit TEXT,
            difficulty TEXT,
            xp INTEGER,
            required_xp INTEGER DEFAULT 0
        )
    """)

    try:
        cur.execute("""
            ALTER TABLE detective_cases
            ADD COLUMN IF NOT EXISTS required_xp INTEGER DEFAULT 0
        """)
    except:
        conn.rollback()

    # ---------------- DETECTIVE PROGRESS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS detective_progress(
            id SERIAL PRIMARY KEY,
            username TEXT,
            case_id INTEGER,
            xp INTEGER
        )
    """)

    # ---------------- PLAYER REWARDS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS player_rewards(
            username TEXT PRIMARY KEY,
            xp INTEGER DEFAULT 0,
            gems INTEGER DEFAULT 0,
            blinks INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            login_streak INTEGER DEFAULT 0,
            total_login_days INTEGER DEFAULT 0,
            last_login DATE,
            hundred_day_claimed BOOLEAN DEFAULT FALSE
        )
    """)

    # ---------------- REWARD HISTORY ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reward_history(
            id SERIAL PRIMARY KEY,
            username TEXT,
            reward_type TEXT,
            xp INTEGER DEFAULT 0,
            gems INTEGER DEFAULT 0,
            blinks INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------- DETECTIVE ATTEMPTS ----------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS detective_attempts(
            username TEXT,
            case_id INTEGER,
            attempts INTEGER DEFAULT 0,
            PRIMARY KEY(username, case_id)
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()

 # ---------------- HOME ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
     return RedirectResponse("/login", status_code=303)


 # ---------------- LOGIN ----------------
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
     return templates.TemplateResponse(
         "register.html",
         {"request": request}
     )
    
@app.post("/register")
def register(
     username: str = Form(...),
     password: str = Form(...)
 ):
     conn = get_conn()
     cur = conn.cursor()

     try:
         cur.execute(
             "INSERT INTO users(username,password) VALUES(%s,%s)",
             (username, password)
         )
         conn.commit()
         conn.close()
         return RedirectResponse("/login", status_code=303)

     except:
         conn.close()
         return HTMLResponse("Username already exists")

@app.get("/login")
def login_page(request: Request):
     return templates.TemplateResponse(
         request=request,
        name="login.html"
     )

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
     conn = get_conn()
     cur = conn.cursor()

     cur.execute(
         "SELECT username FROM users WHERE username=%s AND password=%s",
         (username, password)
     )

     user = cur.fetchone()
     conn.close()

     if not user:
         return HTMLResponse("Invalid login ❌", status_code=401)

     request.session["username"] = username

     return RedirectResponse("/dashboard", status_code=303)


 # ---------------- DASHBOARD ----------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
     username = request.session.get("username")
     if not username:
         return RedirectResponse("/login")

     return templates.TemplateResponse("dashboard.html", {
         "request": request,
         "username": username
     })


 # ---------------- USERS ----------------
@app.get("/users", response_class=HTMLResponse)
def users(request: Request):
     username = request.session.get("username")
     if not username:
         return RedirectResponse("/login")

     conn = get_conn()
     cur = conn.cursor()

     cur.execute("SELECT username FROM users WHERE username != %s", (username,))
     users = cur.fetchall()
     conn.close()

     return templates.TemplateResponse("users.html", {
         "request": request,
         "users": users
     })


 # ---------------- FRIEND REQUEST ----------------
@app.post("/send-request")
def send_request(request: Request, receiver: str = Form(...)):
     sender = request.session.get("username")
     if not sender:
         return RedirectResponse("/login")

     conn = get_conn()
     cur = conn.cursor()

     cur.execute(
         "INSERT INTO friends(sender, receiver, status) VALUES (%s, %s, 'pending')",
         (sender, receiver)
     )

     conn.commit()
     conn.close()

     return RedirectResponse("/users", status_code=303)


 # ---------------- REQUESTS ----------------
@app.get("/requests", response_class=HTMLResponse)
def requests_page(request: Request):
     username = request.session.get("username")
     if not username:
         return RedirectResponse("/login")

     conn = get_conn()
     cur = conn.cursor()

     cur.execute(
         "SELECT id, sender FROM friends WHERE receiver=%s AND status='pending'",
         (username,)
     )

     requests = cur.fetchall()
     conn.close()

     return templates.TemplateResponse("requests.html", {
         "request": request,
         "requests": requests
     })


 # ---------------- ACCEPT REQUEST ----------------
@app.post("/accept-request")
def accept(request_id: int = Form(...)):
     conn = get_conn()
     cur = conn.cursor()

     cur.execute("UPDATE friends SET status='accepted' WHERE id=%s", (request_id,))

     conn.commit()
     conn.close()

     return RedirectResponse("/requests", status_code=303)


 # ---------------- CHAT LIST ----------------
@app.get("/friends", response_class=HTMLResponse)
def friends(request: Request):
    username = request.session.get("username")
    if not username:
         return RedirectResponse("/login", status_code=303)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
         SELECT sender, receiver
         FROM friends
         WHERE status='accepted'
         AND (sender=%s OR receiver=%s)
     """, (username, username))

    data = cur.fetchall()
    conn.close()

    friend_set = set()

    for s, r in data:
         friend_set.add(r if s == username else s)

    return templates.TemplateResponse("friends.html", {
         "request": request,
         "friends": list(friend_set)
     })


 # ---------------- CHAT PAGE ----------------
@app.get("/chat/{friend}", response_class=HTMLResponse)
def chat(request: Request, friend: str):
    username= request.session.get("username")
    if not username:
         return RedirectResponse("/login")
    
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, sender, message, timestamp
        FROM messages
        WHERE (sender=%s AND receiver=%s)
        OR (sender=%s AND receiver=%s)
        ORDER BY id 
    """, (username, friend, friend, username))

    messages = cur.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "messages": messages,
            "friend": friend,
            "username": username
        }
    )


# ---------------- SEND MESSAGE ----------------
@app.post("/chat/{friend}")
def send_message(request: Request, friend: str, message: str = Form(...)):
    username = request.session.get("username")
    if not username:
        return RedirectResponse("/login")

    conn = get_conn()
    cur = conn.cursor()

    current_time = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%I:%M %p")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message, timestamp) VALUES (%s, %s, %s, %s)",
        (username, friend, message, current_time)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(f"/chat/{friend}", status_code=303)


# ---------------- WHO AM I ----------------
@app.get("/whoami")
def whoami(request: Request):
    return {"username": request.session.get("username")}

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@app.post("/upload/{friend}")
def upload_image(friend: str, file: UploadFile = File(...), request: Request = None):
    username = request.session.get("username")

    if not username:
        return {"error": "not logged in"}

    file_path = f"/uploads/{file.filename}"

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    conn = get_conn()
    cur = conn.cursor()

    current_time = datetime.now().strftime("%I:%M %p")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message, timestamp) VALUES (%s, %s, %s, %s)",
        (username, friend, file_path, current_time)
    )

    conn.commit()
    conn.close()

    return {"message": "image sent"}

@app.get("/delete-message/{msg_id}/{friend}")
def delete_message(msg_id: int, friend: str):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM messages WHERE id=%s",
        (msg_id,)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(
        f"/chat/{friend}",
        status_code=303
    )

@app.get("/camera", response_class=HTMLResponse)
def camera(request: Request):
    return templates.TemplateResponse("camera.html", {"request": request})



@app.post("/camera-upload/{friend}")
async def camera_upload(friend: str, request: Request):
    data = await request.json()

    image_data = data["image"]

    # remove base64 header
    image_data = image_data.split(",")[1]

    filename = f"{uuid.uuid4()}.png"

    save_path = f"uploads/{filename}"
    db_path = f"/uploads/{filename}"

    with open(save_path, "wb") as f:
        f.write(base64.b64decode(image_data))

    conn = get_conn()
    cur = conn.cursor()

    username = request.session.get("username")

    current_time = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).strftime("%I:%M %p")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message, timestamp) VALUES (%s, %s, %s, %s)",
        (username, friend, db_path, current_time)
    )

    conn.commit()
    conn.close()

    return {"message": "sent"}

@app.get("/camera/{friend}", response_class=HTMLResponse)
def camera(request: Request, friend: str):
    return templates.TemplateResponse("camera.html", {
        "request": request,
        "friend": friend
    })
    
@app.get("/filters/{friend}", response_class=HTMLResponse)
def filters(request: Request, friend: str):
    return templates.TemplateResponse(
        "filter.html",
        {
            "request": request,
            "friend": friend
        }
    )
    
@app.get("/test")
def test():
    return HTMLResponse("<h1>Test works</h1>")

@app.get("/test-template")
def test_template(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.get("/count-users")
def count_users():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    conn.close()

    return {"count": count}


@app.get("/debug-users-page")
def debug_users_page(request: Request):
    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT username FROM users WHERE username != %s",
        (username,)
    )

    data = cur.fetchall()

    conn.close()

    return {
        "logged_in_as": username,
        "users": data
    }
    
@app.get("/search-users")
def search_users(request: Request, q: str = ""):
    username = request.session.get("username")

    if not username:
        return {"error": "not logged in"}

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            u.username,
            CASE
                WHEN f.id IS NOT NULL THEN 'sent'
                ELSE 'none'
            END AS request_status
        FROM users u
        LEFT JOIN friends f
            ON f.sender = %s
            AND f.receiver = u.username
        WHERE u.username ILIKE %s
        AND u.username != %s
        ORDER BY u.username
    """, (username, f"%{q}%", username))

    users = cur.fetchall()

    cur.close()
    conn.close()

    return {"users": users}

@app.get("/test-users")
def test_users():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT username FROM users")

    users = cur.fetchall()

    cur.close()
    conn.close()

    return users
    
@app.get("/detective/clues", response_class=HTMLResponse)
def detective_clues(request: Request):

    clues = [
        "Muddy shoe prints near the sports room",
        "Watchman has keys",
        "Arjun practiced on muddy ground",
        "Coach left school at 5 PM"
    ]

    return templates.TemplateResponse(
        "clues.html",
        {
            "request": request,
            "clues": clues
        }
    )
    
@app.get("/detective/suspects", response_class=HTMLResponse)
def detective_suspects(request: Request):

    return templates.TemplateResponse(
        "suspects.html",
        {
            "request": request
        }
    )
    
@app.post("/detective/result", response_class=HTMLResponse)
def detective_result(
    request: Request,
    suspect: str = Form(...)
):

    correct = "Arjun"

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "suspect": suspect,
            "correct": correct,
            "won": suspect == correct
        }
    )
    
@app.get("/add-all-cases")
def add_all_cases():

    cases = [

    (
    "The Missing Trophy",
    "The school trophy disappeared one day before Sports Day.",
    "A muddy footprint was found near the trophy room|Rahul was seen near the room after school|The room was locked with a key",
    "Rahul|Watchman Suresh|Coach Ravi",
    "Rahul",
    "Easy",
    10
    ),

    (
    "The Lost Science Project",
    "A science project vanished before the exhibition.",
    "A bottle of glue was left behind|A student saw Priya carrying a large box|The project was found in Class 8B",
    "Priya|Amit|Teacher Meera",
    "Priya",
    "Easy",
    10
    ),

    (
    "The Vanished Homework",
    "A notebook containing homework disappeared.",
    "The notebook was last seen on a desk|Rohan sat at that desk after lunch|The notebook was found in Rohan's bag",
    "Rohan|Karan|Sneha",
    "Rohan",
    "Easy",
    10
    ),

    (
    "The Missing Library Book",
    "A popular library book disappeared.",
    "The last borrower was Anjali|The book was found under Anjali's desk|No one else borrowed it",
    "Anjali|Librarian|Ritesh",
    "Anjali",
    "Easy",
    10
    ),

    (
    "The Stolen Football",
    "The football used for practice went missing.",
    "Vikas was playing with it last|The ball was found in Vikas's garage|No one else took it home",
    "Vikas|Coach Ravi|Arjun",
    "Vikas",
    "Easy",
    10
    ),

    (
    "The Broken Classroom Clock",
    "The classroom clock was broken during recess.",
    "A cricket ball hit the wall|Sameer was playing cricket nearby|The ball belonged to Sameer",
    "Sameer|Rohit|Watchman",
    "Sameer",
    "Easy",
    10
    ),

    (
    "The Missing Exam Papers",
    "A stack of practice exam papers disappeared.",
    "Neha wanted extra copies|Papers were found in Neha's locker|No signs of forced entry",
    "Neha|Teacher Meera|Aman",
    "Neha",
    "Easy",
    10
    ),

    (
    "The Lost Art Painting",
    "A painting prepared for the art competition vanished.",
    "Paint stains were found on Kunal's hands|Kunal carried a drawing tube home|The painting was inside the tube",
    "Kunal|Riya|Art Teacher",
    "Kunal",
    "Easy",
    10
    ),

    (
    "The Mystery of the Empty Lunch Box",
    "A student's lunch disappeared.",
    "Food crumbs were found near Ajay's seat|Ajay skipped bringing lunch that day|Ajay admitted eating it",
    "Ajay|Rohan|Sneha",
    "Ajay",
    "Easy",
    10
    ),

    (
    "The Missing Cricket Cap",
    "The captain's cricket cap disappeared before the match.",
    "The cap was last seen in the locker room|Manav was changing there after practice|The cap was found in Manav's bag",
    "Manav|Coach Ravi|Watchman Suresh",
    "Manav",
    "Easy",
    10
    )

    ]

    conn = get_conn()
    cur = conn.cursor()

    for case in cases:
        cur.execute("""
            INSERT INTO detective_cases
            (title, story, clues, suspects, culprit, difficulty, xp)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, case)

    conn.commit()
    conn.close()

    return {"message": "All cases added"}
    
@app.get("/detective", response_class=HTMLResponse)
def detective(request: Request):

    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    # User XP
    cur.execute("""
        SELECT COALESCE(SUM(xp),0)
        FROM detective_progress
        WHERE username=%s
    """, (username,))

    user_xp = cur.fetchone()[0]

    # Cases
    cur.execute("""
        SELECT id, title, difficulty, xp, required_xp
        FROM detective_cases
        ORDER BY id
    """)

    cases = cur.fetchall()

    conn.close()

    return templates.TemplateResponse(
        "detective_cases.html",
        {
            "request": request,
            "cases": cases,
            "user_xp": user_xp   # 👈 THIS MUST EXIST
        }
    )
    
@app.get("/case/{case_id}", response_class=HTMLResponse)
def play_case(request: Request, case_id: int):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, title, story, clues, suspects
        FROM detective_cases
        WHERE id=%s
    """, (case_id,))

    case = cur.fetchone()

    conn.close()

    if not case:
        return HTMLResponse("Case not found", status_code=404)

    suspects = case[4].split("|")
    clues = case[3].split("|")

    return templates.TemplateResponse(
        "case.html",
        {
            "request": request,
            "case": case,
            "clues": clues,
            "suspects": suspects
        }
    )
    
@app.post("/accuse/{case_id}", response_class=HTMLResponse)
def accuse(
    request: Request,
    case_id: int,
    suspect: str = Form(...)
):
    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    # Get case
    cur.execute("""
        SELECT culprit, xp
        FROM detective_cases
        WHERE id=%s
    """, (case_id,))

    data = cur.fetchone()

    if not data:
        conn.close()
        return HTMLResponse("Case not found", status_code=404)

    culprit = data[0]
    xp = data[1]

    won = (suspect == culprit)

    if won:

        # Check if already solved
        cur.execute("""
            SELECT id
            FROM detective_progress
            WHERE username=%s
            AND case_id=%s
        """, (username, case_id))

        already_done = cur.fetchone()

        if not already_done:

            # Save XP
            cur.execute("""
                INSERT INTO detective_progress
                (username, case_id, xp)
                VALUES(%s,%s,%s)
            """, (username, case_id, xp))

            conn.commit()
            conn.close()

            # Reward player
            add_rewards(
                username=username,
                xp=10,
                gems=5,
                blinks=10,
                reason="Solved Detective Case"
            )

        else:
            conn.close()

    else:
        conn.close()

    return templates.TemplateResponse(
        "case_result.html",
        {
            "request": request,
            "won": won,
            "suspect": suspect,
            "culprit": culprit,
            "xp": xp
        }
    )


@app.get("/reset-detective-xp")
def reset_detective_xp(request: Request):

    username = request.session.get("username")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM detective_progress
        WHERE username=%s
    """, (username,))

    conn.commit()
    conn.close()

    return {"message": "XP reset"}

@app.get("/detective-profile", response_class=HTMLResponse)
def detective_profile(request: Request):

    username = request.session.get("username")

    if not username:
        return RedirectResponse("/login", status_code=303)

    conn = get_conn()
    cur = conn.cursor()

    # Get rewards
    cur.execute("""
        SELECT
            COALESCE(xp,0),
            COALESCE(blinks,0),
            COALESCE(gems,0),
            COALESCE(coins,0),
            COALESCE(login_streak,0)
        FROM player_rewards
        WHERE username=%s
    """, (username,))

    user = cur.fetchone()

    conn.close()

    if user:
        xp = user[0]
        blinks = user[1]
        gems = user[2]
        coins = user[3]
        login_streak = user[4]
    else:
        xp = 0
        blinks = 0
        gems = 0
        coins = 0
        login_streak = 0

    # Detective Level
    if xp >= 1000:
        level = "Legend Detective"
        next_xp = 1000
    elif xp >= 600:
        level = "Master Detective"
        next_xp = 1000
    elif xp >= 350:
        level = "Expert Detective"
        next_xp = 600
    elif xp >= 200:
        level = "Senior Detective"
        next_xp = 350
    elif xp >= 100:
        level = "School Detective"
        next_xp = 200
    elif xp >= 50:
        level = "Junior Detective"
        next_xp = 100
    else:
        level = "Rookie Detective"
        next_xp = 50

    progress = min(int((xp / next_xp) * 100), 100)

    return templates.TemplateResponse(
        "detective_profile.html",
        {
            "request": request,
            "username": username,
            "xp": xp,
            "level": level,
            "progress": progress,
            "next_xp": next_xp,
            "blinks": blinks,
            "gems": gems,
            "coins": coins,
            "login_streak": login_streak
        }
    )
    
def get_user_profile(username):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT blinks, gems, coins
        FROM users
        WHERE username=%s
    """, (username,))

    user = cur.fetchone()

    conn.close()

    return user


def add_rewards(username, xp=0, gems=0, blinks=0, coins=0, reason="Reward"):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO player_rewards(username)
        VALUES(%s)
        ON CONFLICT(username) DO NOTHING
    """, (username,))

    cur.execute("""
        UPDATE player_rewards
        SET
            xp = xp + %s,
            gems = gems + %s,
            blinks = blinks + %s,
            coins = coins + %s
        WHERE username=%s
    """, (xp, gems, blinks, coins, username))

    cur.execute("""
        INSERT INTO reward_history
        (username,reward_type,xp,gems,blinks,coins)
        VALUES(%s,%s,%s,%s,%s,%s)
    """, (username, reason, xp, gems, blinks, coins))

    conn.commit()
    conn.close()
    
@app.get("/setup-case-xp")
def setup_case_xp():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE detective_cases
        SET required_xp = (id - 1) * 10
    """)

    conn.commit()
    conn.close()

    return {"message":"XP requirements added"}

@app.get("/profile/{username}")
def profile(username: str):
    user = get_user_profile(username)

    if not user:
        return {"error": "User not found"}

    return {
        "username": username,
        "blinks": user[0],
        "gems": user[1],
        "coins": user[2]
    }
    
def update_attempts(username, case_id):

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT attempts
        FROM detective_attempts
        WHERE username=%s
        AND case_id=%s
    """, (username, case_id))

    row = cur.fetchone()

    attempts = 1

    if row:
        attempts = row[0] + 1

    cur.execute("""
        INSERT INTO detective_attempts(username, case_id, attempts)
        VALUES(%s,%s,%s)
        ON CONFLICT(username, case_id)
        DO UPDATE SET attempts=%s
    """, (username, case_id, attempts, attempts))

    conn.commit()
    conn.close()

    return attempts


@app.get("/fix-player-rewards")
def fix_player_rewards():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        ALTER TABLE player_rewards
        ADD COLUMN IF NOT EXISTS coins INTEGER DEFAULT 0
    """)

    conn.commit()
    conn.close()

    return {"message": "Fixed"}

@app.get("/check-player-table")
def check_player_table():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='player_rewards'
        ORDER BY ordinal_position
    """)

    columns = cur.fetchall()

    conn.close()

    return {"columns": columns}