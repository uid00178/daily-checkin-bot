from __future__ import annotations

import io

import boto3

from .config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )


def upload_bytes(data: bytes, key: str, content_type: str) -> None:
    if not settings.store_media_in_s3:
        return
    if not settings.s3_bucket:
        raise RuntimeError("S3_BUCKET is required when STORE_MEDIA_IN_S3=true")

    client = _client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )