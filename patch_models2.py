from app import app
from models import db
from sqlalchemy import text

try:
    with app.app_context():
        # Let's insert for objectives and calendar_events which DO have assigned_to
        db.session.execute(text("INSERT INTO objective_assignments (objective_id, user_id) SELECT id, assigned_to FROM objectives WHERE assigned_to IS NOT NULL"))
        db.session.execute(text("INSERT INTO event_assignments (event_id, user_id) SELECT id, assigned_to FROM calendar_events WHERE assigned_to IS NOT NULL"))
        
        db.session.commit()
        print("Data migrated.")
except Exception as e:
    print("Error:", e)
