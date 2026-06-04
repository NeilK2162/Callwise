"""Telephony provider factory — selects the active adapter from settings (PRD §1.1)."""

from __future__ import annotations

from callwise.config import Settings, TelephonyProvider as TelephonyProviderName, get_settings
from callwise.providers.telephony.base import TelephonyProvider
from callwise.providers.telephony.mock import MockTelephonyProvider


def get_telephony_provider(settings: Settings | None = None) -> TelephonyProvider:
    settings = settings or get_settings()
    match settings.telephony_provider:
        case TelephonyProviderName.mock:
            return MockTelephonyProvider(base_url=settings.base_url)
        case TelephonyProviderName.exotel:
            from callwise.providers.telephony.exotel import ExotelProvider

            return ExotelProvider(settings)
        case TelephonyProviderName.twilio:
            from callwise.providers.telephony.twilio import TwilioProvider

            return TwilioProvider(settings)
        case _:
            raise NotImplementedError(
                f"telephony provider {settings.telephony_provider!r} not wired up"
            )
