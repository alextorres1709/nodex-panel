from app import app
from models import db, Task, User
from services import gcal
with app.app_context():
    u = User.query.filter_by(email="djalesito10@gmail.com").first()
    if not u: u = User.query.first()
    print("User:", u.email, "Connected:", gcal.is_connected(u.id))
    
    token_dict = gcal.get_token(u.id)
    if token_dict:
        creds = gcal._build_credentials(token_dict)
        print("Refresh needed?", gcal._refresh_if_needed(creds, token_dict, u.id))
        
