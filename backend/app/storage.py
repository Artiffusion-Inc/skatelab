"""S3-compatible object storage (Cloudflare R2) for video transfer.

Sync client: per-thread via threading.local() (boto3 client is NOT thread-safe).
Async client: singleton with asyncio.Lock double-check + credential hash rotation.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

import aiobotocore.session
import boto3
from botocore.config import Config as BotoConfig

from app.config import get_settings

logger = logging.getLogger(__name__)

_async_session = aiobotocore.session.get_session()
_thread_local = threading.local()
_async_client_instance: Any = None
_async_client_lock = asyncio.Lock()
_credential_hash: str | None = None

_R2_CONFIG = BotoConfig(
    signature_version="s3v4",
    connect_timeout=10,
    read_timeout=300,  # 5 min for large video files
    retries={"max_attempts": 3, "mode": "adaptive"},
)


def _get_credential_hash() -> str:
    s = get_settings()
    return hashlib.sha256(
        (s.r2.access_key_id.get_secret_value() + s.r2.secret_access_key.get_secret_value()).encode()
    ).hexdigest()


def get_r2_client():
    """Per-thread boto3 client (thread-safe for asyncio.to_thread)."""
    client = getattr(_thread_local, "r2_client", None)
    if client is None:
        s = get_settings()
        client = boto3.client(
            "s3",
            endpoint_url=s.r2.endpoint_url or None,
            aws_access_key_id=s.r2.access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2.secret_access_key.get_secret_value(),
            config=_R2_CONFIG,
            region_name="auto",
        )
        _thread_local.r2_client = client
    return client


async def get_r2_async_client():
    """Async R2 singleton with init lock and credential rotation."""
    global _async_client_instance, _credential_hash  # noqa: PLW0603
    current_hash = _get_credential_hash()
    if _async_client_instance is not None and _credential_hash == current_hash:
        return _async_client_instance
    async with _async_client_lock:
        # Double-check after lock
        current_hash = _get_credential_hash()
        if _async_client_instance is not None and _credential_hash == current_hash:
            return _async_client_instance
        # Close old client if credential changed
        if _async_client_instance is not None:
            with suppress(Exception):
                await _async_client_instance.__aexit__(None, None, None)
        s = get_settings()
        _async_client_instance = _async_session.create_client(
            "s3",
            endpoint_url=s.r2.endpoint_url or None,
            aws_access_key_id=s.r2.access_key_id.get_secret_value(),
            aws_secret_access_key=s.r2.secret_access_key.get_secret_value(),
            config=_R2_CONFIG,
            region_name="auto",
        )
        await _async_client_instance.__aenter__()
        _credential_hash = current_hash
    return _async_client_instance


async def reset_r2_async_client() -> None:
    """Force-recreate the async client (after unrecoverable errors)."""
    global _async_client_instance  # noqa: PLW0603
    async with _async_client_lock:
        if _async_client_instance is not None:
            with suppress(Exception):
                await _async_client_instance.__aexit__(None, None, None)
            _async_client_instance = None


async def close_r2_clients() -> None:
    """Close all R2 clients (call at shutdown)."""
    global _async_client_instance  # noqa: PLW0603
    if _async_client_instance is not None:
        with suppress(Exception):
            await _async_client_instance.__aexit__(None, None, None)
        _async_client_instance = None
    # Sync per-thread clients: close current thread's client
    client = getattr(_thread_local, "r2_client", None)
    if client is not None:
        client.close()
        _thread_local.r2_client = None


# ============ Sync operations (use get_r2_client()) ============


def upload_file(local_path: str | Path, key: str) -> str:
    """Upload file to R2. Returns the key."""
    bucket = get_settings().r2.bucket
    logger.info("Uploading %s -> s3://%s/%s", local_path, bucket, key)
    get_r2_client().upload_file(str(local_path), bucket, key)
    return key


def download_file(key: str, local_path: str | Path) -> str:
    """Download file from R2. Returns the local path."""
    bucket = get_settings().r2.bucket
    logger.info("Downloading s3://%s/%s -> %s", bucket, key, local_path)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    get_r2_client().download_file(bucket, key, str(local_path))
    return str(local_path)


def delete_object(key: str) -> None:
    """Delete object from R2."""
    get_r2_client().delete_object(Bucket=get_settings().r2.bucket, Key=key)


def upload_bytes(data: bytes, key: str) -> str:
    """Upload bytes to R2. Returns the key."""
    bucket = get_settings().r2.bucket
    logger.info("Uploading %d bytes -> s3://%s/%s", len(data), bucket, key)
    get_r2_client().put_object(Bucket=bucket, Key=key, Body=data)
    return key


def stream_object(key: str) -> tuple:
    """Stream object from R2. Returns (body, content_length, content_type)."""
    bucket = get_settings().r2.bucket
    logger.info("Streaming s3://%s/%s", bucket, key)
    resp = get_r2_client().get_object(Bucket=bucket, Key=key)
    body = resp["Body"]
    length = resp.get("ContentLength", 0)
    ctype = resp.get("ContentType", "application/octet-stream")
    return body, length, ctype


def object_exists(key: str) -> bool:
    """Check if object exists in R2."""
    from botocore.exceptions import ClientError

    try:
        get_r2_client().head_object(Bucket=get_settings().r2.bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def get_object_url(key: str, expires: int = 3600) -> str:
    """Generate a presigned URL for an object."""
    bucket = get_settings().r2.bucket
    return get_r2_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


def list_objects(prefix: str) -> list[str]:
    """List object keys with given prefix."""
    bucket = get_settings().r2.bucket
    resp = get_r2_client().list_objects_v2(Bucket=bucket, Prefix=prefix)
    return [obj["Key"] for obj in resp.get("Contents", [])]


# ============ Async operations (use get_r2_async_client()) ============


async def upload_file_async(local_path: str | Path, key: str) -> str:
    """Upload file to R2 asynchronously. Returns the key."""
    bucket = get_settings().r2.bucket
    logger.info("Uploading %s -> s3://%s/%s (async)", local_path, bucket, key)
    s3 = await get_r2_async_client()
    await s3.upload_file(str(local_path), bucket, key)
    return key


async def download_file_async(key: str, local_path: str | Path) -> str:
    """Download file from R2 asynchronously. Returns the local path."""
    bucket = get_settings().r2.bucket
    logger.info("Downloading s3://%s/%s -> %s (async)", bucket, key, local_path)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    s3 = await get_r2_async_client()
    await s3.download_file(bucket, key, str(local_path))
    return str(local_path)


async def upload_bytes_async(data: bytes, key: str) -> str:
    """Upload bytes to R2 asynchronously. Returns the key."""
    bucket = get_settings().r2.bucket
    logger.info("Uploading %d bytes -> s3://%s/%s (async)", len(data), bucket, key)
    s3 = await get_r2_async_client()
    await s3.put_object(Bucket=bucket, Key=key, Body=data)
    return key


async def object_exists_async(key: str) -> bool:
    """Check if object exists in R2 asynchronously."""
    from botocore.exceptions import ClientError

    s3 = await get_r2_async_client()
    try:
        await s3.head_object(Bucket=get_settings().r2.bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


async def stream_object_async(key: str) -> tuple:
    """Stream object from R2 asynchronously. Returns (body, content_length, content_type)."""
    bucket = get_settings().r2.bucket
    logger.info("Streaming s3://%s/%s (async)", bucket, key)
    s3 = await get_r2_async_client()
    resp = await s3.get_object(Bucket=bucket, Key=key)
    body = resp["Body"]
    length = resp.get("ContentLength", 0)
    ctype = resp.get("ContentType", "application/octet-stream")
    return body, length, ctype


async def get_object_url_async(key: str, expires: int = 3600) -> str:
    """Generate a presigned URL for an object asynchronously."""
    bucket = get_settings().r2.bucket
    s3 = await get_r2_async_client()
    return await s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


async def delete_object_async(key: str) -> None:
    """Delete object from R2 asynchronously."""
    s3 = await get_r2_async_client()
    await s3.delete_object(Bucket=get_settings().r2.bucket, Key=key)


async def list_objects_async(prefix: str) -> list[str]:
    """List object keys with given prefix asynchronously."""
    bucket = get_settings().r2.bucket
    s3 = await get_r2_async_client()
    resp = await s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return [obj["Key"] for obj in resp.get("Contents", [])]
