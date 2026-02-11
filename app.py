from flask import (
    Flask, render_template, redirect, request,
    flash, url_for, session, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps   # 【功能】權限 decorator
import uuid                   # 【功能】產生唯一檔名
import os

# ========================
# Flask 基本設定
# ========================
app = Flask(__name__)

# 🔐 功能：使用 Render 的環境變數當 SECRET_KEY
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# ========================
# 資料庫設定（修正 Render PostgreSQL 問題）
# ========================
database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///math.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.permanent_session_lifetime = timedelta(days=7)

db = SQLAlchemy(app)


# ========================
# 流量限制（防止暴力登入）
# ========================
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://"
)
limiter.init_app(app)

# ========================
# Gmail 郵件設定
# ========================
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=465,
    MAIL_USE_SSL=True,
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_DEFAULT_SENDER=MAIL_USERNAME
)

mail = Mail(app)

# ========================
# 上傳檔案設定
# ========================
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"jpg", "png", "pdf", "zip", "docx"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """【功能】檢查檔案副檔名是否合法"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ========================
# 資料庫模型
# ========================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # 👤 使用者帳號（唯一）
    username = db.Column(db.String(50), unique=True, nullable=False)

    # 🔐 密碼雜湊（使用 Text，避免長度不足造成 500 錯誤）
    password_hash = db.Column(db.Text, nullable=False)

    # 🧑‍🎓 使用者角色：student / admin
    role = db.Column(db.String(20), default="student")

    # 設定密碼（自動產生安全雜湊）
    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    # 驗證密碼
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # 📰 最新消息標題
    title = db.Column(db.String(100), nullable=False)

    # 📝 最新消息內容（可很長）
    content = db.Column(db.Text, nullable=False)

    # 📎 附件檔名（可選）
    filename = db.Column(db.String(200))

    # 📅 發布時間
    date = db.Column(db.DateTime, default=datetime.utcnow)


# ========================
# 管理員權限 decorator
# 【功能】保護所有 admin 頁面
# ========================
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            flash("❌ 無權限")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated

# ========================
# 前台頁面
# ========================
@app.route("/")
def root():
    return redirect(url_for("home"))

@app.route("/home")
def home():
    return render_template("index.html")

@app.route("/teaching")
def teaching():
    return render_template("teaching.html")

@app.route("/news")
def news():
    news_list = News.query.order_by(News.date.desc()).all()
    return render_template("news.html", news_list=news_list)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/class")
def class_page():
    return render_template("class.html")

# ========================
# 聯絡我們（安全版）
# ========================
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        grade = request.form.get("grade")
        email = request.form.get("email")
        message = request.form.get("message")

        # 判斷是否在 Render
        on_render = os.environ.get("RENDER") is not None

        # Render 上不寄信，避免 WORKER TIMEOUT
        if on_render:
            # 之後可改成存資料庫 / webhook
            flash("✅ 已收到您的訊息，我們會盡快與您聯絡")
            return redirect(url_for("contact"))

        # 本機或其他環境才寄 Gmail
        if not MAIL_USERNAME or not MAIL_PASSWORD:
            flash("❌ 郵件系統尚未設定完成")
            return redirect(url_for("contact"))

        msg = Message(
            subject=f"📩 聯絡訊息來自 {name}",
            recipients=[MAIL_USERNAME],
            body=f"""姓名：{name}
年級：{grade}
Email：{email}

內容：
{message}
"""
        )

        try:
            mail.send(msg)
            flash("✅ 已成功送出")
        except Exception as e:
            print("MAIL ERROR:", e)
            flash("❌ 郵件系統暫時忙碌，請稍後再試")

        return redirect(url_for("contact"))

    return render_template("contact.html")



# ========================
# 註冊
# ========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        if password != confirm:
            flash("❌ 密碼不一致")
            return redirect(url_for("register"))

        if len(password) < 4:
            flash("❌ 密碼至少 4 碼")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("❌ 帳號已存在")
            return redirect(url_for("register"))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("✅ 註冊成功")
        return redirect(url_for("login"))

    return render_template("register.html")

# ========================
# 登入（限制 5 次/分鐘）
# ========================
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        if user and user.check_password(request.form["password"]):
            session.permanent = True
            session["user_id"] = user.id
            session["role"] = user.role

            return redirect(url_for("admin_users") if user.role == "admin" else url_for("home"))

        flash("❌ 帳號或密碼錯誤")

    return render_template("login.html")

# ========================
# 登出
# ========================
@app.route("/logout")
def logout():
    session.clear()
    flash("✅ 已登出")
    return redirect(url_for("home"))

# ========================
# 管理員：新增消息
# ========================
@app.route("/admin/news/new", methods=["GET", "POST"])
@admin_required
def admin_new_news():
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        file = request.files.get("image")

        filename = None
        if file and allowed_file(file.filename):
            # 【功能】避免檔名重複覆蓋
            ext = file.filename.rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        db.session.add(News(title=title, content=content, filename=filename))
        db.session.commit()

        flash("✅ 新消息已新增")
        return redirect(url_for("news"))

    return render_template("admin_new_news.html")

# ========================
# 管理員：使用者管理
# ========================
@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    users = User.query.all()

    if request.method == "POST":
        user = User.query.get(request.form.get("user_id"))
        action = request.form.get("action")

        if action == "demote" and user.id == session["user_id"]:
            flash("❌ 不能降級自己")
            return redirect(url_for("admin_users"))

        user.role = "admin" if action == "promote" else "student"
        db.session.commit()
        flash("✅ 權限已更新")

    return render_template("admin_users.html", users=users)

# ========================
# 管理員：刪除消息
# ========================
@app.route("/admin/news/delete/<int:news_id>", methods=["POST"])
@admin_required
def admin_delete_news(news_id):
    news = News.query.get_or_404(news_id)

    if news.filename:
        path = os.path.join(app.config["UPLOAD_FOLDER"], news.filename)
        if os.path.exists(path):
            os.remove(path)

    db.session.delete(news)
    db.session.commit()
    flash("🗑️ 消息已刪除")

    return redirect(url_for("news"))

# ========================
# Google 驗證
# ========================
@app.route("/google77b51b745d5d14fa.html")
def google_verify():
    return send_from_directory(".", "google77b51b745d5d14fa.html")

# ========================
# 啟動
# ========================
# ========================
# 啟動 & 自動建立資料表
# ========================
with app.app_context():
    # db.drop_all()     # 刪除舊資料表
    db.create_all()   # 建立新資料表


if __name__ == "__main__":
    app.run(debug=False)







#上傳
#git add .
#git commit -m "update project"
#git push
