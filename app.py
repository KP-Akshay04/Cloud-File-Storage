from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_bcrypt import Bcrypt
import boto3

app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)

bucket_name = "akshay-cloud-upload-2026"

s3 = boto3.client('s3', region_name='eu-north-1')


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    password = db.Column(db.String(200))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/")
def home():
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form["username"]
        password = bcrypt.generate_password_hash(request.form["password"]).decode('utf-8')

        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/login", methods=["POST"])
def login():

    username = request.form["username"]
    password = request.form["password"]

    user = User.query.filter_by(username=username).first()

    if user and bcrypt.check_password_hash(user.password, password):
        login_user(user)
        return redirect("/dashboard")

    return "Invalid credentials"


@app.route("/dashboard")
@login_required
def dashboard():

    objects = s3.list_objects_v2(Bucket=bucket_name)

    files = []

    if 'Contents' in objects:
        for obj in objects['Contents']:
            files.append(obj['Key'])

    return render_template("dashboard.html", files=files)


@app.route("/upload", methods=["POST"])
@login_required
def upload():

    file = request.files.get("file")

    if not file or file.filename == "":
        return "No file selected"

    s3.upload_fileobj(file, bucket_name, file.filename)

    return redirect("/dashboard")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)