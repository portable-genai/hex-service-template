"""GCP AuditSinkPort: the Cloud Logging WORM bucket (SDK imports stay lazy).

The bucket is Write-Once-Read-Many once the deployment locks it (``infra/terraform``,
``worm_locked``). That variable has no default, so the lock is always a stated decision rather
than one this repository took on a deployment's behalf.
"""

from __future__ import annotations

from hex_service_kit.serialization import to_jsonable

from ...config import Settings
from ...domain.kernel import AuditEvent


class CloudAuditAdapter:
    """Write already-redacted audit events to a Cloud Logging WORM sink.

    The ``google-cloud-logging`` import lives inside the method so the ``local``/``onprem``
    profiles import this module with no GCP SDK installed (the portability proof).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record(self, event: AuditEvent) -> None:  # pragma: no cover - needs live GCP
        # Lazy import: absent in the offline profile and in CI (hence import-not-found ignore).
        from google.cloud import logging as cloud_logging

        client = cloud_logging.Client()
        logger = client.logger("{{ cookiecutter.package_name }}-audit")
        logger.log_struct(to_jsonable(event), severity="NOTICE")
