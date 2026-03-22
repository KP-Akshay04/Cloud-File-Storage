from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
import boto3

# ================= CONFIG =================

app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "home"   # 🔥 redirect if not logged in

# ================= S3 =================

bucket_name = "akshay-cloud-upload-2026"
s3 = boto3.client('s3', region_name='eu-north-1')

# ================= FILE VALIDATION =================

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ================= USER MODEL =================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)  # 🔥 prevent duplicates
    password = db.Column(db.String(200))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================

@app.route("/")
def home():
    return render_template("login.html")

# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # 🔥 check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return "User already exists"

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for("home"))

    return render_template("signup.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    user = User.query.filter_by(username=username).first()

    if user and bcrypt.check_password_hash(user.password, password):
        login_user(user)
        return redirect("/dashboard")

    return "Invalid credentials"

# ---------- DASHBOARD ----------
@app.route("/dashboard")
@login_required
def dashboard():
    files = []

    search_query = request.args.get('search', '').lower()

    response = s3.list_objects_v2(
        Bucket=bucket_name,
        Prefix=f"user_uploads/{current_user.id}/"
    )

    if 'Contents' in response:
        for obj in response['Contents']:
            key = obj['Key']

            if key.endswith('/'):
                continue

            filename = key.split('/')[-1]

            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': key},
                ExpiresIn=3600
            )

            if search_query in filename.lower():
                files.append({
                    "url": url,
                    "key": key,
                    "name": filename
                })

    return render_template("dashboard.html", files=files)

# ---------- UPLOAD ----------
@app.route("/upload", methods=["POST"])
@login_required
def upload():
    file = request.files.get('file')

    if not file or file.filename == "":
        return "No file selected"

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        s3_key = f"user_uploads/{current_user.id}/{filename}"

        s3.upload_fileobj(file, bucket_name, s3_key)

        return redirect("/dashboard")

    return "Invalid file type"

# ---------- DELETE ----------
@app.route('/delete', methods=['POST'])
@login_required
def delete():
    key = request.form.get('key')

    if key:
        s3.delete_object(Bucket=bucket_name, Key=key)

    return redirect('/dashboard')

# ---------- LOGOUT (FIXED) ----------
@app.route("/logout")
@login_required
def logout():
    logout_user()   # 🔥 this is enough
    return redirect("/")

@app.route("/files")
@login_required
def all_files():
    return redirect("/dashboard")  # for now reuse dashboard

@app.route("/profile")
@login_required
def profile():
    return {
        "username": current_user.username,
        "id": current_user.id
    }

# ---------- ERROR HANDLER ----------
@app.errorhandler(413)
def too_large(e):
    return "File is too large (Max 10MB)", 413

# ================= RUN =================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(host="0.0.0.0", port=8000)