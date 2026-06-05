"""Telephony provider factory — selects the active adapter from settings (PRD §1.1)."""

from __future__ import annotations

from callwise.config import Settings, get_settings
from callwise.providers.telephony.base import TelephonyProvider
from callwise.providers.telephony.mock import MockTelephonyProvider


def get_telephony_provider_by_name(name: str, settings: Settings | None = None) -> TelephonyProvider:
    """Resolve an adapter by provider name. Used by the reconciler to query the *session's*
    provider (`sess.provider`) rather than the globally-configured default."""
    settings = settings or get_settings()
    match name:
        case "mock":
            return MockTelephonyProvider(base_url=settings.base_url)
        case "exotel":
            from callwise.providers.telephony.exotel import ExotelProvider

            return ExotelProvider(settings)
        case "twilio":
            from callwise.providers.telephony.twilio import TwilioProvider

            return TwilioProvider(settings)
        case "plivo":
            from callwise.providers.telephony.plivo import PlivoProvider

            return PlivoProvider(settings)
        case "telnyx":
            from callwise.providers.telephony.telnyx import TelnyxProvider

            return TelnyxProvider(settings)
        case _:
            raise NotImplementedError(f"telephony provider {name!r} not wired up")


def get_telephony_provider(settings: Settings | None = None) -> TelephonyProvider:
    settings = settings or get_settings()
    return get_telephony_provider_by_name(settings.telephony_provider.value, settings)
