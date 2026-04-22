from app import app
from models import db, Task
from services import gcal
with app.app_context():
    t = Task.query.order_by(Task.id.desc()).first()
    print("Pushing task...")
    res1 = gcal.push_item("task", t, t.assignees[0].id if t.assignees else 1)
    print("Task push res:", res1)
    print("Pushing task_event...")
    res2 = gcal.push_item("task_event", t, t.assignees[0].id if t.assignees else 1)
    print("Event push res:", res2)
