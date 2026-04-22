from app import app
from models import db, Task, User
from services import gcal
with app.app_context():
    u = User.query.filter_by(email="djalesito10@gmail.com").first()
    if not u: u = User.query.first()
    t = Task.query.order_by(Task.id.desc()).first()
    print("User:", u.email)
    print("Task:", t.title, "created:", t.created_at)
    res = gcal.push_item("task", t, u.id)
    print("Result:", res)
