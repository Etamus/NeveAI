from typing import Optional
from pydantic import BaseModel
from fastapi import (APIRouter, Depends, HTTPException, status, Request)
import logging
import io
import zipfile

from sqlalchemy.orm import Session
from neveai.internal.db import get_session
from neveai.models.groups import Groups
from neveai.models.knowledge import (KnowledgeFileListResponse, Knowledges, KnowledgeResponse, KnowledgeUserResponse)
from neveai.models.files import FileMetadataResponse

from neveai.constants import ERROR_MESSAGES
from neveai.utils.auth import get_verified_user
from neveai.models.access_grants import AccessGrants


from neveai.config import BYPASS_ADMIN_ACCESS_CONTROL
import neveai.models.models

log = logging.getLogger(__name__)

router = APIRouter()

############################
# getKnowledgeBases
############################

PAGE_ITEM_COUNT = 30

############################
# Knowledge Base Embedding
############################

KNOWLEDGE_BASES_COLLECTION = "knowledge-bases"


class KnowledgeAccessResponse(KnowledgeUserResponse):
    write_access: Optional[bool] = False


class KnowledgeAccessListResponse(BaseModel):
    items: list[KnowledgeAccessResponse]
    total: int


@router.get("/search", response_model=KnowledgeAccessListResponse)
async def search_knowledge_bases(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    page = max(page, 1)
    limit = PAGE_ITEM_COUNT
    skip = (page - 1) * limit

    filter = {}
    if query:
        filter["query"] = query
    if view_option:
        filter["view_option"] = view_option

    groups = Groups.get_groups_by_member_id(user.id, db=db)
    user_group_ids = {group.id for group in groups}

    if not user.role == "admin" or not BYPASS_ADMIN_ACCESS_CONTROL:
        if groups:
            filter["group_ids"] = [group.id for group in groups]

        filter["user_id"] = user.id

    result = Knowledges.search_knowledge_bases(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    # Batch-fetch writable knowledge IDs in a single query instead of N has_access calls
    knowledge_base_ids = [knowledge_base.id for knowledge_base in result.items]
    writable_knowledge_base_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="knowledge",
        resource_ids=knowledge_base_ids,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    return KnowledgeAccessListResponse(
        items=[
            KnowledgeAccessResponse(
                **knowledge_base.model_dump(),
                write_access=(
                    user.id == knowledge_base.user_id
                    or (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or knowledge_base.id in writable_knowledge_base_ids
                ),
            )
            for knowledge_base in result.items
        ],
        total=result.total,
    )


@router.get("/search/files", response_model=KnowledgeFileListResponse)
async def search_knowledge_files(
    query: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    page = max(page, 1)
    limit = PAGE_ITEM_COUNT
    skip = (page - 1) * limit

    filter = {}
    if query:
        filter["query"] = query

    groups = Groups.get_groups_by_member_id(user.id, db=db)
    if groups:
        filter["group_ids"] = [group.id for group in groups]

    filter["user_id"] = user.id

    return Knowledges.search_knowledge_files(
        filter=filter, skip=skip, limit=limit, db=db
    )








############################
# GetKnowledgeById
############################


class KnowledgeFilesResponse(KnowledgeResponse):
    files: Optional[list[FileMetadataResponse]] = None
    write_access: Optional[bool] = False


@router.get("/{id}", response_model=Optional[KnowledgeFilesResponse])
async def get_knowledge_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    knowledge = Knowledges.get_knowledge_by_id(id=id, db=db)

    if knowledge:
        if (
            user.role == "admin"
            or knowledge.user_id == user.id
            or AccessGrants.has_access(
                user_id=user.id,
                resource_type="knowledge",
                resource_id=knowledge.id,
                permission="read",
                db=db,
            )
        ):

            return KnowledgeFilesResponse(
                **knowledge.model_dump(),
                write_access=(
                    user.id == knowledge.user_id
                    or (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or AccessGrants.has_access(
                        user_id=user.id,
                        resource_type="knowledge",
                        resource_id=knowledge.id,
                        permission="write",
                        db=db,
                    )
                ),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )




############################
# UpdateKnowledgeAccessById
############################


class KnowledgeAccessGrantsForm(BaseModel):
    access_grants: list[dict]




############################
# AddFileToKnowledge
############################


class KnowledgeFileIdForm(BaseModel):
    file_id: str
