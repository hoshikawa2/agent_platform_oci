from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agent_framework.oci.auth")


def get_oci_config_and_signer(settings: Any) -> tuple[dict[str, Any], Any | None]:
    """Resolve OCI authentication for SDK clients.

    Supported modes:
    - config_file: ~/.oci/config + profile (current/default behavior)
    - instance_principal: OCI Instance Principal signer for compute/OKE workloads
    - resource_principal: OCI Resource Principal signer for Functions/Resource Principal contexts

    The function returns (config, signer), matching OCI Python SDK client constructors.
    """
    import oci

    mode = str(getattr(settings, "OCI_AUTH_MODE", "config_file") or "config_file").strip().lower()
    region = getattr(settings, "OCI_REGION", None)

    if mode in {"config", "config_file", "api_key", "user_principal"}:
        config_file = getattr(settings, "OCI_CONFIG_FILE", "~/.oci/config")
        profile = getattr(settings, "OCI_PROFILE", "DEFAULT")
        config = oci.config.from_file(config_file, profile)
        if region:
            config.setdefault("region", region)
        return config, None

    if mode in {"instance_principal", "instance_principals"}:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        config: dict[str, Any] = {"region": region or getattr(signer, "region", None)}
        logger.info("OCI auth resolved with instance principal region=%s", config.get("region"))
        return config, signer

    if mode in {"resource_principal", "resource_principals"}:
        signer = oci.auth.signers.get_resource_principals_signer()
        config = {"region": region or getattr(signer, "region", None)}
        logger.info("OCI auth resolved with resource principal region=%s", config.get("region"))
        return config, signer

    raise ValueError(
        "Unsupported OCI_AUTH_MODE=%r. Use config_file, instance_principal or resource_principal." % mode
    )
