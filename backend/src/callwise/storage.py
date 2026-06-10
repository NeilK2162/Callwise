"""Object storage (S3 / MinIO) for recordings, transcripts, and ingest artifacts.

PRD §5.5 (optional `.txt`/`.mp3` upload), §14.5 (presigned URLs with short expiry), §15
(S3 + Glacier lifecycle). Uses aioboto3 so the hot paths stay async. Uploads on the
verification hot path are best-effort — an S3 outage must never fail a verification
(edge #27); the transcript already lives in Postgres.
"""

from __future__ import annotations

from functools import lru_cache

import aioboto3
from botocore.config import Config

from callwise.config import Settings, get_settings
from callwise.logging import get_logger

log = get_logger(__name__)


class ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._session = aioboto3.Session()

    def _kwargs(self) -> dict:
        return {
            "service_name": "s3",
            "endpoint_url": self._s.s3_endpoint_url,
            "region_name": self._s.s3_region,
            "aws_access_key_id": self._s.s3_access_key_id,
            "aws_secret_access_key": self._s.s3_secret_access_key,
        }

    async def ensure_bucket(self) -> None:
        async with self._session.client(**self._kwargs()) as s3:
            try:
                await s3.head_bucket(Bucket=self._s.s3_bucket)
            except Exception:  # noqa: BLE001 — missing bucket → create it
                try:
                    await s3.create_bucket(Bucket=self._s.s3_bucket)
                    log.info("s3_bucket_created", bucket=self._s.s3_bucket)
                except Exception as exc:  # noqa: BLE001
                    log.warning("s3_bucket_create_failed", error=repr(exc))

    async def upload_bytes(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> str:
        async with self._session.client(**self._kwargs()) as s3:
            await s3.put_object(
                Bucket=self._s.s3_bucket, Key=key, Body=data, ContentType=content_type
            )
        return key

    async def download_bytes(self, key: str) -> bytes:
        async with self._session.client(**self._kwargs()) as s3:
            resp = await s3.get_object(Bucket=self._s.s3_bucket, Key=key)
            async with resp["Body"] as stream:
                return await stream.read()

    async def presigned_get(self, key: str, *, expires: int = 300) -> str:
        # Sign against the BROWSER-reachable host, not the in-cluster one — the URL is handed to
        # the dashboard. Signing is offline (no connection), so a different endpoint is safe;
        # path-style keeps the host stable so the SigV4 host header matches on playback.
        kwargs = self._kwargs()
        kwargs["endpoint_url"] = self._s.s3_public_endpoint_url or self._s.s3_endpoint_url
        kwargs["config"] = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        async with self._session.client(**kwargs) as s3:
            return await s3.generate_presigned_url(
                "get_object", Params={"Bucket": self._s.s3_bucket, "Key": key}, ExpiresIn=expires
            )

    async def try_upload(self, key: str, data: bytes, *, content_type: str) -> str | None:
        """Best-effort upload — returns the key on success, None on failure (never raises)."""
        try:
            return await self.upload_bytes(key, data, content_type=content_type)
        except Exception as exc:  # noqa: BLE001
            log.warning("s3_upload_failed", key=key, error=repr(exc))
            return None


@lru_cache
def get_object_store() -> ObjectStore:
    return ObjectStore(get_settings())
