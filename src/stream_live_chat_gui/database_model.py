from sqlalchemy import Column, Text, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


# Test related definition
# def waited_time(context):
#     print("Access model here!")
#     print(context.get_current_parameters())
#     print(type(context.get_current_parameters()))
#     return context.get_current_parameters()["created_ts"]


# https://www.fatalerrors.org/a/default-value-attribute-of-column-in-sqlalchemy.html
class Question(Base):
    __tablename__ = "question"
    id = Column(Integer, autoincrement=True, primary_key=True)
    question = Column(
        Text(),
        nullable=False,
    )
    user_id = Column(Text(), ForeignKey("user.id"))
    user = relationship("User", back_populates="questions")
    created_ts = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    replied_ts = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    is_replied = Column(Boolean, default=False)
    is_super_chat = Column(Boolean, default=False)

    waited = Column(
        Text(),
        server_default="00:00",
        nullable=True,
    )

    def __repr__(self) -> str:
        return "<Question(%r, %r)>" % (self.id, self.question)


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column(Text(), unique=True)
    questions = relationship(
        "Question", back_populates="user", cascade="all, delete, delete-orphan"
    )

    def __repr__(self) -> str:
        return "<User(%r, %r)>" % (self.id, self.name)
