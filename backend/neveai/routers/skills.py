import logging
from typing import Optional

from neveai.models.groups import Groups
from pydantic import BaseModel

from fastapi import (APIRouter, Depends, Request, status)
from sqlalchemy.orm import Session

from neveai.internal.db import get_session
from neveai.models.skills import (SkillAccessResponse, SkillAccessListResponse, Skills)
from neveai.models.access_grants import AccessGrants
from neveai.utils.auth import get_verified_user

from neveai.config import BYPASS_ADMIN_ACCESS_CONTROL

log = logging.getLogger(__name__)

PAGE_ITEM_COUNT = 30

router = APIRouter()




############################
# GetSkillList
############################


@router.get("/list", response_model=SkillAccessListResponse)
async def get_skill_list(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    limit = PAGE_ITEM_COUNT

    page = max(1, page)
    skip = (page - 1) * limit

    filter = {}
    if query:
        filter["query"] = query
    if view_option:
        filter["view_option"] = view_option

    if not (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL):
        groups = Groups.get_groups_by_member_id(user.id, db=db)
        if groups:
            filter["group_ids"] = [group.id for group in groups]

        filter["user_id"] = user.id

    result = Skills.search_skills(user.id, filter=filter, skip=skip, limit=limit, db=db)

    return SkillAccessListResponse(
        items=[
            SkillAccessResponse(
                **skill.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or user.id == skill.user_id
                    or AccessGrants.has_access(
                        user_id=user.id,
                        resource_type="skill",
                        resource_id=skill.id,
                        permission="write",
                        db=db,
                    )
                ),
            )
            for skill in result.items
        ],
        total=result.total,
    )










############################
# UpdateSkillAccessById
############################


class SkillAccessGrantsForm(BaseModel):
    access_grants: list[dict]
