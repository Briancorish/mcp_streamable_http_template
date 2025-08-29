import os
import json
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin
from sqlalchemy import create_engine, select, update, insert, delete
from sqlalchemy.orm import sessionmaker
import secrets

# This is a workaround to import from the parent directory
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import UserCredentials
from database import Base, get_database_url

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))

# --- Database Setup (Sync) ---
# Create a sync-specific engine and session maker for the Flask app
sync_database_url = get_database_url(is_async=False)
sync_engine = create_engine(sync_database_url)
SessionLocal = sessionmaker(bind=sync_engine)


# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# Google OAuth setup
def get_google_client_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("REDIRECT_URI", "http://localhost:5000/oauth2callback")
    
    if not client_id or not client_secret:
        logging.error("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.")
        return None

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    }

SCOPES = ['https://www.googleapis.com/auth/calendar']

@app.route('/')
@login_required
def index():
    """Main dashboard"""
    with SessionLocal() as db:
        credentials = db.execute(select(UserCredentials)).scalars().all()
    return render_template('index.html', credentials=credentials)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        admin_user = os.getenv('ADMIN_USERNAME', 'admin')
        admin_pass = os.getenv('ADMIN_PASSWORD')
        
        if not admin_pass:
            flash('ADMIN_PASSWORD is not set. Cannot log in.')
            return render_template('login.html')

        if username == admin_user and password == admin_pass:
            user = User('admin')
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/oauth2authorize/<user_id>')
@login_required
def oauth2authorize(user_id):
    """Start OAuth2 flow"""
    client_config = get_google_client_config()
    if not client_config:
        flash("Google OAuth is not configured on the server. Set environment variables.")
        return redirect(url_for('index'))

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    session['state'] = state
    session['user_id'] = user_id
    
    return redirect(authorization_url)

@app.route('/oauth2callback')
@login_required
def oauth2callback():
    """Handle OAuth2 callback"""
    state = session.get('state')
    if not state or state != request.args.get('state'):
        flash('State mismatch. Please try again.')
        return redirect(url_for('index'))

    user_id = session.get('user_id', 'default')
    
    client_config = get_google_client_config()
    if not client_config:
        flash("Google OAuth is not configured on the server.")
        return redirect(url_for('index'))

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    
    flow.fetch_token(authorization_response=request.url)
    
    credentials = flow.credentials
    
    with SessionLocal() as db:
        existing = db.execute(
            select(UserCredentials).where(UserCredentials.user_id == user_id)
        ).scalar_one_or_none()
        
        token_data = json.dumps({"access_token": credentials.token})
        
        if existing:
            db.execute(
                update(UserCredentials)
                .where(UserCredentials.user_id == user_id)
                .values(
                    client_id=credentials.client_id,
                    client_secret=credentials.client_secret,
                    token=token_data,
                    refresh_token=credentials.refresh_token
                )
            )
        else:
            new_cred = UserCredentials(
                user_id=user_id,
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                token=token_data,
                refresh_token=credentials.refresh_token
            )
            db.add(new_cred)
        
        db.commit()
    
    flash(f'Credentials saved successfully for user {user_id}')
    return redirect(url_for('index'))

@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    """Add new user for OAuth setup"""
    user_id = request.form['user_id']
    if not user_id:
        flash("User ID cannot be empty.")
        return redirect(url_for('index'))
    return redirect(url_for('oauth2authorize', user_id=user_id))

@app.route('/delete_credentials/<int:cred_id>')
@login_required
def delete_credentials(cred_id):
    """Delete user credentials"""
    with SessionLocal() as db:
        db.execute(
            delete(UserCredentials).where(UserCredentials.id == cred_id)
        )
        db.commit()
    
    flash(f'Credentials deleted.')
    return redirect(url_for('index'))

def create_db_tables():
    Base.metadata.create_all(sync_engine)

if __name__ == '__main__':
    create_db_tables()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
