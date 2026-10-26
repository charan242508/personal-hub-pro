import os
from datetime import timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import or_, func
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import click

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-only-change-this-jwt-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///personal_hub.db")
if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
jwt = JWTManager(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["300 per hour"], storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    records = db.relationship("Person", backref="owner", cascade="all, delete-orphan", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False, default="")
    phone = db.Column(db.String(40), nullable=False, default="")
    category = db.Column(db.String(60), nullable=False, default="Personal")
    city = db.Column(db.String(100), nullable=False, default="")
    notes = db.Column(db.String(2000), nullable=False, default="")
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not app.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

@app.cli.command("init-db")
def init_db():
    """Create database tables."""
    with app.app_context():
        db.create_all()
    click.echo("Database tables created.")

@app.cli.command("make-admin")
@click.argument("email")
def make_admin(email):
    """Promote an existing account to admin: flask --app app make-admin you@example.com"""
    user = User.query.filter_by(email=email.lower().strip()).first()
    if not user:
        raise click.ClickException("No account with that email exists. Register first.")
    user.role = "admin"
    db.session.commit()
    click.echo(f"{user.email} is now an admin.")

def valid_password(password):
    return isinstance(password, str) and len(password) >= 12 and len(password) <= 128

@app.route("/")
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    q = request.args.get("q", "").strip()[:120]
    category = request.args.get("category", "").strip()[:60]
    query = Person.query.filter_by(owner_id=current_user.id)
    if q:
        pattern = f"%{q}%"
        query = query.filter(or_(Person.full_name.ilike(pattern), Person.email.ilike(pattern),
                                 Person.phone.ilike(pattern), Person.city.ilike(pattern)))
    if category:
        query = query.filter_by(category=category)
    people = query.order_by(Person.full_name.asc()).all()
    total = Person.query.filter_by(owner_id=current_user.id).count()
    categories = [r[0] for r in db.session.query(Person.category).filter_by(owner_id=current_user.id).distinct().order_by(Person.category).all()]
    return render_template("dashboard.html", people=people, total=total, categories=categories, q=q, selected_category=category)

@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not display_name or len(display_name) > 100 or not email or len(email) > 254:
            flash("Please provide a name and valid email.", "error")
        elif not valid_password(password):
            flash("Use a password between 12 and 128 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(display_name=display_name, email=email, role="user")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created. You are signed in.", "success")
            return redirect(url_for("home"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session.clear()
            login_user(user)
            return redirect(url_for("home"))
        flash("Email or password was incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("login"))

def record_form_data():
    return {
        "full_name": request.form.get("full_name", "").strip()[:120],
        "email": request.form.get("email", "").strip()[:254],
        "phone": request.form.get("phone", "").strip()[:40],
        "category": request.form.get("category", "Personal").strip()[:60] or "Personal",
        "city": request.form.get("city", "").strip()[:100],
        "notes": request.form.get("notes", "").strip()[:2000],
    }

@app.post("/records/add")
@login_required
def add_record():
    data = record_form_data()
    if not data["full_name"]:
        flash("Full name is required.", "error")
        return redirect(url_for("home"))
    db.session.add(Person(owner_id=current_user.id, **data))
    db.session.commit()
    flash("Record added.", "success")
    return redirect(url_for("home"))

@app.post("/records/<int:record_id>/edit")
@login_required
def edit_record(record_id):
    person = Person.query.filter_by(id=record_id, owner_id=current_user.id).first_or_404()
    data = record_form_data()
    if not data["full_name"]:
        flash("Full name is required.", "error")
        return redirect(url_for("home"))
    for key, value in data.items():
        setattr(person, key, value)
    db.session.commit()
    flash("Record updated.", "success")
    return redirect(url_for("home"))

@app.post("/records/<int:record_id>/delete")
@login_required
def delete_record(record_id):
    person = Person.query.filter_by(id=record_id, owner_id=current_user.id).first_or_404()
    db.session.delete(person)
    db.session.commit()
    flash("Record deleted.", "success")
    return redirect(url_for("home"))

def person_json(p):
    return {"id": p.id, "full_name": p.full_name, "email": p.email, "phone": p.phone,
            "category": p.category, "city": p.city, "notes": p.notes}

# The extension uses short-lived bearer tokens rather than website cookies.
@app.post("/api/auth/login")
@csrf.exempt
@limiter.limit("10 per minute")
def api_login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not isinstance(password, str) or not user.check_password(password):
        return jsonify(error="Email or password was incorrect."), 401
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return jsonify(access_token=token, user={"display_name": user.display_name, "email": user.email}), 200

@app.get("/api/me")
@csrf.exempt
@jwt_required()
def api_me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify(error="Account not found."), 401
    return jsonify(display_name=user.display_name, email=user.email, role=user.role)

@app.get("/api/records")
@csrf.exempt
@jwt_required()
def api_records():
    user_id = int(get_jwt_identity())
    people = Person.query.filter_by(owner_id=user_id).order_by(Person.full_name.asc()).all()
    return jsonify([person_json(p) for p in people])

@app.post("/api/records")
@csrf.exempt
@jwt_required()
def api_add_record():
    data = request.get_json(silent=True) or {}
    name = str(data.get("full_name", "")).strip()
    if not name or len(name) > 120:
        return jsonify(error="Full name is required (maximum 120 characters)."), 400
    p = Person(owner_id=int(get_jwt_identity()), full_name=name,
        email=str(data.get("email", "")).strip()[:254],
        phone=str(data.get("phone", "")).strip()[:40],
        category=str(data.get("category", "Personal")).strip()[:60] or "Personal",
        city=str(data.get("city", "")).strip()[:100],
        notes=str(data.get("notes", "")).strip()[:2000])
    db.session.add(p)
    db.session.commit()
    return jsonify(person_json(p)), 201

@app.put("/api/records/<int:record_id>")
@csrf.exempt
@jwt_required()
def api_edit_record(record_id):
    p = Person.query.filter_by(id=record_id, owner_id=int(get_jwt_identity())).first_or_404()
    data = request.get_json(silent=True) or {}
    name = str(data.get("full_name", "")).strip()
    if not name or len(name) > 120:
        return jsonify(error="Full name is required (maximum 120 characters)."), 400
    p.full_name = name
    for field, limit in [("email",254),("phone",40),("category",60),("city",100),("notes",2000)]:
        setattr(p, field, str(data.get(field, getattr(p, field))).strip()[:limit])
    db.session.commit()
    return jsonify(person_json(p))

@app.delete("/api/records/<int:record_id>")
@csrf.exempt
@jwt_required()
def api_delete_record(record_id):
    p = Person.query.filter_by(id=record_id, owner_id=int(get_jwt_identity())).first_or_404()
    db.session.delete(p)
    db.session.commit()
    return jsonify(ok=True)

@app.get("/health")
def health():
    return jsonify(status="ok")

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
