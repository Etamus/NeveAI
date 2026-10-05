import logging
import time
from typing import Optional

from sqlalchemy.orm import Session
from neveai.internal.db import (Base, get_db_context)
from neveai.models.users import Users, UserResponse
from neveai.models.groups import Groups
from neveai.models.access_grants import AccessGrantModel, AccessGrants

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, BigInteger, Boolean, Column, String, Text, or_

log = logging.getLogger(__name__)

####################
# Skills DB Schema
####################


class Skill(Base):
    __tablename__ = "skill"

    id = Column(String, primary_key=True, unique=True)
    user_id = Column(String)
    name = Column(Text, unique=True)
    description = Column(Text, nullable=True)
    content = Column(Text)
    meta = Column(JSON)
    is_active = Column(Boolean, default=True)

    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)


class SkillMeta(BaseModel):
    tags: Optional[list[str]] = []


class SkillModel(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    content: str
    meta: SkillMeta
    is_active: bool = True
    access_grants: list[AccessGrantModel] = Field(default_factory=list)

    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class SkillUserModel(SkillModel):
    user: Optional[UserResponse] = None


class SkillResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    meta: SkillMeta
    is_active: bool = True
    access_grants: list[AccessGrantModel] = Field(default_factory=list)
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch


class SkillUserResponse(SkillResponse):
    user: Optional[UserResponse] = None

    model_config = ConfigDict(extra="allow")


class SkillAccessResponse(SkillUserResponse):
    write_access: Optional[bool] = False


class SkillForm(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    content: str
    meta: SkillMeta = SkillMeta()
    is_active: bool = True
    access_grants: Optional[list[dict]] = None


class SkillListResponse(BaseModel):
    items: list[SkillUserResponse] = []
    total: int = 0


class SkillAccessListResponse(BaseModel):
    items: list[SkillAccessResponse] = []
    total: int = 0


class SkillsTable:
    def _get_access_grants(
        self, skill_id: str, db: Optional[Session] = None
    ) -> list[AccessGrantModel]:
        return AccessGrants.get_grants_by_resource("skill", skill_id, db=db)

    def _to_skill_model(
        self,
        skill: Skill,
        access_grants: Optional[list[AccessGrantModel]] = None,
        db: Optional[Session] = None,
    ) -> SkillModel:
        skill_data = SkillModel.model_validate(skill).model_dump(
            exclude={"access_grants"}
        )
        skill_data["access_grants"] = (
            access_grants
            if access_grants is not None
            else self._get_access_grants(skill_data["id"], db=db)
        )
        return SkillModel.model_validate(skill_data)


    def get_skill_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[SkillModel]:
        try:
            with get_db_context(db) as db:
                skill = db.get(Skill, id)
                return self._to_skill_model(skill, db=db) if skill else None
        except Exception:
            return None

    def get_skill_by_name(
        self, name: str, db: Optional[Session] = None
    ) -> Optional[SkillModel]:
        try:
            with get_db_context(db) as db:
                skill = db.query(Skill).filter_by(name=name).first()
                return self._to_skill_model(skill, db=db) if skill else None
        except Exception:
            return None

    def get_skills(self, db: Optional[Session] = None) -> list[SkillUserModel]:
        with get_db_context(db) as db:
            all_skills = db.query(Skill).order_by(Skill.updated_at.desc()).all()

            user_ids = list(set(skill.user_id for skill in all_skills))
            skill_ids = [skill.id for skill in all_skills]

            users = Users.get_users_by_user_ids(user_ids, db=db) if user_ids else []
            users_dict = {user.id: user for user in users}
            grants_map = AccessGrants.get_grants_by_resources("skill", skill_ids, db=db)

            skills = []
            for skill in all_skills:
                user = users_dict.get(skill.user_id)
                skills.append(
                    SkillUserModel.model_validate(
                        {
                            **self._to_skill_model(
                                skill,
                                access_grants=grants_map.get(skill.id, []),
                                db=db,
                            ).model_dump(),
                            "user": user.model_dump() if user else None,
                        }
                    )
                )
            return skills

    def get_skills_by_user_id(
        self, user_id: str, permission: str = "write", db: Optional[Session] = None
    ) -> list[SkillUserModel]:
        skills = self.get_skills(db=db)
        user_group_ids = {
            group.id for group in Groups.get_groups_by_member_id(user_id, db=db)
        }

        return [
            skill
            for skill in skills
            if skill.user_id == user_id
            or AccessGrants.has_access(
                user_id=user_id,
                resource_type="skill",
                resource_id=skill.id,
                permission=permission,
                user_group_ids=user_group_ids,
                db=db,
            )
        ]

    def search_skills(
        self,
        user_id: str,
        filter: dict = {},
        skip: int = 0,
        limit: int = 30,
        db: Optional[Session] = None,
    ) -> SkillListResponse:
        try:
            with get_db_context(db) as db:
                from neveai.models.users import User, UserModel

                # Join with User table for user filtering
                query = db.query(Skill, User).outerjoin(User, User.id == Skill.user_id)

                if filter:
                    query_key = filter.get("query")
                    if query_key:
                        query = query.filter(
                            or_(
                                Skill.name.ilike(f"%{query_key}%"),
                                Skill.description.ilike(f"%{query_key}%"),
                                Skill.id.ilike(f"%{query_key}%"),
                                User.name.ilike(f"%{query_key}%"),
                                User.email.ilike(f"%{query_key}%"),
                            )
                        )

                    view_option = filter.get("view_option")
                    if view_option == "created":
                        query = query.filter(Skill.user_id == user_id)
                    elif view_option == "shared":
                        query = query.filter(Skill.user_id != user_id)

                    # Apply access grant filtering
                    query = AccessGrants.has_permission_filter(
                        db=db,
                        query=query,
                        DocumentModel=Skill,
                        filter=filter,
                        resource_type="skill",
                        permission="read",
                    )

                query = query.order_by(Skill.updated_at.desc())

                # Count BEFORE pagination
                total = query.count()

                if skip:
                    query = query.offset(skip)
                if limit:
                    query = query.limit(limit)

                items = query.all()

                skill_ids = [skill.id for skill, _ in items]
                grants_map = AccessGrants.get_grants_by_resources(
                    "skill", skill_ids, db=db
                )

                skills = []
                for skill, user in items:
                    skills.append(
                        SkillUserResponse(
                            **self._to_skill_model(
                                skill,
                                access_grants=grants_map.get(skill.id, []),
                                db=db,
                            ).model_dump(),
                            user=(
                                UserResponse(
                                    **UserModel.model_validate(user).model_dump()
                                )
                                if user
                                else None
                            ),
                        )
                    )

                return SkillListResponse(items=skills, total=total)
        except Exception as e:
            log.exception(f"Error searching skills: {e}")
            return SkillListResponse(items=[], total=0)


Skills = SkillsTable()
