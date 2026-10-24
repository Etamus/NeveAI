"""Small projections for file polling and content-free listings."""

import json

from sqlalchemy import JSON, cast, func
from sqlalchemy.dialects.postgresql import JSONB

from neveai.models.files import File, FileModel, Files


def file_process_state(id, db):
    if db.bind.dialect.name == "sqlite":
        has_status = func.json_type(File.data, "$.status").is_not(None)
    elif db.bind.dialect.name == "postgresql":
        has_status = cast(File.data, JSONB).has_key("status")
    else:
        has_status = File.data["status"].as_string().is_not(None)
    row = db.query(
        File.id, File.user_id,
        has_status.label("has_status"),
        File.data["status"].label("status"),
        File.data["error"].label("error"),
    ).filter(File.id == id).first()
    return dict(row._mapping) if row else None


def files_without_content(user_id=None, filename=None, skip=0, limit=None, db=None):
    dialect = db.bind.dialect.name
    if dialect == "sqlite":
        data = func.json_remove(File.data, "$.content")
    elif dialect == "postgresql":
        data = cast(cast(File.data, JSONB).op("-")("content"), JSON)
    else:
        data = File.data
    columns = [column for column in File.__table__.columns if column.name != "data"]
    query = db.query(*columns, data.label("data"))
    if user_id is not None:
        query = query.filter(File.user_id == user_id)
    if filename is not None:
        pattern = Files._glob_to_like_pattern(filename)
        if pattern != "%":
            query = query.filter(File.filename.ilike(pattern, escape="\\"))
        query = query.order_by(File.created_at.desc(), File.id.desc())
    query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    result = []
    for row in query.all():
        item = dict(row._mapping)
        if isinstance(item["data"], str):
            item["data"] = json.loads(item["data"])
        if isinstance(item["data"], dict):
            item["data"] = {k: v for k, v in item["data"].items() if k != "content"}
        result.append(FileModel.model_validate(item))
    return result
