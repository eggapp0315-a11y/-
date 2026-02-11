# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime


# 初始化 SQLAlchemy
db = SQLAlchemy()


# 聯絡訊息模型
class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)  # 訊息 ID
    name = db.Column(db.String(100), nullable=False)  # 使用者姓名
    email = db.Column(db.String(100), nullable=False)  # 使用者 Email
    message = db.Column(db.Text, nullable=False)  # 訊息內容
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # 建立時間
    replied = db.Column(db.Boolean, default=False)  # 是否已回覆

    def __repr__(self):
        return f"<ContactMessage id={self.id} email={self.email} replied={self.replied}>"
