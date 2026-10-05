import json
import time
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session
from neveai.internal.db import Base, get_db_context

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Text,
    JSON,
    Index,
    func,
)

####################
# Helpers
####################


def _normalize_timestamp(timestamp: int) -> float:
    """Normalize and validate timestamp. Returns current time if invalid."""
    now = time.time()

    # Convert milliseconds to seconds if needed
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000

    # Validate: must be after 2020 and not in the future (with 1 day tolerance)
    min_valid = 1577836800  # 2020-01-01 00:00:00 UTC
    max_valid = now + 86400  # 1 day in the future (clock skew tolerance)

    if timestamp < min_valid or timestamp > max_valid:
        return now

    return timestamp


####################
# ChatMessage DB Schema
####################


class ChatMessage(Base):
    __tablename__ = "chat_message"

    # Identity
    id = Column(Text, primary_key=True)
    chat_id = Column(
        Text, ForeignKey("chat.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Text, index=True)

    # Structure
    role = Column(Text, nullable=False)  # user, assistant, system
    parent_id = Column(Text, nullable=True)

    # Content
    content = Column(JSON, nullable=True)  # Can be str or list of blocks
    output = Column(JSON, nullable=True)

    # Model (for assistant messages)
    model_id = Column(Text, nullable=True, index=True)

    # Attachments
    files = Column(JSON, nullable=True)
    sources = Column(JSON, nullable=True)
    embeds = Column(JSON, nullable=True)

    # Status
    done = Column(Boolean, default=True)
    status_history = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)

    # Usage (tokens, timing, etc.)
    usage = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(BigInteger, index=True)
    updated_at = Column(BigInteger)

    __table_args__ = (
        Index("chat_message_chat_parent_idx", "chat_id", "parent_id"),
        Index("chat_message_model_created_idx", "model_id", "created_at"),
        Index("chat_message_user_created_idx", "user_id", "created_at"),
    )


####################
# Pydantic Models
####################


class ChatMessageModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    user_id: str
    role: str
    parent_id: Optional[str] = None
    content: Optional[Any] = None  # str or list of blocks
    output: Optional[list] = None
    model_id: Optional[str] = None
    files: Optional[list] = None
    sources: Optional[list] = None
    embeds: Optional[list] = None
    done: bool = True
    status_history: Optional[list] = None
    error: Optional[dict | str] = None
    usage: Optional[dict] = None
    created_at: int
    updated_at: int


####################
# Table Operations
####################


class ChatMessageTable:
    def upsert_message(
        self,
        message_id: str,
        chat_id: str,
        user_id: str,
        data: dict,
        db: Optional[Session] = None,
    ) -> Optional[ChatMessageModel]:
        """Insert or update a chat message."""
        with get_db_context(db) as db:
            now = int(time.time())
            timestamp = data.get("timestamp", now)

            # Use composite ID: {chat_id}-{message_id}
            composite_id = f"{chat_id}-{message_id}"

            existing = db.get(ChatMessage, composite_id)
            if existing:
                # Update existing
                if "role" in data:
                    existing.role = data["role"]
                if "parent_id" in data:
                    existing.parent_id = data.get("parent_id") or data.get("parentId")
                if "content" in data:
                    existing.content = data.get("content")
                if "output" in data:
                    existing.output = data.get("output")
                if "model_id" in data or "model" in data:
                    existing.model_id = data.get("model_id") or data.get("model")
                if "files" in data:
                    existing.files = data.get("files")
                if "sources" in data:
                    existing.sources = data.get("sources")
                if "embeds" in data:
                    existing.embeds = data.get("embeds")
                if "done" in data:
                    existing.done = data.get("done", True)
                if "status_history" in data or "statusHistory" in data:
                    existing.status_history = data.get("status_history") or data.get(
                        "statusHistory"
                    )
                if "error" in data:
                    existing.error = data.get("error")
                # Extract usage - check direct field first, then info.usage
                usage = data.get("usage")
                if not usage:
                    info = data.get("info", {})
                    usage = info.get("usage") if info else None
                if usage:
                    existing.usage = usage
                existing.updated_at = now
                db.commit()
                db.refresh(existing)
                return ChatMessageModel.model_validate(existing)
            else:
                # Insert new
                # Extract usage - check direct field first, then info.usage
                usage = data.get("usage")
                if not usage:
                    info = data.get("info", {})
                    usage = info.get("usage") if info else None
                message = ChatMessage(
                    id=composite_id,
                    chat_id=chat_id,
                    user_id=user_id,
                    role=data.get("role", "user"),
                    parent_id=data.get("parent_id") or data.get("parentId"),
                    content=data.get("content"),
                    output=data.get("output"),
                    model_id=data.get("model_id") or data.get("model"),
                    files=data.get("files"),
                    sources=data.get("sources"),
                    embeds=data.get("embeds"),
                    done=data.get("done", True),
                    status_history=data.get("status_history")
                    or data.get("statusHistory"),
                    error=data.get("error"),
                    usage=usage,
                    created_at=timestamp,
                    updated_at=now,
                )
                db.add(message)
                db.commit()
                db.refresh(message)
                return ChatMessageModel.model_validate(message)


    # Analytics methods


ChatMessages = ChatMessageTable()
