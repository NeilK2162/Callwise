"""Centralised configuration via pydantic-settings.

All tunables come from the environment (12-factor). Secrets in production come from
AWS Secrets Manager / SSM injected as env vars — never committed files (PRD §14.5).
Startup validation fails fast on unsafe config (e.g. a too-short JWT secret).
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    dev = "dev"
    staging = "staging"
    prod = "prod"


class TelephonyProvider(StrEnum):
    mock = "mock"
    exotel = "exotel"
    twilio = "twilio"
    plivo = "plivo"
    telnyx = "telnyx"


class ConversationProvider(StrEnum):
    mock = "mock"
    elevenlabs = "elevenlabs"
    livekit = "livekit"


class LLMProvider(StrEnum):
    mock = "mock"
    azure_openai = "azure_openai"
    openai = "openai"
    anthropic = "anthropic"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- App ---
    app_env: AppEnv = AppEnv.dev
    log_level: str = "INFO"
    base_url: str = "http://localhost:8001"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://callwise:callwise@pgbouncer:6432/callwise"
    database_url_direct: str = "postgresql+asyncpg://callwise:callwise@postgres:5432/callwise"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- Auth ---
    jwt_secret: str = "dev-only-change-me-to-a-32+char-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 1_209_600
    allow_registration: bool = True

    # --- Object store ---
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "callwise"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # --- Provider selection ---
    telephony_provider: TelephonyProvider = TelephonyProvider.mock
    conversation_provider: ConversationProvider = ConversationProvider.mock
    llm_provider: LLMProvider = LLMProvider.mock

    # --- Telephony creds ---
    exotel_sid: str | None = None
    exotel_api_key: str | None = None
    exotel_api_token: str | None = None
    exotel_subdomain: str = "api.exotel.com"  # api.in.exotel.com for the Mumbai cluster
    exotel_caller_id: str | None = None  # your ExoPhone (virtual number) shown as CallerId
    exotel_from: str | None = None  # number/SIP dialed first to bridge the agent leg
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    plivo_auth_id: str | None = None
    plivo_auth_token: str | None = None
    plivo_from: str | None = None
    telnyx_api_key: str | None = None
    telnyx_connection_id: str | None = None
    telnyx_from: str | None = None

    # --- Conversation creds ---
    elevenlabs_api_key: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_webhook_secret: str | None = None
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"  # agent TTS voice (ElevenLabs voice id)
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    livekit_agent_name: str = "callwise-agent"
    soniox_api_key: str | None = None  # Soniox STT (LiveKit path); plugin reads SONIOX_API_KEY

    # --- Voice agent (LiveKit: Soniox STT → LLM → ElevenLabs TTS) ---
    agent_llm_provider: str = "openai"  # openai | anthropic (the conversation brain)
    agent_llm_model: str = "gpt-4o-mini"
    clinic_name: str = "Bright Smile Dental"
    inbound_campaign_id: str | None = None  # attribute inbound calls to this campaign

    # --- Agent server tools (ElevenLabs Agent orchestration path) ---
    # Shared secret the ElevenLabs agent sends as `X-Callwise-Agent-Secret` on every tool
    # call. Required outside dev. The agent's mid-call outcomes are stashed by conversation_id
    # for this long so the post-call verifier can apply them to the card.
    agent_tools_secret: str | None = None
    agent_tools_outcome_ttl_seconds: int = 21_600  # 6h

    # --- Booking / scheduler (Cal.com live booking) ---
    calcom_api_key: str | None = None
    calcom_event_type_id: int | None = None
    calcom_timezone: str = "Asia/Kolkata"
    calcom_api_version_bookings: str = "2024-08-13"
    calcom_api_version_slots: str = "2024-09-04"

    # --- LLM creds ---
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = None  # cheap default model (deployment name)
    azure_openai_escalation_deployment: str | None = None  # strong model for low-confidence
    azure_openai_api_version: str = "2024-08-01-preview"
    openai_api_key: str | None = None
    # Verify with a cheap model by default; escalate to a strong one only on low confidence.
    openai_model: str = "gpt-4o-mini"  # supports Structured Outputs; ~15-30x cheaper
    openai_escalation_model: str | None = None  # e.g. "gpt-4o-2024-08-06"
    openai_summarize_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    # --- LLM cost controls (PRD §19) ---
    llm_max_output_tokens: int = 400  # verification JSON is small; cap runaway generations
    llm_confidence_escalation_threshold: float = 0.6  # below → re-verify with strong model
    transcript_max_turns: int = 40  # trim long transcripts to the decision-relevant turns
    transcript_max_chars_per_turn: int = 600
    llm_cost_micros_per_1k_tokens: int = 200  # blended estimate for the spend-ceiling accrual

    # --- Webhook security ---
    webhook_timestamp_tolerance_seconds: int = 300
    context_token_secret: str = "dev-only-change-me-context-signing-secret"
    context_token_ttl_seconds: int = 600

    # --- Governors ---
    rate_limit_exotel: str = "40:80"
    rate_limit_twilio: str = "10:20"
    rate_limit_elevenlabs: str = "50:100"
    global_max_concurrent_calls: int = 5000
    concurrency_lease_ttl_seconds: int = 180

    # --- Queue / broker ---
    dial_stream: str = "dial:stream"
    dial_consumer_group: str = "dialers"
    verify_stream: str = "verify:stream"
    verify_consumer_group: str = "verifiers"
    ingest_stream: str = "ingest:stream"
    ingest_consumer_group: str = "ingesters"
    dlq_stream: str = "dlq:stream"
    queue_max_attempts: int = 5
    queue_claim_idle_ms: int = 60_000
    ingest_sync_size_limit: int = 8 * 1024 * 1024  # >this → async S3 ingest (PRD §5.1)

    # --- Observability ---
    otel_exporter_otlp_endpoint: str | None = None  # e.g. http://otel-collector:4317

    # --- Reconciler ---
    reconciler_interval_seconds: int = 45
    session_stale_ttl_seconds: int = 300

    # --- Cost safety ---
    default_max_attempts_per_contact: int = 3
    llm_tokens_per_minute_budget: int = 200_000

    @field_validator("jwt_secret", "context_token_secret")
    @classmethod
    def _secret_long_enough(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("signing secret must be at least 32 characters (PRD §14.1)")
        return v

    @property
    def provider_rate_limits(self) -> dict[str, tuple[float, int]]:
        """Parse `rate:capacity` strings into {provider: (tokens_per_sec, burst)}."""
        out: dict[str, tuple[float, int]] = {}
        for provider, raw in {
            "exotel": self.rate_limit_exotel,
            "twilio": self.rate_limit_twilio,
            "elevenlabs": self.rate_limit_elevenlabs,
        }.items():
            rate, _, cap = raw.partition(":")
            out[provider] = (float(rate), int(cap or rate))
        return out


@lru_cache
def get_settings() -> Settings:
    """Process-wide singleton. Cached so validation runs once at first import."""
    return Settings()
