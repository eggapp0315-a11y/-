from flask import (
    Flask, render_template, redirect, request,
    flash, url_for, session, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from datetime import timedelta
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ========================
# Flask 基本設定
# ========================
app = Flask(__name__)
app.secret_key = "你的密鑰"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///math.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.permanent_session_lifetime = timedelta(days=7)
db = SQLAlchemy(app)

# ========================
# 流量限制設定（Render 上線版）
# ========================
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)



# ========================
# Gmail 郵件設定（穩定版）
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
print("✅ MAIL_USERNAME =", MAIL_USERNAME)
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
    """檢查檔案副檔名是否允許上傳"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ========================
# 資料庫模型
# ========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default="student")  # student / admin

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(200))  # 上傳的檔名
    date = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# 權限檢查
# ========================
def admin_required():
    """檢查當前登入是否為管理員"""
    return "user_id" in session and session.get("role") == "admin"

# ========================
# 路由
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

#關於我們
@app.route("/about")
def about():
    return render_template("about.html")

#課程表
@app.route("/class")
def class_page():
    return render_template("class.html")

#gmail聯絡
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        grade = request.form.get("grade")
        email = request.form.get("email")
        message = request.form.get("message")

        if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
            flash("❌ 郵件功能尚未設定完成，請改用 IG / Line 聯絡", "error")
            return redirect(url_for("contact"))

        msg = Message(
            subject=f"📩 聯絡我們訊息來自 {name}",
            recipients=[app.config["MAIL_USERNAME"]],
            body=f"""姓名：{name}
年級：{grade}
Email：{email}

訊息內容：
{message}
"""
        )

        try:
            mail.send(msg)
            flash("✅ 訊息已成功送出，我們會盡快回覆你！", "success")
        except Exception as e:
            flash("❌ 送信失敗，請稍後再試或直接聯絡我們", "error")
            print(e)

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
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("❌ 兩次輸入的密碼不一致")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("❌ 帳號已存在")
            return redirect(url_for("register"))
        if len(password) == 4:
            flash("❌ 密碼至少 4 碼")
            return redirect(url_for("register"))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("✅ 註冊成功，請登入")
        return redirect(url_for("login"))

    return render_template("register.html")


# ========================
# 登入（分辨管理員與學生）
# ========================
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.permanent = True  # 這裡設定為永久 session
            session["user_id"] = user.id
            session["role"] = user.role

            # 分流
            if user.role == "admin":
                return redirect(url_for("admin_users"))
            else:
                return redirect(url_for("home"))

        flash("❌ 帳號或密碼錯誤")
        return redirect(url_for("login"))

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
# 管理員新增消息
# ========================
@app.route("/admin/news/new", methods=["GET", "POST"])
def admin_new_news():
    if "user_id" not in session or session.get("role") != "admin":
        flash("❌ 無權限")
        return redirect(url_for("home"))

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        file = request.files.get("image")  # 👈 這行修正

        filename = None
        if file and file.filename != "" and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        news = News(title=title, content=content, filename=filename)
        db.session.add(news)
        db.session.commit()

        flash("✅ 最新消息已新增")
        return redirect(url_for("news"))

    return render_template("admin_new_news.html")


# ========================
# 管理員管理使用者
# ========================
@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if not admin_required():
        flash("❌ 無權限")
        return redirect(url_for("home"))

    users = User.query.all()

    if request.method == "POST":
        user_id = request.form.get("user_id")
        action = request.form.get("action")
        user = User.query.get(user_id)

        if not user:
            flash("❌ 找不到使用者")
            return redirect(url_for("admin_users"))

        if action == "promote":
            user.role = "admin"
            flash(f"✅ {user.username} 已升級為管理員")
        elif action == "demote":
            user.role = "student"
            flash(f"✅ {user.username} 已降級為學生")

        db.session.commit()
        return redirect(url_for("admin_users"))

    return render_template("admin_users.html", users=users)

# ========================
# Google 驗證
# ========================
@app.route("/google77b51b745d5d14fa.html")
def google_verify():
    return send_from_directory(".", "google77b51b745d5d14fa.html")

# ========================
# CLI 指令：升級帳號為管理員
# ========================
@app.cli.command("make-admin")
def make_admin():
    username = input("請輸入要升級的帳號：")
    user = User.query.filter_by(username=username).first()

    if not user:
        print("❌ 找不到使用者")
        return

    user.role = "admin"
    db.session.commit()
    print(f"✅ {username} 已升級為管理員")
#刪除文章
@app.route("/admin/news/delete/<int:news_id>", methods=["POST"])
def admin_delete_news(news_id):
    # 權限檢查
    if "user_id" not in session or session.get("role") != "admin":
        flash("❌ 無權限")
        return redirect(url_for("home"))

    news = News.query.get_or_404(news_id)

    # 如果有檔案 → 一起刪掉
    if news.filename:
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], news.filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    db.session.delete(news)
    db.session.commit()

    flash("🗑️ 消息已刪除")
    return redirect(url_for("news"))

print("MAIL_USERNAME =", app.config["MAIL_USERNAME"])
print("MAIL_PASSWORD =", "有設定" if app.config["MAIL_PASSWORD"] else "沒有")

# ========================
# 啟動
# ========================
if __name__ == "__main__":
     with app.app_context():
         db.create_all()
     app.run(debug=False)





#上傳
#git add .
#git commit -m "update project"
#git push
