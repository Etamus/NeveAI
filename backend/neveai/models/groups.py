import json
import logging
import time
from typing import Optional
import uuid

from sqlalchemy.orm import Session
from neveai.internal.db import (Base, get_db_context)
from neveai.env import DEFAULT_GROUP_SHARE_PERMISSION

import neveai.models.files


from pydantic import BaseModel, ConfigDict
from sqlalchemy import (BigInteger, Column, String, Text, JSON, func, ForeignKey, select)

log = logging.getLogger(__name__)

####################
# UserGroup DB Schema
####################


class Group(Base):
    __tablename__ = "group"

    id = Column(Text, unique=True, primary_key=True)
    user_id = Column(Text)

    name = Column(Text)
    description = Column(Text)

    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    permissions = Column(JSON, nullable=True)

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class GroupModel(BaseModel):
    id: str
    user_id: str

    name: str
    description: str

    data: Optional[dict] = None
    meta: Optional[dict] = None

    permissions: Optional[dict] = None

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


class GroupMember(Base):
    __tablename__ = "group_member"

    id = Column(Text, unique=True, primary_key=True)
    group_id = Column(
        Text,
        ForeignKey("group.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=True)
    updated_at = Column(BigInteger, nullable=True)


####################
# Forms
####################


class GroupResponse(GroupModel):
    member_count: Optional[int] = None


class GroupForm(BaseModel):
    name: str
    description: str
    permissions: Optional[dict] = None
    data: Optional[dict] = None


class GroupUpdateForm(GroupForm):
    pass


class GroupTable:
    def _ensure_default_share_config(self, group_data: dict) -> dict:
        """Ensure the group data dict has a default share config if not already set."""
        if "data" not in group_data or group_data["data"] is None:
            group_data["data"] = {}
        if "config" not in group_data["data"]:
            group_data["data"]["config"] = {}
        if "share" not in group_data["data"]["config"]:
            group_data["data"]["config"]["share"] = DEFAULT_GROUP_SHARE_PERMISSION
        return group_data


    def get_groups_by_member_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> list[GroupModel]:
        with get_db_context(db) as db:
            return [
                GroupModel.model_validate(group)
                for group in db.query(Group)
                .join(GroupMember, GroupMember.group_id == Group.id)
                .filter(GroupMember.user_id == user_id)
                .order_by(Group.updated_at.desc())
                .all()
            ]


    def get_group_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[GroupModel]:
        try:
            with get_db_context(db) as db:
                group = db.query(Group).filter_by(id=id).first()
                return GroupModel.model_validate(group) if group else None
        except Exception:
            return None


Groups = GroupTable()
