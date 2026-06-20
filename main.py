from fastapi import FastAPI, Request, Form
from fastapi import File, UploadFile
import os
import base64
import uuid
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import sqlite3

app = FastAPI()

os.makedirs("uploads", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(SessionMiddleware, secret_key="blink-secret-key")

templates = Jinja2Templates(directory="templates")


# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS friends(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        status TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        receiver TEXT,
        message TEXT
    )""")

    conn.commit()
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
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO users(username,password) VALUES(?,?)",
            (username, password)
        )
        conn.commit()
        conn.close()
        return RedirectResponse("/login", status_code=303)

    except:
        conn.close()
        return HTMLResponse("Username already exists")

@app.get("/login")
def login_page():
    return {"message": "login works"}

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT username FROM users WHERE username=? AND password=?",
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

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT username FROM users WHERE username != ?", (username,))
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

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO friends(sender, receiver, status) VALUES (?, ?, 'pending')",
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

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT id, sender FROM friends WHERE receiver=? AND status='pending'",
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
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("UPDATE friends SET status='accepted' WHERE id=?", (request_id,))

    conn.commit()
    conn.close()

    return RedirectResponse("/requests", status_code=303)


# ---------------- CHAT LIST ----------------
@app.get("/friends", response_class=HTMLResponse)
def friends(request: Request):
    username = request.session.get("username")
    if not username:
        return RedirectResponse("/login", status_code=303)

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT sender, receiver
        FROM friends
        WHERE status='accepted'
        AND (sender=? OR receiver=?)
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
    username = request.session.get("username")
    if not username:
        return RedirectResponse("/login")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT id, sender, message
        FROM messages
        WHERE (sender=? AND receiver=?)
        OR (sender=? AND receiver=?)
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

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO messages(sender, receiver, message) VALUES (?, ?, ?)",
        (username, friend, message)
    )

    conn.commit()
    conn.close()

    return RedirectResponse(f"/chat/{friend}", status_code=303)


# ---------------- WHO AM I ----------------
@app.get("/whoami")
def whoami(request: Request):
    return {"username": request.session.get("username")}

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    username = request.session.get("username")

    if not username:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": username
    })
    
@app.get("/debug-messages")
def debug_messages():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT * FROM messages")
    data = cur.fetchall()

    conn.close()

    return data


@app.get("/clear-messages")
def clear_messages():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("DELETE FROM messages")

    conn.commit()
    conn.close()

    return {"message": "all messages deleted"}

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

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO messages(sender, receiver, message) VALUES (?, ?, ?)",
        (username, friend, file_path)
    )

    conn.commit()
    conn.close()

    return {"message": "image sent"}

@app.get("/delete-message/{msg_id}/{friend}")
def delete_message(msg_id: int, friend: str):

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM messages WHERE id=?",
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

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    username = request.session.get("username")

    cur.execute(
        "INSERT INTO messages(sender, receiver, message) VALUES (?, ?, ?)",
        (username, friend, db_path)
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