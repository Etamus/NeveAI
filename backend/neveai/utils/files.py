from fastapi import (Request, UploadFile)
from typing import Optional
from pathlib import Path

from neveai.storage.provider import Storage

from neveai.models.chats import Chats
from neveai.models.files import Files
from neveai.routers.files import upload_file_handler
from neveai.utils.url import validate_url

import mimetypes
import base64
import io
import re

import requests


def get_image_data(data: str, headers=None):
    try:
        if data.startswith(("http://", "https://")):
            response = requests.get(data, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None, None
            return response.content, content_type
        if "," in data:
            header, encoded = data.split(",", 1)
            content_type = header.split(";", 1)[0].removeprefix("data:")
        else:
            encoded = data
            content_type = "image/png"
        return base64.b64decode(encoded), content_type
    except Exception:
        return None, None


def upload_image(request, image_data, content_type, metadata, user, db=None):
    extension = mimetypes.guess_extension(content_type) or ".png"
    file = UploadFile(
        file=io.BytesIO(image_data),
        filename=f"generated-image{extension}",
        headers={"content-type": content_type},
    )
    file_item = upload_file_handler(
        request, file=file, metadata=metadata, process=False, user=user
    )
    if file_item and file_item.id:
        chat_id = metadata.get("chat_id")
        message_id = metadata.get("message_id")
        if chat_id and message_id:
            Chats.insert_chat_files(
                chat_id=chat_id,
                message_id=message_id,
                file_ids=[file_item.id],
                user_id=user.id,
                db=db,
            )
    url = request.app.url_path_for("get_file_content_by_id", id=file_item.id)
    return file_item, url

BASE64_IMAGE_URL_PREFIX = re.compile(r"data:image/\w+;base64,", re.IGNORECASE)
MARKDOWN_IMAGE_URL_PATTERN = re.compile(r"!\[(.*?)\]\((.+?)\)", re.IGNORECASE)


def get_image_base64_from_url(url: str) -> Optional[str]:
    try:
        if url.startswith("http"):
            # Validate URL to prevent SSRF attacks against local/private networks
            validate_url(url)
            # Download the image from the URL
            response = requests.get(url)
            response.raise_for_status()
            image_data = response.content
            encoded_string = base64.b64encode(image_data).decode("utf-8")
            content_type = response.headers.get("Content-Type", "image/png")
            return f"data:{content_type};base64,{encoded_string}"
        else:
            file = Files.get_file_by_id(url)

            if not file:
                return None

            file_path = Storage.get_file(file.path)
            file_path = Path(file_path)

            if file_path.is_file():
                with open(file_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                    content_type, _ = mimetypes.guess_type(file_path.name)
                    return f"data:{content_type};base64,{encoded_string}"
            else:
                return None

    except Exception as e:
        return None


def get_image_url_from_base64(request, base64_image_string, metadata, user):
    if BASE64_IMAGE_URL_PREFIX.match(base64_image_string):
        image_url = ""
        # Extract base64 image data from the line
        image_data, content_type = get_image_data(base64_image_string)
        if image_data is not None:
            _, image_url = upload_image(
                request,
                image_data,
                content_type,
                metadata,
                user,
            )

        return image_url
    return None


def convert_markdown_base64_images(request, content: str, metadata, user):
    def replace(match):
        base64_string = match.group(2)
        MIN_REPLACEMENT_URL_LENGTH = 1024
        if len(base64_string) > MIN_REPLACEMENT_URL_LENGTH:
            url = get_image_url_from_base64(request, base64_string, metadata, user)
            if url:
                return f"![{match.group(1)}]({url})"
        return match.group(0)

    return MARKDOWN_IMAGE_URL_PATTERN.sub(replace, content)


def load_b64_audio_data(b64_str):
    try:
        if "," in b64_str:
            header, b64_data = b64_str.split(",", 1)
        else:
            b64_data = b64_str
            header = "data:audio/wav;base64"
        audio_data = base64.b64decode(b64_data)
        content_type = (
            header.split(";")[0].split(":")[1] if ";" in header else "audio/wav"
        )
        return audio_data, content_type
    except Exception as e:
        print(f"Error decoding base64 audio data: {e}")
        return None, None


def upload_audio(request, audio_data, content_type, metadata, user):
    audio_format = mimetypes.guess_extension(content_type)
    file = UploadFile(
        file=io.BytesIO(audio_data),
        filename=f"generated-{audio_format}",  # will be converted to a unique ID on upload_file
        headers={
            "content-type": content_type,
        },
    )
    file_item = upload_file_handler(
        request,
        file=file,
        metadata=metadata,
        process=False,
        user=user,
    )
    url = request.app.url_path_for("get_file_content_by_id", id=file_item.id)
    return url


def get_audio_url_from_base64(request, base64_audio_string, metadata, user):
    if "data:audio/wav;base64" in base64_audio_string:
        audio_url = ""
        # Extract base64 audio data from the line
        audio_data, content_type = load_b64_audio_data(base64_audio_string)
        if audio_data is not None:
            audio_url = upload_audio(
                request,
                audio_data,
                content_type,
                metadata,
                user,
            )
        return audio_url
    return None


def get_file_url_from_base64(request, base64_file_string, metadata, user):
    if "data:image/png;base64" in base64_file_string:
        return get_image_url_from_base64(request, base64_file_string, metadata, user)
    elif "data:audio/wav;base64" in base64_file_string:
        return get_audio_url_from_base64(request, base64_file_string, metadata, user)
    return None
