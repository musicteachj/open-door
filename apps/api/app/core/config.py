"""Application settings, read from the environment and validated once at startup."""

import ipaddress
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    Field,
    PostgresDsn,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from app.core.encryption import DEFAULT_KEYRING_PATH

# What a browser sends in its Origin header: a lowercase scheme and host, an optional port, and
# nothing after them. The same-origin check compares that header with APP_ORIGIN character for
# character, so a trailing slash or a path here would refuse every request. IPv6 literals such as
# http://[::1]:5173 are not supported.
ORIGIN_PATTERN = re.compile(r"(https?)://[a-z0-9.-]+(?::([0-9]{1,5}))?")
# Browsers leave the default port out of the Origin header, so it can never appear in APP_ORIGIN.
DEFAULT_PORTS = {"http": 80, "https": 443}
DEFAULT_APP_ORIGIN = "http://localhost:5173"
# The only hosts a production origin may use over plain http: the local production run. The match is
# exact, so http://localhost.example.com and http://127.0.0.2 are refused.
LOOPBACK_HOSTS = ("localhost", "127.0.0.1")

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# Cloudflare's documented Turnstile test keys. Their secrets answer without any network call (see
# app/modules/sandbox/turnstile.py), so they are fit for development and tests only.
# Source: Turnstile "Testing", https://developers.cloudflare.com/turnstile/troubleshooting/testing/,
# read from developers.cloudflare.com on 2026-11-11.
TURNSTILE_TEST_SITE_KEYS = (
    "1x00000000000000000000AA",
    "2x00000000000000000000AB",
    "1x00000000000000000000BB",
    "2x00000000000000000000BB",
    "3x00000000000000000000FF",
)
TURNSTILE_PASS_SITE_KEY = "1x00000000000000000000AA"  # noqa: S105
# The three test secrets: the first passes the dummy token, the second always fails, the third
# answers `timeout-or-duplicate`. Public values.
TURNSTILE_PASS_SECRET = "1x0000000000000000000000000000000AA"  # noqa: S105
TURNSTILE_ALWAYS_FAIL_SECRET = "2x0000000000000000000000000000000AA"  # noqa: S105
TURNSTILE_ALREADY_SPENT_SECRET = "3x0000000000000000000000000000000AA"  # noqa: S105
TURNSTILE_TEST_SECRETS = (
    TURNSTILE_PASS_SECRET,
    TURNSTILE_ALWAYS_FAIL_SECRET,
    TURNSTILE_ALREADY_SPENT_SECRET,
)
# The address-hash key used when none is set outside production. It is public in the repository, so
# production refuses it with no exception.
DEVELOPMENT_IP_HASH_KEY = "development-only-sandbox-ip-hash-key-not-secret"
MIN_IP_HASH_KEY_BYTES = 32


def require_asyncpg_scheme(value: PostgresDsn, name: str) -> PostgresDsn:
    """The one check every database URL setting shares (also used by owner_settings)."""
    if value.scheme != "postgresql+asyncpg":
        msg = f"{name.upper()} must use the postgresql+asyncpg:// scheme"
        raise ValueError(msg)
    return value


# The settings whose empty or blank value in the environment is ignored, so that the value in .env
# is used. A shell can export a key as an empty string (a claude agent shell exports
# ANTHROPIC_API_KEY that way), and that would otherwise shadow .env for every entry point: alembic,
# the scripts, pytest, and uvicorn by hand. No other setting gets this: an empty APP_ENV or
# AI_TRANSPORT must still fail validation, not quietly become the default.
KEY_SETTINGS = (
    "anthropic_api_key",
    "voyage_api_key",
    "encryption_keyring",
    "encryption_keyring_file",
)


class EnvWithoutBlankKeys(PydanticBaseSettingsSource):
    """The environment source, minus any API key whose value is empty or only spaces."""

    def __init__(self, environment: PydanticBaseSettingsSource) -> None:
        super().__init__(environment.settings_cls)
        self.environment = environment

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        raise NotImplementedError  # Only __call__ is used.

    def __call__(self) -> dict[str, Any]:
        return {
            name: value
            for name, value in self.environment().items()
            if not (name in KEY_SETTINGS and isinstance(value, str) and not value.strip())
        }


class Settings(BaseSettings):
    """Every setting the API reads. A missing or malformed value stops the process at boot."""

    model_config = SettingsConfigDict(
        # Relative to the working directory: `make` and CI always run the API from apps/api.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # A malformed database URL would otherwise print its password in the startup error.
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    # The API's own login, a member of od_app. Row-level security applies to it.
    database_url: PostgresDsn = Field(repr=False)
    # The owner's and the cleanup login's URLs are not here: the API process holds only its own
    # login. Alembic and the owner scripts read OwnerSettings, the cleanup job and its tests read
    # CleanupSettings (app.core.owner_settings). A .env may still hold them; extra keys are ignored.
    # The web app's origin, for the same-origin check on every request. Production requires it.
    app_origin: str = DEFAULT_APP_ORIGIN
    # The client addresses (and networks) whose X-Forwarded-For uvicorn may trust: the load
    # balancer's. A comma list in FORWARDED_ALLOW_IPS; empty means only the direct peer, never "*".
    # Stage 2 passes it to uvicorn's --forwarded-allow-ips.
    forwarded_allow_ips: Annotated[tuple[Network, ...], NoDecode] = ()
    # The built web app (its `dist/`), which the production image sets. Unset in development, where
    # Vite serves the web app: then the API serves nothing outside /api/ and sends no CSP.
    web_dist_dir: Path | None = None
    # Cloudflare Turnstile's public site key, written into the page's meta tag. It is public by
    # design. Outside production a blank key and secret become Cloudflare's always-pass test keys;
    # the API refuses to start in production without both, or with test keys unless the origin
    # is a loopback one (require_entry_settings_fit_for_production, checked at startup, not here).
    turnstile_site_key: str = ""
    turnstile_secret_key: SecretStr | None = Field(default=None, repr=False)
    # The key of the HMAC that hides a visitor's address in `sandbox_starts` (ADR 0021). At least 32
    # bytes. Outside production a fixed development value is the default; production refuses it.
    sandbox_ip_hash_key: SecretStr = Field(default=SecretStr(DEVELOPMENT_IP_HASH_KEY), repr=False)
    # How many sandboxes one address may start in an hour and in a rolling 24 hours, and how many
    # all addresses together may start in a UTC day.
    sandbox_starts_per_hour: int = Field(default=5, ge=1)
    sandbox_starts_per_day: int = Field(default=20, ge=1)
    sandbox_starts_daily_total: int = Field(default=500, ge=1)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # `make embed` and the API with AI_TRANSPORT=anthropic use it (the API embeds each handbook
    # question). Without it the search is full-text only. An empty value counts as unset.
    voyage_api_key: SecretStr | None = Field(default=None, repr=False)

    # Only the anthropic transport needs it, and it checks for the key when it is built
    # (anthropic_transport.from_settings), not here: Settings is also built by alembic, the setup
    # scripts, and the tests, which never call the model. An empty value counts as unset.
    anthropic_api_key: SecretStr | None = Field(default=None, repr=False)
    # What answers the assistant's questions. `scripted` is a rule-based stand-in and `replay` plays
    # back recorded runs; neither makes a paid call. Production must use `anthropic`, which the API
    # checks when it starts (app.ai.transport.require_a_transport_fit_for), not here: alembic and
    # the setup scripts build Settings too, and never call the model.
    ai_transport: Literal["anthropic", "scripted", "replay"] = "scripted"
    # Test only: how long the scripted model waits, paced like the real one, for the load test
    # (`make load`). `none` makes no wait. Production refuses anything but `none` (checked at
    # startup by app.ai.transport.require_a_transport_fit_for). See app.ai.scripted.REALISTIC.
    scripted_delay_profile: Literal["none", "realistic"] = "none"
    # What one sandbox may spend on the assistant, and what all sandboxes may spend per UTC day.
    ai_sandbox_budget_usd: Decimal = Field(default=Decimal("1.00"), gt=0)
    ai_daily_budget_usd: Decimal = Field(default=Decimal("3.00"), gt=0)
    # Seconds of silence before a stream sends a keep-alive comment. 0 turns it off, which the
    # proxy check uses as its control run.
    ai_heartbeat_seconds: int = Field(default=15, ge=0)

    # The key-encryption keys for case and conversation text (ADR 0015): lines of `id:base64`,
    # newest first, either in a file or in ENCRYPTION_KEYRING. Both are secret values and never
    # print. Optional here, like the API keys, because alembic, the scripts, and the tests build
    # Settings and never encrypt; `create_app` refuses to start without a keyring. The file path is
    # relative to apps/api whatever the working directory, and `make setup` writes the file. An
    # empty ENCRYPTION_KEYRING or ENCRYPTION_KEYRING_FILE counts as unset.
    encryption_keyring_file: SecretStr | None = Field(
        default=SecretStr(DEFAULT_KEYRING_PATH), repr=False
    )
    encryption_keyring: SecretStr | None = Field(default=None, repr=False)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            EnvWithoutBlankKeys(env_settings),
            dotenv_settings,
            file_secret_settings,
        )

    @model_validator(mode="before")
    @classmethod
    def blank_keyring_file_is_unset(cls, data: Any) -> Any:
        # A blank ENCRYPTION_KEYRING_FILE= in .env counts as unset, and unset means the default
        # path (a file that is simply None, set in code, stays None). Dropping the blank here, from
        # the raw input, keeps the field out of `model_fields_set`, so the two-keyrings check below
        # needs no marker that a copy or a rebuild from a dump could lose.
        if isinstance(data, dict):
            value = data.get("encryption_keyring_file")
            if isinstance(value, str) and not value.strip():
                return {k: v for k, v in data.items() if k != "encryption_keyring_file"}
        return data

    @field_validator(
        "voyage_api_key",
        "anthropic_api_key",
        "encryption_keyring",
        "turnstile_secret_key",
        mode="before",
    )
    @classmethod
    def empty_key_is_none(cls, value: object) -> object:
        # An empty value written in .env itself means no key. (An empty one in the environment never
        # gets here: `EnvWithoutBlankKeys` drops it, so .env's value is used.)
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def refuse_two_keyrings(self) -> Self:
        # The file has a default, so only a file someone set counts as set. A blank value was
        # dropped as unset and is not a second keyring, but an explicit path is, even when it
        # spells the default.
        file_is_set = (
            "encryption_keyring_file" in self.model_fields_set
            and self.encryption_keyring_file is not None
        )
        if self.encryption_keyring is not None and file_is_set:
            msg = "Set ENCRYPTION_KEYRING or ENCRYPTION_KEYRING_FILE, not both."
            raise ValueError(msg)
        return self

    @field_validator("database_url")
    @classmethod
    def require_asyncpg_driver(cls, value: PostgresDsn, info: ValidationInfo) -> PostgresDsn:
        return require_asyncpg_scheme(value, str(info.field_name))

    @field_validator("web_dist_dir", mode="before")
    @classmethod
    def blank_web_dist_dir_is_unset(cls, value: object) -> object:
        # `WEB_DIST_DIR=` means "not set", as an empty key does; Path("") would be the working
        # directory and turn the web serving on.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("forwarded_allow_ips", mode="before")
    @classmethod
    def parse_forwarded_allow_ips(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        entries = [entry.strip() for entry in value.split(",") if entry.strip()]
        try:
            networks = tuple(ipaddress.ip_network(entry, strict=True) for entry in entries)
        except ValueError as error:
            detail = (
                " (host bits set: write the network's own address)"
                if "host bits" in str(error)
                else ""
            )
            msg = (
                "FORWARDED_ALLOW_IPS must be a comma list of addresses and networks "
                f"such as 10.0.1.5,10.0.2.0/24 (no wildcard){detail}"
            )
            raise ValueError(msg) from None
        if any(network.prefixlen == 0 for network in networks):
            msg = "FORWARDED_ALLOW_IPS must not include 0.0.0.0/0 or ::/0: that trusts every client"
            raise ValueError(msg)
        return networks

    @field_validator("app_origin")
    @classmethod
    def require_bare_origin(cls, value: str) -> str:
        match = ORIGIN_PATTERN.fullmatch(value)
        if match is None:
            msg = (
                "APP_ORIGIN must look like http://localhost:5173: lowercase, "
                "with no path and no trailing slash"
            )
            raise ValueError(msg)
        scheme, port = match.groups()
        if port is not None:
            if not 1 <= int(port) <= 65535:
                msg = "APP_ORIGIN port must be between 1 and 65535"
                raise ValueError(msg)
            if port.startswith("0"):
                # Browsers send the port as a plain number, so 05173 would never equal 5173.
                msg = "APP_ORIGIN port must be written without leading zeros"
                raise ValueError(msg)
            if int(port) == DEFAULT_PORTS[scheme]:
                msg = "APP_ORIGIN must leave the default port out, because browsers omit it"
                raise ValueError(msg)
        return value

    @field_validator("sandbox_ip_hash_key", mode="before")
    @classmethod
    def blank_ip_hash_key_is_the_default(cls, value: object) -> object:
        # `SANDBOX_IP_HASH_KEY=` in .env means "not set": the development value, which production
        # then refuses.
        if isinstance(value, str) and not value.strip():
            return DEVELOPMENT_IP_HASH_KEY
        return value

    @field_validator("sandbox_ip_hash_key")
    @classmethod
    def require_a_long_ip_hash_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < MIN_IP_HASH_KEY_BYTES:
            msg = f"SANDBOX_IP_HASH_KEY must be at least {MIN_IP_HASH_KEY_BYTES} bytes"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def default_the_turnstile_keys_outside_production(self) -> Self:
        # Outside production a missing key pair means Cloudflare's always-pass test keys, so
        # development, the tests, and the browser tests need no Cloudflare account.
        if self.app_env == "production":
            return self
        site_blank = not self.turnstile_site_key
        secret_blank = self.turnstile_secret_key is None
        # The pair is defaulted only when both are blank. One real key beside a test key would
        # mix them, and every start would fail as "couldn't confirm".
        if site_blank and not secret_blank:
            msg = "TURNSTILE_SITE_KEY is missing: set both Turnstile keys or neither"
            raise ValueError(msg)
        if secret_blank and not site_blank:
            msg = "TURNSTILE_SECRET_KEY is missing: set both Turnstile keys or neither"
            raise ValueError(msg)
        if site_blank and secret_blank:
            self.turnstile_site_key = TURNSTILE_PASS_SITE_KEY
            self.turnstile_secret_key = SecretStr(TURNSTILE_PASS_SECRET)
        return self

    @model_validator(mode="after")
    def refuse_a_test_origin_in_production(self) -> Self:
        if self.app_env != "production":
            return self
        if self.app_origin == DEFAULT_APP_ORIGIN:
            msg = "APP_ORIGIN must be set in production: it is still the development default"
            raise ValueError(msg)
        if not self.app_origin.startswith("https://") and not is_loopback_origin(self.app_origin):
            msg = (
                "APP_ORIGIN must use https in production (only http://localhost:<port> and "
                "http://127.0.0.1:<port> may use http)"
            )
            raise ValueError(msg)
        return self


def is_loopback_origin(origin: str) -> bool:
    """True for http(s)://localhost:<port> and http(s)://127.0.0.1:<port>. The port is required and
    the host match is exact, so https://localhost and http://localhost.example.com are not loopback.
    The one test behind every loopback exemption (plain http, the Turnstile test keys, the
    forwarded-address list)."""
    match = ORIGIN_PATTERN.fullmatch(origin)
    if match is None or match.group(2) is None:
        return False
    return origin.removeprefix(f"{match.group(1)}://").split(":")[0] in LOOPBACK_HOSTS


def require_entry_settings_fit_for_production(settings: Settings) -> None:
    """Refuse to start the API in production without what serving visitors needs: the Turnstile
    keys (real ones, unless the origin is a loopback one), a real address-hash key, and the load
    balancer's addresses. Raises ValueError, naming the setting and never its value.

    The API calls this at startup. It is not a rule on `Settings`, because alembic, the setup
    scripts, and the cleanup job build `Settings` in production too and never serve a visitor, so
    they need none of these (like `app.ai.transport.require_a_transport_fit_for`).
    """
    if settings.app_env != "production":
        return
    if settings.sandbox_ip_hash_key.get_secret_value() == DEVELOPMENT_IP_HASH_KEY:
        msg = "SANDBOX_IP_HASH_KEY must be set in production: it is still the development value"
        raise ValueError(msg)
    if not settings.turnstile_site_key:
        msg = "TURNSTILE_SITE_KEY must be set in production"
        raise ValueError(msg)
    if settings.turnstile_secret_key is None:
        msg = "TURNSTILE_SECRET_KEY must be set in production"
        raise ValueError(msg)
    if is_loopback_origin(settings.app_origin):
        return
    if settings.turnstile_site_key in TURNSTILE_TEST_SITE_KEYS:
        msg = "TURNSTILE_SITE_KEY is a Cloudflare test key: not allowed in production"
        raise ValueError(msg)
    if settings.turnstile_secret_key.get_secret_value() in TURNSTILE_TEST_SECRETS:
        msg = "TURNSTILE_SECRET_KEY is a Cloudflare test key: not allowed in production"
        raise ValueError(msg)
    if not settings.forwarded_allow_ips:
        # Behind a load balancer every visitor would arrive from the balancer's address, so the
        # per-address limit on starting sandboxes would become one limit for the site.
        msg = (
            "FORWARDED_ALLOW_IPS must be set in production (the load balancer's addresses): "
            "without it every visitor shares one client address"
        )
        raise ValueError(msg)


@lru_cache
def get_settings() -> Settings:
    """Read settings once per process."""
    return Settings()
