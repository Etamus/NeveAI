import time
from typing import Optional

from sqlalchemy.orm import Session, defer
from neveai.internal.db import (Base, get_db_context)


from neveai.env import DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL

import neveai.models.chats
from neveai.models.groups import GroupMember

from neveai.utils.misc import throttle
from neveai.utils.validate import validate_profile_image_url


from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import (BigInteger, JSON, Column, String, Boolean, Text, Date, exists, select)
from sqlalchemy import or_, case, func

import datetime

####################
# User DB Schema
####################


class UserSettings(BaseModel):
    ui: Optional[dict] = {}
    model_config = ConfigDict(extra="allow")
    pass


class User(Base):
    __tablename__ = "user"

    id = Column(String, primary_key=True, unique=True)
    email = Column(String)
    username = Column(String(50), nullable=True)
    role = Column(String)

    name = Column(String)

    profile_image_url = Column(Text)
    profile_banner_image_url = Column(Text, nullable=True)

    bio = Column(Text, nullable=True)
    gender = Column(Text, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    timezone = Column(String, nullable=True)

    presence_state = Column(String, nullable=True)
    status_emoji = Column(String, nullable=True)
    status_message = Column(Text, nullable=True)
    status_expires_at = Column(BigInteger, nullable=True)

    info = Column(JSON, nullable=True)
    settings = Column(JSON, nullable=True)

    oauth = Column(JSON, nullable=True)
    scim = Column(JSON, nullable=True)

    last_active_at = Column(BigInteger)
    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)


class UserModel(BaseModel):
    id: str

    email: str
    username: Optional[str] = None
    role: str = "pending"

    name: str

    profile_image_url: Optional[str] = None
    profile_banner_image_url: Optional[str] = None

    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None
    timezone: Optional[str] = None

    presence_state: Optional[str] = None
    status_emoji: Optional[str] = None
    status_message: Optional[str] = None
    status_expires_at: Optional[int] = None

    info: Optional[dict] = None
    settings: Optional[UserSettings] = None

    oauth: Optional[dict] = None
    scim: Optional[dict] = None

    last_active_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def set_profile_image_url(self):
        if not self.profile_image_url:
            self.profile_image_url = f"/api/v1/users/{self.id}/profile/image"
        return self


class UserStatusModel(UserModel):
    is_active: bool = False

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class UpdateProfileForm(BaseModel):
    profile_image_url: str
    name: str
    bio: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[datetime.date] = None

    @field_validator("profile_image_url")
    @classmethod
    def check_profile_image_url(cls, v: str) -> str:
        return validate_profile_image_url(v)


class UserGroupIdsModel(UserModel):
    group_ids: list[str] = []


class UserModelResponse(UserModel):
    model_config = ConfigDict(extra="allow")


class UserStatus(BaseModel):
    status_emoji: Optional[str] = None
    status_message: Optional[str] = None
    status_expires_at: Optional[int] = None


class UserInfoResponse(UserStatus):
    id: str
    name: str
    email: str
    role: str
    bio: Optional[str] = None
    groups: Optional[list] = []
    is_active: bool = False


class UserInfoListResponse(BaseModel):
    users: list[UserInfoResponse]
    total: int


class UserNameResponse(BaseModel):
    id: str
    name: str
    role: str


class UserResponse(UserNameResponse):
    email: str


class UserProfileImageResponse(UserNameResponse):
    email: str
    profile_image_url: str


class UsersTable:
    def insert_new_user(
        self,
        id: str,
        name: str,
        email: str,
        profile_image_url: str = "/user.png",
        role: str = "pending",
        username: Optional[str] = None,
        oauth: Optional[dict] = None,
        db: Optional[Session] = None,
    ) -> Optional[UserModel]:
        with get_db_context(db) as db:
            user = UserModel(
                **{
                    "id": id,
                    "email": email,
                    "name": name,
                    "role": role,
                    "profile_image_url": profile_image_url,
                    "last_active_at": int(time.time()),
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                    "username": username,
                    "oauth": oauth,
                }
            )
            result = User(**user.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            if result:
                return user
            else:
                return None

    def get_user_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        try:
            with get_db_context(db) as db:
                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_email(
        self, email: str, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        try:
            with get_db_context(db) as db:
                user = (
                    db.query(User)
                    .filter(func.lower(User.email) == email.lower())
                    .first()
                )
                return UserModel.model_validate(user) if user else None
        except Exception:
            return None

    def get_users(
        self,
        filter: Optional[dict] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> dict:
        with get_db_context(db) as db:
            # Join GroupMember so we can order by group_id when requested
            query = db.query(User).options(defer(User.profile_image_url))

            if filter:
                query_key = filter.get("query")
                if query_key:
                    query = query.filter(
                        or_(
                            User.name.ilike(f"%{query_key}%"),
                            User.email.ilike(f"%{query_key}%"),
                        )
                    )

                user_ids = filter.get("user_ids")
                group_ids = filter.get("group_ids")

                if isinstance(user_ids, list) and isinstance(group_ids, list):
                    # If both are empty lists, return no users
                    if not user_ids and not group_ids:
                        return {"users": [], "total": 0}

                if user_ids:
                    query = query.filter(User.id.in_(user_ids))

                if group_ids:
                    query = query.filter(
                        exists(
                            select(GroupMember.id).where(
                                GroupMember.user_id == User.id,
                                GroupMember.group_id.in_(group_ids),
                            )
                        )
                    )

                roles = filter.get("roles")
                if roles:
                    include_roles = [role for role in roles if not role.startswith("!")]
                    exclude_roles = [role[1:] for role in roles if role.startswith("!")]

                    if include_roles:
                        query = query.filter(User.role.in_(include_roles))
                    if exclude_roles:
                        query = query.filter(~User.role.in_(exclude_roles))

                order_by = filter.get("order_by")
                direction = filter.get("direction")

                if order_by and order_by.startswith("group_id:"):
                    group_id = order_by.split(":", 1)[1]

                    # Subquery that checks if the user belongs to the group
                    membership_exists = exists(
                        select(GroupMember.id).where(
                            GroupMember.user_id == User.id,
                            GroupMember.group_id == group_id,
                        )
                    )

                    # CASE: user in group → 1, user not in group → 0
                    group_sort = case((membership_exists, 1), else_=0)

                    if direction == "asc":
                        query = query.order_by(group_sort.asc(), User.name.asc())
                    else:
                        query = query.order_by(group_sort.desc(), User.name.asc())

                elif order_by == "name":
                    if direction == "asc":
                        query = query.order_by(User.name.asc())
                    else:
                        query = query.order_by(User.name.desc())

                elif order_by == "email":
                    if direction == "asc":
                        query = query.order_by(User.email.asc())
                    else:
                        query = query.order_by(User.email.desc())

                elif order_by == "created_at":
                    if direction == "asc":
                        query = query.order_by(User.created_at.asc())
                    else:
                        query = query.order_by(User.created_at.desc())

                elif order_by == "last_active_at":
                    if direction == "asc":
                        query = query.order_by(User.last_active_at.asc())
                    else:
                        query = query.order_by(User.last_active_at.desc())

                elif order_by == "updated_at":
                    if direction == "asc":
                        query = query.order_by(User.updated_at.asc())
                    else:
                        query = query.order_by(User.updated_at.desc())
                elif order_by == "role":
                    if direction == "asc":
                        query = query.order_by(User.role.asc())
                    else:
                        query = query.order_by(User.role.desc())

            else:
                query = query.order_by(User.created_at.desc())

            # Count BEFORE pagination
            total = query.count()

            # correct pagination logic
            if skip is not None:
                query = query.offset(skip)
            if limit is not None:
                query = query.limit(limit)

            users = query.all()
            return {
                "users": [UserModel.model_validate(user) for user in users],
                "total": total,
            }


    def get_users_by_user_ids(
        self, user_ids: list[str], db: Optional[Session] = None
    ) -> list[UserStatusModel]:
        with get_db_context(db) as db:
            users = (
                db.query(User)
                .options(defer(User.profile_image_url))
                .filter(User.id.in_(user_ids))
                .all()
            )
            return [UserModel.model_validate(user) for user in users]

    def get_num_users(self, db: Optional[Session] = None) -> Optional[int]:
        with get_db_context(db) as db:
            return db.query(User).count()


    def update_user_role_by_id(
        self, id: str, role: str, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        try:
            with get_db_context(db) as db:
                user = db.query(User).filter_by(id=id).first()
                if not user:
                    return None
                user.role = role
                db.commit()
                db.refresh(user)
                return UserModel.model_validate(user)
        except Exception:
            return None


    @throttle(DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL)
    def update_last_active_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        try:
            with get_db_context(db) as db:
                user = db.query(User).filter_by(id=id).first()
                if not user:
                    return None
                user.last_active_at = int(time.time())
                db.commit()
                db.refresh(user)
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_by_id(
        self, id: str, updated: dict, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        try:
            with get_db_context(db) as db:
                user = db.query(User).filter_by(id=id).first()
                if not user:
                    return None
                for key, value in updated.items():
                    setattr(user, key, value)
                db.commit()
                db.refresh(user)
                return UserModel.model_validate(user)
        except Exception as e:
            print(e)
            return None

    def update_user_settings_by_id(
        self, id: str, updated: dict, db: Optional[Session] = None
    ) -> Optional[UserModel]:
        try:
            with get_db_context(db) as db:
                user = db.query(User).filter_by(id=id).first()
                if not user:
                    return None

                user_settings = user.settings

                if user_settings is None:
                    user_settings = {}

                user_settings.update(updated)

                db.query(User).filter_by(id=id).update({"settings": user_settings})
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None



    @staticmethod
    def is_active(user: UserModel) -> bool:
        """Compute active status from an already-loaded UserModel (no DB hit)."""
        if user.last_active_at:
            three_minutes_ago = int(time.time()) - 180
            return user.last_active_at >= three_minutes_ago
        return False

    def is_user_active(self, user_id: str, db: Optional[Session] = None) -> bool:
        with get_db_context(db) as db:
            user = db.query(User).filter_by(id=user_id).first()
            if user and user.last_active_at:
                # Consider user active if last_active_at within the last 3 minutes
                three_minutes_ago = int(time.time()) - 180
                return user.last_active_at >= three_minutes_ago
            return False


Users = UsersTable()
