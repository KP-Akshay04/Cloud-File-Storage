from flask import Flask, render_template, request, redirect, url_for, jsonify
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
login_manager.login_view = "login"

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
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================

@app.route("/")
def home():
    return redirect("/login")

# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return redirect("/login")

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        user = User(username=username, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        return redirect("/login")

    return render_template("signup.html")

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect("/dashboard")

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            return redirect("/login")

        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect("/dashboard")

        return redirect("/login")

    return render_template("login.html")

# ---------- DASHBOARD ----------
@app.route('/dashboard')
@login_required
def dashboard():
    user_prefix = f"{current_user.id}/"

    response = s3.list_objects_v2(
        Bucket=bucket_name,
        Prefix=user_prefix
    )

    files = []

    if 'Contents' in response:
        for obj in response['Contents']:
            key = obj['Key']

            if key.endswith('/'):
                continue

            files.append({
                "name": key.split('/')[-1],
                "key": key,
                "url": f"https://{bucket_name}.s3.amazonaws.com/{key}"
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

        s3_key = f"{current_user.id}/{filename}"

        s3.upload_fileobj(
            file,
            bucket_name,
            s3_key,
            ExtraArgs={
                "ContentType": file.content_type,
                "ContentDisposition": "inline"
            }
        )

        return redirect("/dashboard")

    return "Invalid file type"

# ---------- DELETE ----------
@app.route("/delete", methods=["POST"])
@login_required
def delete():
    key = request.form.get("key")

    s3.copy_object(
        Bucket=bucket_name,
        CopySource={'Bucket': bucket_name, 'Key': key},
        Key=f"trash/{key}"
    )

    s3.delete_object(Bucket=bucket_name, Key=key)

    return redirect("/dashboard")

# ---------- PREVIEW ----------
@app.route('/preview/<path:file_key>')
@login_required
def preview_file(file_key):
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': file_key
            },
            ExpiresIn=300
        )

        return jsonify({
            "url": url,
            "type": file_key.split('.')[-1].lower()
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------- FILES ----------
@app.route("/files")
@login_required
def files():
    return redirect("/dashboard")

# ---------- RECENT ----------
@app.route("/recent")
@login_required
def recent():
    response = s3.list_objects_v2(Bucket=bucket_name)

    files = []

    if 'Contents' in response:
        sorted_files = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)

        for obj in sorted_files[:5]:
            key = obj['Key']

            if key.endswith("/"):
                continue

            files.append({
                "name": key.split("/")[-1],
                "key": key,
                "url": f"https://{bucket_name}.s3.amazonaws.com/{key}"
            })

    return render_template("dashboard.html", files=files)

# ---------- TRASH ----------
@app.route("/trash")
@login_required
def trash():
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix="trash/")

    files = []

    if 'Contents' in response:
        for obj in response['Contents']:
            key = obj['Key']

            if key.endswith("/"):
                continue

            files.append({
                "name": key.split("/")[-1],
                "key": key,
                "url": f"https://{bucket_name}.s3.amazonaws.com/{key}"
            })

    return render_template("dashboard.html", files=files)

# ---------- LOGOUT ----------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# ---------- ERROR ----------
@app.errorhandler(413)
def too_large(e):
    return "File too large (Max 10MB)", 413

# ================= RUN =================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(host="0.0.0.0", port=8000)