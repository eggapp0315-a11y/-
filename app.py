from flask import (
    Flask, render_template, redirect, request,
    flash, url_for, session, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
import uuid
import os
from flask_migrate import Migrate
from flask_migrate import Migrate


# ========================
# Flask 基本設定
# ========================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# ========================
# 資料庫設定
# ========================
database_url = os.environ.get("DATABASE_URL")

if database_url:
    # 修正 Render / Supabase 可能出現的舊格式
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # 本機開發用
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///math.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.permanent_session_lifetime = timedelta(days=7)

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ========================
# 流量限制
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
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================
# 資料庫模型
# ========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default="student")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(20))
    email = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    replied = db.Column(db.Boolean, default=False)



# ========================
# 管理員權限
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

    # 修正圖片路徑（讓前端可以正常顯示）
    for n in news_list:
        if n.filename:
            n.image_url = url_for("static", filename=f"uploads/{n.filename}")
        else:
            n.image_url = None

    return render_template("news.html", news_list=news_list)



@app.route("/about")
def about():
    return render_template("about.html")
#======#
#施展
#======#
@app.route("/zanzan")
def zanzan():
    return render_template("zanzan.html")

@app.route("/class")
def class_page():
    return render_template("class.html")

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
# 登入
# ========================
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("90 per minute")
def login():
    if request.method == "POST":
        user = User.query.filter_by(
            username=request.form["username"]
        ).first()

        if user and user.check_password(request.form["password"]):
            session.permanent = True
            session["user_id"] = user.id
            session["role"] = user.role

            return redirect(
                url_for("admin_users")
                if user.role == "admin"
                else url_for("home")
            )

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
# 聯絡我們
# ========================
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        grade = request.form.get("grade")
        email = request.form.get("email")
        message = request.form.get("message")

        if not name or not message:
            flash("❌ 請填寫必要欄位")
            return redirect(url_for("contact"))

        contact_msg = ContactMessage(
            name=name,
            grade=grade,
            email=email,
            message=message
        )

        try:
            db.session.add(contact_msg)
            db.session.commit()
            flash("✅ 已成功送出，我們會盡快與您聯絡")
        except Exception as e:
            db.session.rollback()
            print("DB ERROR:", e)
            flash("❌ 系統錯誤，請稍後再試")

        return redirect(url_for("contact"))

    return render_template("contact.html")

@app.route("/admin/users")
def admin_users():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user or user.role != "admin":
        return redirect(url_for("home"))

    users = User.query.all()
    return render_template("admin_users.html", users=users)



#新增訊息
@app.route("/admin/news/new", methods=["GET", "POST"])
def admin_new_news():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user or user.role != "admin":
        return redirect(url_for("home"))

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")

        new_news = News(title=title, content=content)
        db.session.add(new_news)
        db.session.commit()

        return redirect(url_for("home"))

    return render_template("admin_new_news.html")

# ========================
# 管理員訊息列表
# ========================
@app.route("/admin/contacts")
@admin_required
def admin_contacts():
    messages = ContactMessage.query.order_by(
        ContactMessage.created_at.desc()
    ).all()
    return render_template("admin_contacts.html", messages=messages)


# ========================
# 管理員回覆（SendGrid 版本）
# ========================
@app.route("/admin/contacts/reply/<int:msg_id>", methods=["GET", "POST"])
@admin_required
def reply_contact(msg_id):
    msg = ContactMessage.query.get_or_404(msg_id)

    if request.method == "POST":
        reply_text = request.form.get("reply")

        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        sg_key = os.environ.get("SENDGRID_API_KEY")
        mail_from = os.environ.get("MAIL_FROM")

        if not sg_key or not mail_from:
            flash("❌ 郵件系統未設定")
            return redirect(url_for("admin_contacts"))

        mail = Mail(
            from_email=mail_from,
            to_emails=msg.email,
            subject="回覆您的聯絡訊息",
            plain_text_content=reply_text
        )

        try:
            sg = SendGridAPIClient(sg_key)
            sg.send(mail)
            msg.replied = True
            db.session.commit()
            flash("✅ 已成功回覆")
        except Exception as e:
            db.session.rollback()
            print("SENDGRID ERROR:", e)
            flash("❌ 寄信失敗")

        return redirect(url_for("admin_contacts"))

    return render_template("reply_contact.html", msg=msg)

#刪除訊息
@app.route("/admin/news/delete/<int:news_id>", methods=["POST"])
@admin_required
def admin_delete_news(news_id):
    news = News.query.get_or_404(news_id)
    # 如果有上傳檔案，先刪掉
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
# 自動升級指定帳號為 admin
# ========================



# ========================
# 建立資料表（Render 需要）
# ========================
if __name__ == "__main__":
    app.run(debug=False)
#上傳 #git add .
# #git commit -m"update project"
# #git push
