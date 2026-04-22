import traceback
from app import app
from models import db, Task, User
from services import gcal

with app.app_context():
    u = User.query.filter_by(email="djalesito10@gmail.com").first()
    if not u: u = User.query.first()
    print("User:", u.email)
    
    t = Task.query.order_by(Task.id.desc()).first()
    print("Task:", t.title, "Created:", t.created_at)
    
    try:
        from googleapiclient.discovery import build
        token_dict = gcal.get_token(u.id)
        if not token_dict:
            print("No token dict")
            exit()
            
        creds = gcal._build_credentials(token_dict)
        gcal._refresh_if_needed(creds, token_dict, u.id)
        
        service = build("tasks", "v1", credentials=creds, cache_discovery=False)
        
        body = {
            "title": t.title,
            "notes": t.description or "",
        }
        
        c_date_str = None
        if hasattr(t, "created_at"):
            try:
                if hasattr(t.created_at, "date"):
                    c_date_str = t.created_at.date().isoformat()
                elif isinstance(t.created_at, str):
                    c_date_str = t.created_at[:10]
            except Exception as ex:
                print("Error extracting date:", ex)
                
        if c_date_str:
            body["due"] = f"{c_date_str}T00:00:00.000Z"
        
        print("Body:", body)
        
        # Test insert
        print("Inserting task into @default list...")
        result = service.tasks().insert(tasklist="@default", body=body).execute()
        print("Success:", result)
        
    except Exception as e:
        print("Exception occurred:")
        traceback.print_exc()

