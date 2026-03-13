from sqlalchemy import Column, Integer, String, Text
from .database import Base

class Inscription(Base):
    __tablename__ = "inscriptions"

    id = Column(Integer, primary_key=True, index=True)
    serial_num = Column(String, index=True)  # 文档编号 (如：【017】)
    name = Column(String, index=True)        # 器名 (核心检索字段)
    era = Column(String)                     # 时代
    alias = Column(String)                   # 别称
    discovery = Column(String)               # 出土/发现地
    collection = Column(String)              # 现藏地点
    publication = Column(String)             # 主要著录
    format = Column(String)                  # 形制
    transcript = Column(Text)                # 释文 (支持长文本)
    image_url = Column(Text)                 # 图片存储路径 (JSON list of strings)
