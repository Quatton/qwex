import os
import logging
from kubernetes import config as k8s_config
from kubernetes.client import Configuration


logger = logging.getLogger(__name__)


def setup() -> None:
    """Setup Kubernetes client.

    Uses K8S_PROXY env var if set (dev), otherwise in-cluster config (prod).
    """
    proxy = os.getenv("K8S_PROXY")

    if proxy:
        logger.info("Using K8S_PROXY=%s", proxy)
        config = Configuration.get_default_copy()
        config.host = proxy.rstrip("/")
        Configuration.set_default(config)
        return

    try:
        k8s_config.load_incluster_config()
        logger.info("Loaded in-cluster config")
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        raise RuntimeError(
            "Kubernetes unavailable. Set K8S_PROXY for dev or run in-cluster."
        ) from e


__all__ = ["setup"]
