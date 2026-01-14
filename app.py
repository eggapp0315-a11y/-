from flask import Flask, render_template, redirect, request, flash, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
import json
import os
# ========================
# Flask 與資料庫設定
# ========================
app = Flask(__name__)
app.secret_key = "你的密鑰"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///math.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ========================
# Gmail 郵件設定
# ⚠️ 正式上線請改用環境變數
# ========================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.environ.get("MAIL_USERNAME", "eggapp0315@gmail.com")
app.config['MAIL_PASSWORD'] = os.environ.get("MAIL_PASSWORD", "krzg kfui mcgs gray")
mail = Mail(app)


# ========================
# 資料庫模型
# ========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    grade = db.Column(db.String(10))
    courses = db.Column(db.Text)
    scores = db.Column(db.Text)
    user = db.relationship("User", backref="student_profile")


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    grade_id = db.Column(db.Integer, db.ForeignKey("grade.id"), nullable=False)
    topic = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    grade = db.relationship("Grade", backref="lessons")

# ========================
# 路由
# ========================
@app.route("/")
def root():
    return redirect(url_for("home"))

@app.route("/home")
def home():
    grades = Grade.query.all()
    return render_template("index.html", grades=grades)

@app.route("/<grade_code>/<topic>")
def lesson(grade_code, topic):
    lesson = Lesson.query.join(Grade).filter(Grade.code == grade_code, Lesson.topic == topic).first()
    if not lesson:
        return "找不到課程", 404
    return render_template(
        "lesson.html",
        grade_name=lesson.grade.name,
        title=lesson.title,
        content=lesson.content
    )

# ========================
# Google HTML 驗證
# ========================
@app.route('/google77b51b745d5d14fa.html')
def google_verification():
    # 把 Google 驗證 HTML 放在 static 目錄下
    return send_from_directory('static', 'google77b51b745d5d14fa.html')

# ========================
# 聯絡我們
# ========================
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        message = request.form["message"]

        msg = Message(
            subject=f"聯絡我們訊息來自 {name}",
            sender=app.config["MAIL_USERNAME"],
            recipients=[app.config["MAIL_USERNAME"]],
            body=f"姓名: {name}\nEmail: {email}\n訊息:\n{message}"
        )

        try:
            mail.send(msg)
            flash("✅ 訊息已送出", "success")
        except Exception as e:
            flash(f"❌ 送信失敗：{e}", "error")

        return redirect(url_for("home"))

    return render_template("contact.html")

# ========================
# 註冊
# ========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if User.query.filter_by(username=username).first():
            flash("帳號已存在")
            return redirect(url_for("register"))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        student = Student(
            user_id=user.id,
            grade="",
            courses=json.dumps({}),
            scores=json.dumps({})
        )
        db.session.add(student)
        db.session.commit()

        flash("✅ 註冊成功，請登入")
        return redirect(url_for("home"))  # 註冊後回首頁登入 Modal 顯示

    return render_template("register.html")

# ========================
# 登入（Modal 用）
# ========================
@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        session["user_id"] = user.id
        session["role"] = user.role

        if user.role == "student":
            return redirect(url_for("student_dashboard"))

        return redirect(url_for("home"))

    flash("帳號或密碼錯誤！", "login_error")
    return redirect(url_for("home"))

# ========================
# 學生專屬頁面
# ========================
@app.route("/student")
def student_dashboard():
    if "user_id" not in session or session.get("role") != "student":
        flash("請先登入學生帳號", "login_error")
        return redirect(url_for("home"))

    student = Student.query.filter_by(user_id=session["user_id"]).first()
    courses = json.loads(student.courses) if student.courses else {}
    scores = json.loads(student.scores) if student.scores else {}

    return render_template(
        "student.html",
        student=student,
        courses=courses,
        scores=scores
    )

# ========================
# 管理員新增課程
# ========================
@app.route("/admin/lesson/new", methods=["GET", "POST"])
def admin_new_lesson():
    grades = Grade.query.all()

    if request.method == "POST":
        lesson = Lesson(
            grade_id=request.form["grade_id"],
            topic=request.form["topic"],
            title=request.form["title"],
            content=request.form["content"]
        )
        db.session.add(lesson)
        db.session.commit()
        return redirect(url_for("home"))

    return render_template("admin_new_lesson.html", grades=grades)



# ========================
# 初始化資料
# ========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        if Grade.query.count() == 0:
            g7 = Grade(code="grade7", name="七年級數學")
            db.session.add(g7)
            db.session.commit()

            db.session.add_all([
                Lesson(grade_id=g7.id, topic="fraction", title="分數", content="分數由分子與分母組成"),
                Lesson(grade_id=g7.id, topic="integer", title="整數", content="整數包含正負與 0")
            ])
            db.session.commit()

    app.run(debug=True)