import html
import os
import secrets

from fastapi import FastAPI, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

import database as db

load_dotenv()

WEB_USERNAME = os.getenv("WEB_USERNAME")
WEB_PASSWORD = os.getenv("WEB_PASSWORD")

if not WEB_USERNAME or not WEB_PASSWORD:
    raise RuntimeError("WEB_USERNAME и WEB_PASSWORD должны быть заданы")

app = FastAPI()
security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode("utf8"), WEB_USERNAME.encode("utf8"))
    ok_pass = secrets.compare_digest(credentials.password.encode("utf8"), WEB_PASSWORD.encode("utf8"))
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def render_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 1100px; margin: 2em auto; padding: 0 1em; background: #f5f5f5; color: #222; }}
h1 {{ color: #333; }}
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; vertical-align: middle; }}
th {{ background: #4a5568; color: white; font-weight: 600; }}
tr:hover {{ background: #f9f9f9; }}
.btn {{ display: inline-block; padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 14px; }}
.btn-primary {{ background: #4299e1; color: white; }}
.btn-danger {{ background: #f56565; color: white; }}
.btn-success {{ background: #48bb78; color: white; }}
.btn-sm {{ padding: 4px 8px; font-size: 13px; }}
input[type=text] {{ width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-family: inherit; }}
select {{ padding: 8px; border: 1px solid #ccc; border-radius: 4px; font-family: inherit; }}
.status-on {{ color: #38a169; font-weight: bold; }}
.status-off {{ color: #e53e3e; font-weight: bold; }}
.msg {{ background: white; padding: 12px; margin-bottom: 8px; border-radius: 6px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
.msg .time {{ color: #888; font-size: 12px; margin-bottom: 4px; }}
.empty {{ text-align: center; padding: 40px; color: #888; background: white; border-radius: 8px; }}
.topnav {{ margin-bottom: 1em; }}
.topnav a {{ margin-right: 1em; color: #4299e1; text-decoration: none; }}
.topnav a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


@app.api_route("/healthz", methods=["GET", "HEAD"])
async def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(username: str = Depends(verify_credentials)):
    users = db.list_users()
    templates = db.list_templates()
    template_options = "".join(
        f'<option value="{html.escape(t["text"], quote=True)}">{html.escape(t["text"][:60])}</option>'
        for t in templates
    )
    rows = []
    for u in users:
        user_id = u["id"]
        username_attr = f"@{u['username']}" if u["username"] else "—"
        tg_id = u["telegram_id"] if u["telegram_id"] else "—"
        name = html.escape(u["first_name"] or "")
        reply_text = html.escape(u["reply_text"] or "")
        enabled = bool(u["reply_enabled"])
        status_html = '<span class="status-on">✅ вкл</span>' if enabled else '<span class="status-off">❌ выкл</span>'
        toggle_label = "Выключить" if enabled else "Включить"
        toggle_class = "btn-danger" if enabled else "btn-success"
        rows.append(f"""
        <tr>
            <td>{user_id}</td>
            <td><b>{name or '—'}</b><br><small>{username_attr}</small><br><small style="color:#999;">tg: {tg_id}</small></td>
            <td>{status_html}</td>
            <td>
                <form method="post" action="/reply" style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                    <input type="hidden" name="user_id" value="{user_id}">
                    <input type="text" name="text" value="{reply_text}" placeholder="Текст автоответа..." required style="flex:1; min-width:200px;">
                    <select onchange="if(this.value) this.previousElementSibling.value=this.value; this.value='';">
                        <option value="">Шаблон...</option>
                        {template_options}
                    </select>
                    <button type="submit" class="btn btn-primary btn-sm" title="Сохранить">💾</button>
                </form>
            </td>
            <td style="white-space:nowrap;">
                <form method="post" action="/toggle/{user_id}" style="display:inline;">
                    <button type="submit" class="btn {toggle_class} btn-sm">{toggle_label}</button>
                </form>
                <a href="/messages/{user_id}" class="btn btn-primary btn-sm" title="Сообщения">📩</a>
                <form method="post" action="/delete_user/{user_id}" style="display:inline;" onsubmit="return confirm('Удалить пользователя id={user_id}?');">
                    <button type="submit" class="btn btn-danger btn-sm" title="Удалить">🗑</button>
                </form>
            </td>
        </tr>
        """)
    if not users:
        content = '<div class="empty">Пока никто не писал. Добавьте вручную через форму выше или подождите сообщения.</div>'
    else:
        content = f"""<table>
            <thead><tr><th>ID</th><th>Пользователь</th><th>Статус</th><th>Автоответ</th><th>Действия</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>"""

    body = f"""
    <h1>🤖 Автоответчик</h1>
    <div class="topnav">
        <a href="/templates">📝 Шаблоны</a>
        <a href="/backup">💾 Скачать бэкап БД</a>
    </div>
    <form method="post" action="/add_user" style="display:flex; gap:6px; margin: 1em 0;">
        <input type="text" name="target" placeholder="@username или числовой telegram_id" required style="flex:1;">
        <button type="submit" class="btn btn-success">➕ Добавить</button>
    </form>
    <p style="color:#666;">Контакты, которые вам писали (через Telegram Business), и добавленные вручную</p>
    {content}
    """
    return render_page("Автоответчик", body)


@app.post("/reply")
async def set_reply(user_id: int = Form(...), text: str = Form(...), username: str = Depends(verify_credentials)):
    db.set_auto_reply(user_id, text, enabled=True)
    return RedirectResponse("/", status_code=303)


@app.post("/toggle/{user_id}")
async def toggle(user_id: int, username: str = Depends(verify_credentials)):
    db.toggle_auto_reply(user_id)
    return RedirectResponse("/", status_code=303)


@app.get("/messages/{user_id}", response_class=HTMLResponse)
async def messages(user_id: int, username: str = Depends(verify_credentials)):
    user = db.get_user_by_internal_id(user_id)
    if not user:
        return HTMLResponse("<h1>Пользователь не найден</h1><a href='/'>← Назад</a>", status_code=404)
    msgs = db.get_messages(user_id, limit=100)
    username_attr = f"@{user['username']}" if user["username"] else "—"
    if msgs:
        msg_html = "".join(
            f'<div class="msg"><div class="time">{html.escape(m["received_at"])}</div>{html.escape(m["text"] or "—")}</div>'
            for m in msgs
        )
    else:
        msg_html = '<div class="empty">Сообщений пока нет.</div>'
    body = f"""
    <p><a href="/">← К списку контактов</a></p>
    <h1>{html.escape(user['first_name'] or '')} ({username_attr})</h1>
    <p style="color:#666;">Последние 100 сообщений</p>
    {msg_html}
    """
    return render_page(f"Сообщения — {user['first_name'] or ''}", body)


@app.get("/templates", response_class=HTMLResponse)
async def templates_page(username: str = Depends(verify_credentials)):
    templates = db.list_templates()
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
            </tr>"""
            for t in templates
        )
        content = f"""<table>
            <thead><tr><th>ID</th><th>Текст</th><th>Создан</th><th></th></tr></thead>
            <tbody>{rows}</tbody>
        </table>"""
    else:
        content = '<div class="empty">Шаблонов пока нет.</div>'

    body = f"""
    <p><a href="/">← К контактам</a></p>
    <h1>📝 Шаблоны ответов</h1>
    <form method="post" action="/templates/add" style="display:flex; gap:6px; margin: 1em 0;">
        <input type="text" name="text" placeholder="Текст нового шаблона..." required>
        <button type="submit" class="btn btn-success">Добавить</button>
    </form>
    {content}
    """
    return render_page("Шаблоны", body)


@app.post("/templates/add")
async def add_template_route(text: str = Form(...), username: str = Depends(verify_credentials)):
    db.add_template(text)
    return RedirectResponse("/templates", status_code=303)


@app.post("/templates/delete/{template_id}")
async def delete_template_route(template_id: int, username: str = Depends(verify_credentials)):
    db.delete_template(template_id)
    return RedirectResponse("/templates", status_code=303)


@app.get("/backup")
async def backup_route(username: str = Depends(verify_credentials)):
    if not os.path.exists(db.DB_PATH):
        raise HTTPException(404, "Файл базы данных ещё не создан")
    return FileResponse(db.DB_PATH, filename="bot.db", media_type="application/octet-stream")

@app.post("/add_user")
async def add_user_route(target: str = Form(...), username: str = Depends(verify_credentials)):
    target = target.strip()
    try:
        if target.lstrip("-").isdigit():
            db.add_user_by_telegram_id(int(target))
        else:
            db.add_user_by_username(target)
    except Exception:
        pass
    return RedirectResponse("/", status_code=303)


@app.post("/delete_user/{user_id}")
async def delete_user_route(user_id: int, username: str = Depends(verify_credentials)):
    db.delete_user(user_id)
    return RedirectResponse("/", status_code=303)
