import uuid
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, String, Text
from sqlalchemy.orm import Session

from neveai.internal.db import Base, get_db_context
from neveai.models.users import UserModel, Users


class Auth(Base):
    __tablename__ = "auth"

    id = Column(String, primary_key=True, unique=True)
    email = Column(String)
    password = Column(Text)
    active = Column(Boolean)


class Token(BaseModel):
    token: str
    token_type: str


class AuthsTable:
    def insert_new_auth(
        self,
        email: str,
        password: str,
        name: str,
        profile_image_url: str = "/user.png",
        role: str = "admin",
        db: Optional[Session] = None,
    ) -> Optional[UserModel]:
        with get_db_context(db) as session:
            user_id = str(uuid.uuid4())
            auth = Auth(
                id=user_id,
                email=email,
                password=password,
                active=True,
            )
            session.add(auth)
            user = Users.insert_new_user(
                user_id,
                name,
                email,
                profile_image_url,
                role,
                db=session,
            )
            session.commit()
            return user


Auths = AuthsTable()
