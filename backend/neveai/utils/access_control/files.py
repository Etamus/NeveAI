import logging
from typing import Optional, Any

from neveai.models.users import UserModel
from neveai.models.files import Files
from neveai.models.knowledge import Knowledges
from neveai.models.groups import Groups
from neveai.models.models import Models
from neveai.models.access_grants import AccessGrants

log = logging.getLogger(__name__)


def has_access_to_file(
    file_id: Optional[str],
    access_type: str,
    user: UserModel,
    db: Optional[Any] = None,
) -> bool:
    """
    Check if a user has the specified access to a file through any of:
    - Knowledge bases (ownership or access grants)
    - Shared workspace models that attach the file directly

    NOTE: This does NOT check direct file ownership — callers should check
    file.user_id == user.id separately before calling this.
    """
    file = Files.get_file_by_id(file_id, db=db)
    log.debug(f"Checking if user has {access_type} access to file")
    if not file:
        return False

    # Direct ownership
    if file.user_id == user.id:
        return True

    # Check if the file is associated with any knowledge bases the user has access to
    knowledge_bases = Knowledges.get_knowledges_by_file_id(file_id, db=db)
    user_group_ids = {
        group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
    }
    for knowledge_base in knowledge_bases:
        if knowledge_base.user_id == user.id or AccessGrants.has_access(
            user_id=user.id,
            resource_type="knowledge",
            resource_id=knowledge_base.id,
            permission=access_type,
            user_group_ids=user_group_ids,
            db=db,
        ):
            return True

    knowledge_base_id = file.meta.get("collection_name") if file.meta else None
    if knowledge_base_id:
        knowledge_bases = Knowledges.get_knowledge_bases_by_user_id(
            user.id, access_type, db=db
        )
        for knowledge_base in knowledge_bases:
            if knowledge_base.id == knowledge_base_id:
                return True

    # Check if the file is directly attached to a shared workspace model
    for model in Models.get_models_by_user_id(user.id, permission=access_type, db=db):
        knowledge_items = getattr(model.meta, "knowledge", None) or []
        for item in knowledge_items:
            if (
                isinstance(item, dict)
                and item.get("type") == "file"
                and item.get("id") == file.id
            ):
                return True

    return False
