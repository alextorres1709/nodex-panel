from app import app
from models import db
from sqlalchemy import text

try:
    with app.app_context():
        db.session.execute(text("CREATE TABLE objective_requirements (id INTEGER PRIMARY KEY, objective_id INTEGER NOT NULL, title VARCHAR(300) NOT NULL, description TEXT, is_met BOOLEAN, FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE CASCADE)"))
        db.session.execute(text("CREATE TABLE objective_weekly_plans (id INTEGER PRIMARY KEY, objective_id INTEGER NOT NULL, week_start DATE NOT NULL, focus VARCHAR(300) NOT NULL, notes TEXT, FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE CASCADE)"))
        
        db.session.execute(text("CREATE TABLE project_assignments (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, user_id INTEGER NOT NULL, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)"))
        db.session.execute(text("CREATE TABLE objective_assignments (id INTEGER PRIMARY KEY, objective_id INTEGER NOT NULL, user_id INTEGER NOT NULL, FOREIGN KEY(objective_id) REFERENCES objectives(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)"))
        db.session.execute(text("CREATE TABLE event_assignments (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, user_id INTEGER NOT NULL, FOREIGN KEY(event_id) REFERENCES calendar_events(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)"))
        
        db.session.execute(text("INSERT INTO project_assignments (project_id, user_id) SELECT id, assigned_to FROM projects WHERE assigned_to IS NOT NULL"))
        db.session.execute(text("INSERT INTO objective_assignments (objective_id, user_id) SELECT id, assigned_to FROM objectives WHERE assigned_to IS NOT NULL"))
        db.session.execute(text("INSERT INTO event_assignments (event_id, user_id) SELECT id, assigned_to FROM calendar_events WHERE assigned_to IS NOT NULL"))
        
        db.session.commit()
        print("Tables created.")
except Exception as e:
    print("Error:", e)
