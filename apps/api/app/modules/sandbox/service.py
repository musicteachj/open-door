"""Creating a sandbox: a new company, seeded, with the visitor signed in as one of its personas."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.models import Tenant
from app.db.tenancy import NO_TENANT, TenantContext, tenant_session
from app.modules.audit.service import record_event
from app.modules.identity.actor import load_actor
from app.modules.identity.sessions import end_session, find_session, start_session
from app.modules.identity.tokens import SessionTokens
from app.modules.people.queries import get_me
from app.modules.people.schemas import Me, PersonaKey
from app.modules.sandbox.seed import build_company, insert_company

# A sandbox, and every session in it, is deleted 24 hours after it is created (ADR 0007).
SANDBOX_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class NewSandbox:
    tenant_id: UUID
    expires_at: datetime
    tokens: SessionTokens
    me: Me


async def _end_replaced_session(engine: AsyncEngine, token_hash: bytes) -> None:
    # The sessions table has no row-level security, so the lookup needs no tenant.
    async with tenant_session(engine, NO_TENANT) as db:
        old = await find_session(db, token_hash)
    if old is None:
        return
    async with tenant_session(engine, TenantContext(old.tenant_id, old.person_id)) as db:
        if await end_session(db, token_hash):
            await record_event(
                db, tenant_id=old.tenant_id, actor_id=old.person_id, action="session.ended"
            )


async def create_sandbox(
    engine: AsyncEngine, persona: PersonaKey, replacing: bytes | None
) -> NewSandbox:
    """Create and seed a sandbox, and start a session in it as `persona`, in one transaction.

    `replacing` is the token hash of a session the visitor already had. It ends first, in its own
    transaction scoped to its own sandbox, where `session.ended` is audited, so each sandbox
    creation leaves the browser with exactly one session. If creating the new sandbox then fails,
    the visitor has no session.
    """
    if replacing is not None:
        await _end_replaced_session(engine, replacing)
    tenant_id = uuid4()
    created_at = datetime.now(UTC)
    expires_at = created_at + SANDBOX_LIFETIME
    company = build_company(tenant_id, created_at.date())
    person_id = next(person.id for person in company.people if person.persona_key == persona)
    async with tenant_session(engine, TenantContext(tenant_id, person_id)) as db:
        await db.execute(
            insert(Tenant).values(
                id=tenant_id, expires_at=expires_at, anchor_date=company.anchor_date
            )
        )
        await insert_company(db, company)
        tokens = await start_session(db, tenant_id, person_id)
        await record_event(
            db,
            tenant_id=tenant_id,
            actor_id=person_id,
            action="sandbox.created",
            target_type="tenant",
            target_id=tenant_id,
            after={"personaKey": persona},
        )
        actor = await load_actor(db, tenant_id, person_id)
        if actor is None:
            msg = f"The seed company has no {persona!r} persona"
            raise RuntimeError(msg)
        me = await get_me(db, actor, expires_at)
    return NewSandbox(tenant_id, expires_at, tokens, me)
