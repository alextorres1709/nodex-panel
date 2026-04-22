from app import app
from models import db, Task
with app.app_context():
    t = Task.query.order_by(Task.id.desc()).first()
    print("Created at type:", type(t.created_at))
    print("Created at value:", t.created_at)
