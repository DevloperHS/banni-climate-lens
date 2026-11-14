"""Google Earth Engine authentication and status. Credentials come only from environment
variables / files outside Git. Failures are reported, never replaced with fake data."""
from __future__ import annotations
import threading
from ..core.config import get_settings

_lock = threading.Lock()
_state: dict = {"initialised": False, "error": None, "mode": None}

SETUP_HELP = (
    "Earth Engine is not available. Configure ONE of: (A) service account - set GCL_EE_PROJECT, "
    "GCL_EE_SERVICE_ACCOUNT and GCL_EE_PRIVATE_KEY_FILE in .env; or (B) local development - run "
    "`earthengine authenticate` then set GCL_EE_PROJECT. See docs/SETUP.md."
)


class EarthEngineUnavailable(RuntimeError):
    pass


def get_ee():
    """Return an initialised `ee` module or raise EarthEngineUnavailable with a setup message."""
    s = get_settings()
    with _lock:
        if _state["initialised"]:
            import ee
            return ee
        try:
            import ee
        except ImportError as e:  # pragma: no cover
            _state["error"] = f"earthengine-api not installed: {e}"
            raise EarthEngineUnavailable(_state["error"] + " " + SETUP_HELP)
        if not s.ee_project:
            _state["error"] = "GCL_EE_PROJECT is not set."
            raise EarthEngineUnavailable(_state["error"] + " " + SETUP_HELP)
        try:
            if s.ee_service_account and s.ee_private_key_file:
                creds = ee.ServiceAccountCredentials(s.ee_service_account, s.ee_private_key_file)
                ee.Initialize(creds, project=s.ee_project)
                _state["mode"] = "service-account"
            else:
                ee.Initialize(project=s.ee_project)
                _state["mode"] = "user-credentials"
            _state.update(initialised=True, error=None)
            return ee
        except Exception as e:
            _state["error"] = f"{type(e).__name__}: {e}"
            raise EarthEngineUnavailable(_state["error"] + " " + SETUP_HELP)


def status(probe: bool = False) -> dict:
    """Cheap by default (configuration only, no network). probe=True attempts a real initialisation."""
    s = get_settings()
    configured = bool(s.ee_project)
    out = {
        "project_configured": configured,
        "auth_mode": "service-account" if (s.ee_service_account and s.ee_private_key_file)
        else ("user-credentials" if configured else None),
        "initialised": _state["initialised"], "verified": False, "error": _state["error"],
        "setup_help": None if _state["initialised"] else SETUP_HELP,
    }
    if probe:
        try:
            ee = get_ee()
            ee.Number(1).getInfo()
            out.update(initialised=True, verified=True, error=None, setup_help=None)
        except EarthEngineUnavailable as e:
            out.update(error=str(e))
        except Exception as e:
            out.update(error=f"{type(e).__name__}: {e}")
    return out
