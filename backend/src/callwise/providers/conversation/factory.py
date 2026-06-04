"""Conversation provider factory (PRD §1.1, §5.4)."""

from __future__ import annotations

from callwise.config import (
    ConversationProvider as ConversationProviderName,
    Settings,
    get_settings,
)
from callwise.providers.conversation.base import ConversationProvider
from callwise.providers.conversation.mock import MockConversationProvider


def get_conversation_provider(settings: Settings | None = None) -> ConversationProvider:
    settings = settings or get_settings()
    match settings.conversation_provider:
        case ConversationProviderName.mock:
            return MockConversationProvider()
        case ConversationProviderName.elevenlabs:
            from callwise.providers.conversation.elevenlabs import ElevenLabsProvider

            return ElevenLabsProvider(settings)
        case ConversationProviderName.livekit:
            from callwise.providers.conversation.livekit import LiveKitProvider

            return LiveKitProvider(settings)
        case _:
            raise NotImplementedError(
                f"conversation provider {settings.conversation_provider!r} not wired up"
            )
