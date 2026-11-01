"""Paired devices: pairing codes, pairing, listing and revoking (Phase 10)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.errors import ErrorCode, HypatiaError, ResourceNotFoundError
from app.models.db_models import Device
from app.models.schemas import (
    DeviceRead,
    PairingCodeRead,
    PairRequest,
    PairResponse,
    RemoteAccessRead,
)
from app.security import require_local_client
from app.services import device_auth, remote_access
from app.utils.logging import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post(
    "/pairing-code",
    response_model=PairingCodeRead,
    dependencies=[Depends(require_local_client)],
)
async def create_pairing_code() -> PairingCodeRead:
    """Only the desktop app may offer a code, so a lost phone can't pair others."""
    code, expires_at = device_auth.pairing_codes.issue()
    logger.info("pairing_code_issued")
    status = await _remote_status()
    return PairingCodeRead(
        code=code, expires_at=expires_at, urls=status.urls, cert_sha256=status.cert_sha256
    )


@router.get(
    "/remote-access",
    response_model=RemoteAccessRead,
    dependencies=[Depends(require_local_client)],
)
async def get_remote_access() -> RemoteAccessRead:
    """Whether phones can connect, and the addresses and fingerprint they'd use."""
    return await _remote_status()


async def _remote_status() -> RemoteAccessRead:
    port = settings.remote_port
    if not settings.remote_access_enabled or port is None:
        return RemoteAccessRead(enabled=False, port=None, urls=[], cert_sha256=None)
    cert_path, _ = remote_access.cert_paths(settings.data_dir)
    # Address detection may run the Tailscale CLI.
    urls = await asyncio.to_thread(remote_access.pairing_urls, port)
    return RemoteAccessRead(
        enabled=True,
        port=port,
        urls=urls,
        cert_sha256=remote_access.fingerprint(cert_path) if cert_path.exists() else None,
    )


@router.post("/pair", response_model=PairResponse, status_code=status.HTTP_201_CREATED)
async def pair(body: PairRequest, session: AsyncSession = Depends(get_session)) -> PairResponse:
    """Open to unauthenticated clients: the code is the credential."""
    if not device_auth.pairing_codes.redeem(body.code):
        logger.warning("pairing_failed")
        raise HypatiaError(ErrorCode.PAIRING_CODE_INVALID)
    device, token = await device_auth.create_device(session, body.device_name)
    logger.info("device_paired", device_id=str(device.id), name=device.name)
    return PairResponse(device=DeviceRead.model_validate(device), token=token)


@router.get("", response_model=list[DeviceRead])
async def list_devices(session: AsyncSession = Depends(get_session)) -> list[DeviceRead]:
    devices = await session.scalars(
        select(Device).where(Device.revoked_at.is_(None)).order_by(Device.created_at)
    )
    return [DeviceRead.model_validate(d) for d in devices]


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(
    device_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Response:
    device = await session.get(Device, device_id)
    if device is None or device.revoked_at is not None:
        raise ResourceNotFoundError(f"Device {device_id} not found")
    device.revoked_at = datetime.now(UTC)
    await session.commit()
    logger.info("device_revoked", device_id=str(device_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
