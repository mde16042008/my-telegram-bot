import html
import os

from fastapi import FastAPI, Form, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

import database as db

load_dotenv()

app = FastAPI()
security = HTTPBasic()


# ---------- Аутентификация ----------

def current_user(credentials: HTTPBasicCredentials = Depends(security)):
    user = db.get_system_user_by_username(credentials.username)
    if not user or not db.verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


# ---------- Общий шаблон с темами ----------

def render_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<script>
(function() {{
  var t = localStorage.getItem('theme') || 'white';
  document.documentElement.setAttribute('data-theme', t);
}})();
</script>
<style>
:root[data-theme="white"] {{
  --bg: #f5f5f5; --text: #222; --card-bg: #fff; --border: #eee;
  --th-bg: #4a5568; --th-text: #fff; --input-bg: #fff; --input-border: #ccc;
  --hover: #f9f9f9; --muted: #666; --gradient: none;
}}
:root[data-theme="gray"] {{
  --bg: #2b2b2b; --text: #e0e0e0; --card-bg: #3a3a3a; --border: #505050;
  --th-bg: #1f1f1f; --th-text: #e0e0e0; --input-bg: #2b2b2b; --input-border: #505050;
  --hover: #454545; --muted: #aaa; --gradient: none;
}}
:root[data-theme="black"] {{
  --bg: #000; --text: #ccc; --card-bg: #111; --border: #222;
  --th-bg: #0a0a0a; --th-text: #ccc; --input-bg: #0a0a0a; --input-border: #333;
  --hover: #1a1a1a; --muted: #888; --gradient: none;
}}
:root[data-theme="space"] {{
  --bg: #0a0e27; --text: #c8d0ff; --card-bg: rgba(30, 40, 80, 0.75); --border: #3a4a7a;
  --th-bg: rgba(15, 25, 55, 0.95); --th-text: #a0b0ff; --input-bg: rgba(20, 30, 60, 0.7);
  --input-border: #4a5a8a; --hover: rgba(40, 50, 100, 0.7); --muted: #8899cc;
  --gradient: radial-gradient(ellipse at top, #1a1f3a 0%, #0a0e27 50%, #000 100%);
}}
html, body {{
  margin: 0; padding: 0; min-height: 100vh;
  font-family: system-ui, -apple-system, sans-serif;
  background-color: var(--bg);
  background-image: var(--gradient);
  color: var(--text);
}}
body {{ max-width: 1150px; margin: 2em auto; padding: 0 1em; }}
a {{ color: #6b9eff; }}
h1 {{ margin-top: 0; }}
table {{
  width: 100%; border-collapse: collapse;
  background: var(--card-bg); border-radius: 8px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.25);
}}
th, td {{
  padding: 10px; text-align: left;
  border-bottom: 1px solid var(--border); vertical-align: middle;
}}
th {{ background: var(--th-bg); color: var(--th-text); font-weight: 600; }}
tr:hover {{ background: var(--hover); }}
.btn {{
  display: inline-block; padding: 6px 12px; border: none; border-radius: 4px;
  cursor: pointer; text-decoration: none; font-size: 14px;
}}
.btn-primary {{ background: #4299e1; color: white; }}
.btn-danger {{ background: #f56565; color: white; }}
.btn-success {{ background: #48bb78; color: white; }}
.btn-sm {{ padding: 4px 8px; font-size: 13px; }}
input[type=text], input[type=password], select, textarea {{
  padding: 8px; border: 1px solid var(--input-border); border-radius: 4px;
  background: var(--input-bg); color: var(--text); font-family: inherit;
  box-sizing: border-box;
}}
input[type=text], input[type=password], textarea {{ width: 100%; }}
.status-on {{ color: #48bb78; font-weight: bold; }}
.status-off {{ color: #f56565; font-weight: bold; }}
.msg {{
  background: var(--card-bg); padding: 12px; margin-bottom: 8px;
  border-radius: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}}
.msg .time {{ color: var(--muted); font-size: 12px; margin-bottom: 4px; }}
.empty {{
  text-align: center; padding: 40px; color: var(--muted);
  background: var(--card-bg); border-radius: 8px;
}}
.topnav {{
  margin-bottom: 1em; display: flex; gap: 1em; align-items: center;
  flex-wrap: wrap;
}}
.topnav a {{ color: #6b9eff; text-decoration: none; }}
.topnav a:hover {{ text-decoration: underline; }}
.topnav .spacer {{ flex: 1; }}
.muted {{ color: var(--muted); }}
.form-row {{
  display: flex; gap: 6px; margin: 1em 0; flex-wrap: wrap;
  align-items: center;
}}
.form-row input[type=text] {{ flex: 1; min-width: 180px; width: auto; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


THEME_SWITCHER = """
<select id="theme-switcher" onchange="localStorage.setItem('theme', this.value); document.documentElement.setAttribute('data-theme', this.value);" style="width:auto;">
  <option value="white">☀️ Белая</option>
  <option value="gray">🌥 Серая</option>
  <option value="black">🌑 Чёрная</option>
  <option value="space">🌌 Космос</option>
</select>
<script>
(function() {{
  var t = localStorage.getItem('theme') || 'white';
  var el = document.getElementById('theme-switcher');
  if (el) el.value = t;
}})();
</script>
"""


def topnav(user):
    is_admin = user["role"] == "admin"
    admin_link = '<a href="/admin">👥 Операторы</a>' if is_admin else ""
    return f"""
    <div class="topnav">
        <a href="/">🏠 Контакты</a>
        <a href="/templates">📝 Шаблоны</a>
        <a href="/backup">💾 Бэкап</a>
        {admin_link}
        <span class="spacer"></span>
        <span class="muted">👤 {html.escape(user['display_name'] or user['username'])} ({user['role']})</span>
        {THEME_SWITCHER}
    </div>
    """


def can_edit(user, contact) -> bool:
    if user["role"] == "admin":
        return True
    return contact["assigned_to"] == user["id"]


# ---------- Health check (без пароля) ----------

@app.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz():
    return {"status": "ok"}


# ---------- Главная: контакты ----------

@app.get("/", response_class=HTMLResponse)
async def index(user=Depends(current_user)):
    is_admin = user["role"] == "admin"
    contacts = db.list_contacts(assigned_to=user["id"], include_all=is_admin)
    templates = db.list_templates(owner_id=user["id"], include_shared=True)
    template_options = "".join(
        f'<option value="{html.escape(t["text"], quote=True)}">{html.escape(t["text"][:60])}</option>'
        for t in templates
    )
    template_options_id = "".join(
        f'<option value="{t["id"]}">{html.escape(t["text"][:60])}</option>'
        for t in templates
    )

    rows = []
    for c in contacts:
        cid = c["id"]
        editable = can_edit(user, c)
        username_attr = f"@{c['username']}" if c["username"] else "—"
        tg_id = c["telegram_id"] if c["telegram_id"] else "—"
        phone = html.escape(c["phone"] or "—")
        name = html.escape(c["first_name"] or "")
        reply_text = html.escape(c["reply_text"] or "")
        enabled = bool(c["reply_enabled"])
        status_html = '<span class="status-on">✅ вкл</span>' if enabled else '<span class="status-off">❌ выкл</span>'
        toggle_label = "Выключить" if enabled else "Включить"
        toggle_class = "btn-danger" if enabled else "btn-success"

        operator_col = ""
        if is_admin:
            op_name = (c["operator_username"] if "operator_username" in c.keys() and c["operator_username"] else "админ")
            operator_col = f"<td><small>{html.escape(op_name)}</small></td>"

        if editable:
            reply_cell = f"""
                <form method="post" action="/reply" style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                    <input type="hidden" name="contact_id" value="{cid}">
                    <input type="text" name="text" value="{reply_text}" placeholder="Текст автоответа..." required style="flex:1; min-width:150px;">
                    <select onchange="if(this.value) this.previousElementSibling.value=this.value; this.value='';" style="width:auto;">
                        <option value="">Шаблон...</option>
                        {template_options}
                    </select>
                    <button type="submit" class="btn btn-primary btn-sm">💾</button>
                </form>"""
            actions_cell = f"""
                <form method="post" action="/toggle/{cid}" style="display:inline;">
                    <button type="submit" class="btn {toggle_class} btn-sm">{toggle_label}</button>
                </form>
                <a href="/messages/{cid}" class="btn btn-primary btn-sm" title="Сообщения">📩</a>
                <form method="post" action="/delete_contact/{cid}" style="display:inline;" onsubmit="return confirm('Удалить контакт id={cid}?');">
                    <button type="submit" class="btn btn-danger btn-sm" title="Удалить">🗑</button>
                </form>"""
        else:
            reply_cell = f"<small>{reply_text or '—'}</small>"
            actions_cell = f'<a href="/messages/{cid}" class="btn btn-primary btn-sm">📩</a>'

        rows.append(f"""
        <tr>
            <td>{cid}</td>
            <td><b>{name or '—'}</b><br><small>{username_attr}</small><br><small class="muted">tg: {tg_id}</small></td>
            <td><small>{phone}</small></td>
            {operator_col}
            <td>{status_html}</td>
            <td>{reply_cell}</td>
            <td style="white-space:nowrap;">{actions_cell}</td>
        </tr>""")

    op_header = "<th>У кого</th>" if is_admin else ""
    if not contacts:
        content = '<div class="empty">Контактов нет. Добавьте через форму выше.</div>'
    else:
        content = f"""<table>
            <thead><tr><th>ID</th><th>Контакт</th><th>Телефон</th>{op_header}<th>Статус</th><th>Автоответ</th><th>Действия</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>"""

    body = f"""
    {topnav(user)}
    <h1>🤖 Контакты</h1>
    <form method="post" action="/add_contact" class="form-row">
        <input type="text" name="target" placeholder="@username / telegram_id / +телефон" required>
        <input type="text" name="reply" placeholder="Автоответ (необязательно)">
        <select name="template_id" style="width:auto;">
            <option value="">Шаблон...</option>
            {template_options_id}
        </select>
        <button type="submit" class="btn btn-success">➕ Добавить</button>
    </form>
    {content}
    """
    return render_page("Контакты", body)


# ---------- Действия с контактом ----------

@app.post("/reply")
async def set_reply(contact_id: int = Form(...), text: str = Form(...), user=Depends(current_user)):
    contact = db.get_contact(contact_id)
    if not contact or not can_edit(user, contact):
        raise HTTPException(403)
    db.set_auto_reply(contact_id, text, enabled=True)
    return RedirectResponse("/", status_code=303)


@app.post("/toggle/{contact_id}")
async def toggle(contact_id: int, user=Depends(current_user)):
    contact = db.get_contact(contact_id)
    if not contact or not can_edit(user, contact):
        raise HTTPException(403)
    db.toggle_auto_reply(contact_id)
    return RedirectResponse("/", status_code=303)


@app.post("/add_contact")
async def add_contact(
    target: str = Form(...),
    reply: str = Form(""),
    template_id: str = Form(""),
    user=Depends(current_user),
):
    target = target.strip()
    existing = None
    if target.startswith("+") or (target.replace(" ", "").replace("-", "").isdigit() and len(target) > 9):
        existing = db.get_contact_by_phone(target)
        contact_id = existing["id"] if existing else db.add_contact(assigned_to=user["id"], phone=target)
    elif target.lstrip("-").isdigit():
        existing = db.get_contact_by_telegram_id(int(target))
        contact_id = existing["id"] if existing else db.add_contact(assigned_to=user["id"], telegram_id=int(target))
    else:
        username = target.lstrip("@")
        existing = db.get_contact_by_username(username)
        contact_id = existing["id"] if existing else db.add_contact(assigned_to=user["id"], username=username)

    final_text = reply.strip()
    if not final_text and template_id.strip():
        templates = db.list_templates(owner_id=user["id"])
        match = next((t for t in templates if str(t["id"]) == template_id.strip()), None)
        if match:
            final_text = match["text"]
    if final_text:
        db.set_auto_reply(contact_id, final_text, enabled=True)
    return RedirectResponse("/", status_code=303)


@app.post("/delete_contact/{contact_id}")
async def delete_contact(contact_id: int, user=Depends(current_user)):
    contact = db.get_contact(contact_id)
    if not contact or not can_edit(user, contact):
        raise HTTPException(403)
    db.delete_contact(contact_id)
    return RedirectResponse("/", status_code=303)


@app.post("/assign/{contact_id}")
async def assign(contact_id: int, operator: str = Form(...), user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    op = db.get_system_user_by_username(operator.lstrip("@"))
    if not op:
        raise HTTPException(400, "Оператор не найден")
    db.update_contact(contact_id, assigned_to=op["id"])
    return RedirectResponse("/", status_code=303)


# ---------- Сообщения контакта ----------

@app.get("/messages/{contact_id}", response_class=HTMLResponse)
async def messages(contact_id: int, user=Depends(current_user)):
    contact = db.get_contact(contact_id)
    if not contact:
        raise HTTPException(404)
    if not can_edit(user, contact):
        raise HTTPException(403)
    msgs = db.get_messages(contact_id, limit=100)
    username_attr = f"@{contact['username']}" if contact["username"] else "—"
    if msgs:
        msg_html = "".join(
            f'<div class="msg"><div class="time">{html.escape(m["received_at"])}</div>{html.escape(m["text"] or "—")}</div>'
            for m in msgs
        )
    else:
        msg_html = '<div class="empty">Сообщений нет.</div>'
    body = f"""
    {topnav(user)}
    <p><a href="/">← К контактам</a></p>
    <h1>{html.escape(contact['first_name'] or '')} ({username_attr})</h1>
    {msg_html}
    """
    return render_page("Сообщения", body)


# ---------- Шаблоны ----------

@app.get("/templates", response_class=HTMLResponse)
async def templates_page(user=Depends(current_user)):
    templates = db.list_templates(owner_id=user["id"], include_shared=True)
    if templates:
        rows = "".join(
            f"""<tr>
                <td>{t['id']}</td>
                <td>{html.escape(t['text'])}</td>
                <td><small>{html.escape(t['created_at'])}</small></td>
                <td>
                    <form method="post" action="/templates/delete/{t['id']}" style="display:inline;">
                        <button type="submit" class="btn btn-danger btn-sm">Удалить</button>
                    </form>
                </td>
            </tr>""" for t in templates
        )
        content = f"""<table>
            <thead><tr><th>ID</th><th>Текст</th><th>Создан</th><th></th></tr></thead>
            <tbody>{rows}</tbody>
        </table>"""
    else:
        content = '<div class="empty">Шаблонов нет.</div>'
    body = f"""
    {topnav(user)}
    <h1>📝 Шаблоны</h1>
    <form method="post" action="/templates/add" class="form-row">
        <input type="text" name="text" placeholder="Текст нового шаблона..." required>
        <button type="submit" class="btn btn-success">Добавить</button>
    </form>
    {content}
    """
    return render_page("Шаблоны", body)


@app.post("/templates/add")
async def add_template(text: str = Form(...), user=Depends(current_user)):
    db.add_template(text, owner_id=user["id"])
    return RedirectResponse("/templates", status_code=303)


@app.post("/templates/delete/{template_id}")
async def delete_template(template_id: int, user=Depends(current_user)):
    is_admin = user["role"] == "admin"
    db.delete_template(template_id, requester_id=user["id"], is_admin=is_admin)
    return RedirectResponse("/templates", status_code=303)


# ---------- Бэкап ----------

@app.get("/backup")
async def backup(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    if not os.path.exists(db.DB_PATH):
        raise HTTPException(404, "База не создана")
    return FileResponse(db.DB_PATH, filename="bot.db", media_type="application/octet-stream")


# ---------- Админ: управление операторами ----------

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    users = db.list_system_users()
    rows = []
    for u in users:
        delete_btn = ""
        if u["role"] != "admin":
            delete_btn = f"""
            <form method="post" action="/admin/delete_user/{u['id']}" style="display:inline;" onsubmit="return confirm('Удалить оператора {html.escape(u['username'])}?');">
                <button type="submit" class="btn btn-danger btn-sm">Удалить</button>
            </form>"""
        rows.append(f"""
        <tr>
            <td>{u['id']}</td>
            <td>{html.escape(u['username'])}</td>
            <td>{html.escape(u['display_name'] or '—')}</td>
            <td>{u['role']}</td>
            <td>{u['telegram_id'] or '—'}</td>
            <td>{delete_btn}</td>
        </tr>""")
    body = f"""
    {topnav(user)}
    <h1>👥 Системные пользователи</h1>
    <form method="post" action="/admin/add_operator" class="form-row">
        <input type="text" name="login" placeholder="Логин" required style="width:150px; flex:0;">
        <input type="password" name="password" placeholder="Пароль" required style="width:150px; flex:0;">
        <input type="text" name="name" placeholder="Отображаемое имя" style="width:180px; flex:0;">
        <button type="submit" class="btn btn-success">➕ Добавить оператора</button>
    </form>
    <table>
        <thead><tr><th>ID</th><th>Логин</th><th>Имя</th><th>Роль</th><th>tg_id</th><th></th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>

    <h2 style="margin-top:2em;">🔐 Смена своего пароля</h2>
    <form method="post" action="/admin/change_password" class="form-row">
        <input type="password" name="new_password" placeholder="Новый пароль (мин. 6 символов)" required style="width:280px; flex:0;">
        <button type="submit" class="btn btn-primary">Сменить пароль</button>
    </form>
    """
    return render_page("Операторы", body)


@app.post("/admin/add_operator")
async def add_operator(
    login: str = Form(...),
    password: str = Form(...),
    name: str = Form(""),
    user=Depends(current_user),
):
    if user["role"] != "admin":
        raise HTTPException(403)
    if db.get_system_user_by_username(login):
        return RedirectResponse("/admin?error=login_taken", status_code=303)
    db.create_system_user(login, password, role="operator", display_name=name or login)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete_user/{user_id}")
async def delete_operator(user_id: int, user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403)
    target = db.get_conn().execute("SELECT * FROM system_users WHERE id = ?", (user_id,)).fetchone()
    if target and target["role"] != "admin":
        db.delete_system_user(user_id)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/change_password")
async def change_password(new_password: str = Form(...), user=Depends(current_user)):
    if len(new_password) < 6:
        raise HTTPException(400, "Пароль слишком короткий")
    db.change_password(user["id"], new_password)
    return RedirectResponse("/admin", status_code=303)
