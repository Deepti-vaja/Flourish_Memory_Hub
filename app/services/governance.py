"""
Flourish Governed Memory Hub - Governance Tollgate & Steward Adjudication Engine (`Stage 4 Engine`)
Strictly adheres to Enterprise Technical Blueprint (`Section 1.1`, `Section 11.5`, `Section 12`, `Section 14`, `Section 19 RSK-05`, `Section 26.4`).
Operates asynchronously over an open SQLAlchemy AsyncSession (`psycopg3`).
Enforces Role/Clearance boundaries, Four-Eyes Principle (`BR-05`), Blue-Green promotion/demotion (`RSK-05`),
immutable `governance_decisions` persistence, and cryptographic HMAC audit chaining (`RSK-04`).
"""

import datetime
import uuid
from typing import Any, Dict, List, Optional, Union
import sqlalchemy.exc
from sqlalchemy import select, update
from app.audit.chainer import AuditChainService, AuditEventPayload
from app.core.constants import AuditActionEnum, KnowledgeStatusEnum
from app.models.governance import GovernanceDecision
from app.models.knowledge import KnowledgeItem
from app.security.context import CallerContext
from app.services.governance_exceptions import (
    DocumentAlreadyApprovedError,
    DocumentAlreadyRejectedError,
    DocumentNotFoundError,
    DocumentNotPendingError,
    FourEyesPrincipleViolationError,
    GovernanceError,
    StewardAuthorizationError,
)
from app.services.governance_protocols import GovernanceServiceProtocol


class GovernanceService(GovernanceServiceProtocol):
    """
    Stage 4 Governance Adjudication Core Engine (`Section 26.4`).
    All operations execute inside an externally opened transaction boundary (`session.begin()`).
    Never calls `session.begin()`, `session.commit()`, `session.rollback()`, or `session.close()` directly (`Section 15 / Section 26.4`).
    """

    def __init__(self, audit_service: Optional[AuditChainService] = None) -> None:
        self.audit_service = audit_service or AuditChainService()

    async def adjudicate_item(
        self,
        session: Any,
        caller: CallerContext,
        item_id: Union[str, uuid.UUID],
        decision: str,  # 'APPROVED' or 'REJECTED'
        justification: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Adjudicates a quarantined (`PENDING`) knowledge item (`Section 12 / Section 26.4`).
        Steps:
          0. Assert active transaction boundary (`session.in_transaction()`).
          1. Validate caller identity & functional role (`STEWARD` / `ADMIN`).
          2. Lock target `KnowledgeItem` (`SELECT FOR UPDATE with populate_existing=True`).
          3. Enforce horizontal (`allowed_namespaces`) & vertical (`max_sensitivity_level`) clearances.
          4. Enforce Four-Eyes Principle (`caller.user_id != item.ingested_by_id`).
          5. Enforce legal state transitions (`status == PENDING`).
          6. Execute Blue-Green promotion or rejection (`RSK-05` with strict namespace demotion scoping).
          7. Insert immutable record into `governance_decisions` (`Section 11.5`).
          8. Invoke `AuditChainService.log_event` with `APPROVE` / `REJECT` (`RSK-04`).
        """
        # Step 0: Assert active transaction boundary (`Section 15 / Section 26.4`)
        if not hasattr(session, "in_transaction") or not session.in_transaction():
            raise GovernanceError(
                "Database session is closed or not inside an active transaction boundary (`session.begin()` required)."
            )

        if not isinstance(caller, CallerContext):
            raise GovernanceError("Caller identity must be an authenticated CallerContext object (`Section 26.1`).")

        # Step 1: Validate functional role (`Section 12`)
        if caller.functional_role not in ("STEWARD", "ADMIN"):
            raise StewardAuthorizationError(
                f"Adjudication access denied: caller '{caller.identity_key}' possesses role '{caller.functional_role}', "
                f"requiring 'STEWARD' or 'ADMIN' (`Section 12`)."
            )

        # Validate and sanitize input strings
        decision_upper = str(decision).strip().upper()
        if decision_upper not in ("APPROVED", "REJECTED"):
            raise GovernanceError(f"Invalid adjudication decision '{decision}'. Must be 'APPROVED' or 'REJECTED'.")

        clean_justification: Optional[str] = None
        if justification is not None:
            clean_justification = str(justification).replace("\x00", "").strip()
            if len(clean_justification) > 10_000:
                raise GovernanceError("Adjudication justification exceeds maximum permitted length (`10,000 characters`).")

        try:
            target_uuid = uuid.UUID(str(item_id)) if not isinstance(item_id, uuid.UUID) else item_id
        except (ValueError, TypeError) as err:
            raise DocumentNotFoundError(f"Invalid item_id UUID representation: '{item_id}'.") from err

        try:
            # Step 2: Lock target tuple with pessimistic FOR UPDATE (`RSK-01`)
            # execution_options(populate_existing=True) guarantees refreshing from locked row
            stmt = (
                select(KnowledgeItem)
                .where(KnowledgeItem.item_id == target_uuid)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            res = await session.execute(stmt)
            item: Optional[KnowledgeItem] = res.scalar_one_or_none()

            if item is None:
                raise DocumentNotFoundError(f"KnowledgeItem '{target_uuid}' not found inside database table.")

            # Step 3: Enforce horizontal & vertical clearances (`Section 11.1 / Section 11.3`)
            if item.domain_namespace not in caller.allowed_namespaces:
                raise StewardAuthorizationError(
                    f"Adjudication access denied: caller '{caller.identity_key}' lacks horizontal clearance for "
                    f"namespace '{item.domain_namespace}' (`Section 26.1`)."
                )

            if item.sensitivity_level > caller.max_sensitivity_level:
                raise StewardAuthorizationError(
                    f"Adjudication access denied: caller '{caller.identity_key}' (max level {caller.max_sensitivity_level}) "
                    f"lacks clearance for document sensitivity level {item.sensitivity_level} (`Section 11.3`)."
                )

            # Step 4: Enforce Four-Eyes Principle (`Brief P10 BR-05 / Section 12`)
            if caller.user_id == item.ingested_by_id:
                raise FourEyesPrincipleViolationError(
                    f"Four-Eyes Principle Violation (`BR-05`): Steward '{caller.identity_key}' ({caller.user_id}) "
                    f"cannot adjudicate an item they ingested themselves."
                )

            # Step 5: Enforce legal state transitions (`Section 12 / RSK-05`)
            if item.status == KnowledgeStatusEnum.APPROVED:
                raise DocumentAlreadyApprovedError(
                    f"KnowledgeItem '{target_uuid}' is already APPROVED (`409 Conflict`)."
                )
            elif item.status == KnowledgeStatusEnum.REJECTED:
                raise DocumentAlreadyRejectedError(
                    f"KnowledgeItem '{target_uuid}' is already REJECTED (`409 Conflict`)."
                )
            elif item.status != KnowledgeStatusEnum.PENDING:
                raise DocumentNotPendingError(
                    f"KnowledgeItem '{target_uuid}' is in non-pending status '{item.status}' and cannot be adjudicated (`409 Conflict`)."
                )

            # Step 6: Execute Blue-Green promotion or rejection (`RSK-05`)
            if decision_upper == "APPROVED":
                # If document has canonical URI, demote previous active Blue versions inside exact namespace
                if item.source_uri is not None:
                    await session.execute(
                        update(KnowledgeItem)
                        .where(
                            KnowledgeItem.source_uri == item.source_uri,
                            KnowledgeItem.domain_namespace == item.domain_namespace,  # Strict defense-in-depth scoping
                            KnowledgeItem.item_id != item.item_id,
                            KnowledgeItem.is_latest_approved == True,
                        )
                        .values(is_latest_approved=False)
                    )
                item.status = KnowledgeStatusEnum.APPROVED
                item.is_latest_approved = True
            else:  # REJECTED
                item.status = KnowledgeStatusEnum.REJECTED
                item.is_latest_approved = False

            # Step 7: Insert immutable record into `governance_decisions` (`Section 11.5`)
            decision_row = GovernanceDecision(
                decision_id=uuid.uuid4(),
                item_id=item.item_id,
                steward_id=caller.user_id,
                decision_type=decision_upper,
                justification=clean_justification,
                decided_at=datetime.datetime.now(datetime.timezone.utc),
            )
            session.add(decision_row)
            await session.flush()

            # Step 8: Invoke AuditChainService.log_event (`RSK-04`)
            audit_payload: Dict[str, Any] = {
                "decision_id": str(decision_row.decision_id),
                "item_id": str(item.item_id),
                "steward_id": str(caller.user_id),
                "steward_identity_key": caller.identity_key,
                "decision_type": decision_upper,
                "justification": clean_justification or "",
                "previous_status": "PENDING",
                "new_status": decision_upper,
                "version": item.version,
                "domain_namespace": item.domain_namespace,
                "sensitivity_level": item.sensitivity_level,
                "decided_at": decision_row.decided_at.isoformat(),
            }

            audit_event_payload = AuditEventPayload(
                action_type=AuditActionEnum.APPROVE if decision_upper == "APPROVED" else AuditActionEnum.REJECT,
                actor_id=caller.user_id,
                target_id=item.item_id,
                details=audit_payload,
            )

            await self.audit_service.log_event(
                session=session,
                payload=audit_event_payload,
            )

            return {
                "decision_id": str(decision_row.decision_id),
                "item_id": str(item.item_id),
                "steward_id": str(decision_row.steward_id),
                "decision_type": decision_upper,
                "justification": clean_justification,
                "decided_at": decision_row.decided_at.isoformat(),
                "item_status": decision_upper,
                "is_latest_approved": item.is_latest_approved,
            }

        except (
            DocumentNotFoundError,
            StewardAuthorizationError,
            FourEyesPrincipleViolationError,
            DocumentNotPendingError,
            DocumentAlreadyApprovedError,
            DocumentAlreadyRejectedError,
        ):
            # Re-raise clean domain errors immediately
            raise
        except sqlalchemy.exc.IntegrityError as err:
            sqlstate = getattr(err.orig, "sqlstate", None) if hasattr(err, "orig") else None
            constraint = getattr(getattr(err.orig, "diag", None), "constraint_name", "") if hasattr(err, "orig") else ""
            constraint_str = (constraint or str(err)).lower()

            if sqlstate == "23514" or "four_eyes" in constraint_str:
                if "four_eyes" in constraint_str or (sqlstate == "23514" and "steward" in str(err).lower()):
                    raise FourEyesPrincipleViolationError(
                        f"Four-Eyes Principle Violation (`BR-05 / trg_governance_four_eyes`): {err}"
                    ) from err
                raise GovernanceError(f"Database check constraint violation (`SQLSTATE {sqlstate}`): {err}") from err
            elif sqlstate == "23505" or "unique" in constraint_str:
                if "uidx_latest_approved_source" in constraint_str:
                    raise GovernanceError("Canonical source_uri collision during Blue-Green promotion (`RSK-05`).") from err
                raise GovernanceError(f"Database unique constraint violation (`SQLSTATE {sqlstate}`): {err}") from err
            raise GovernanceError(f"Database integrity error during adjudication: {err}") from err
        except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError) as err:
            sqlstate = getattr(err.orig, "sqlstate", None) if hasattr(err, "orig") else None
            if sqlstate in ("57014", "55P03"):
                raise GovernanceError(
                    f"Database lock contention or query timeout during adjudication (`SQLSTATE {sqlstate}`): {err}"
                ) from err
            raise GovernanceError(f"Database operational anomaly during adjudication (`SQLSTATE {sqlstate}`): {err}") from err
        except Exception as err:
            if isinstance(err, GovernanceError):
                raise
            raise GovernanceError(f"Unexpected internal anomaly during adjudication: {err}") from err

    async def list_pending_items(
        self,
        session: Any,
        caller: CallerContext,
        domain_namespace: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves quarantined (`PENDING`) items within caller clearances (`Section 26.4`).
        Requires active transaction boundary (`session.in_transaction()`).
        """
        if not hasattr(session, "in_transaction") or not session.in_transaction():
            raise GovernanceError(
                "Database session is closed or not inside an active transaction boundary (`session.begin()` required)."
            )

        if not isinstance(caller, CallerContext):
            raise GovernanceError("Caller identity must be an authenticated CallerContext object (`Section 26.1`).")

        if caller.functional_role not in ("STEWARD", "ADMIN"):
            raise StewardAuthorizationError(
                f"Access denied: caller '{caller.identity_key}' possesses role '{caller.functional_role}', "
                f"requiring 'STEWARD' or 'ADMIN' (`Section 12`)."
            )

        if domain_namespace is not None:
            if domain_namespace not in caller.allowed_namespaces:
                raise StewardAuthorizationError(
                    f"Access denied: caller '{caller.identity_key}' lacks horizontal clearance for namespace '{domain_namespace}' (`Section 26.1`)."
                )
            target_namespaces = [domain_namespace]
        else:
            target_namespaces = list(caller.allowed_namespaces)

        if not target_namespaces:
            return []

        try:
            stmt = (
                select(KnowledgeItem)
                .where(
                    KnowledgeItem.status == KnowledgeStatusEnum.PENDING,
                    KnowledgeItem.domain_namespace.in_(target_namespaces),
                    KnowledgeItem.sensitivity_level <= caller.max_sensitivity_level,
                )
                .order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.item_id.asc())
                .limit(max(1, min(limit, 500)))
                .offset(max(0, offset))
            )
            res = await session.execute(stmt)
            items = res.scalars().all()

            results: List[Dict[str, Any]] = []
            for item in items:
                results.append({
                    "item_id": str(item.item_id),
                    "title": item.title,
                    "body": item.body,
                    "source_uri": item.source_uri,
                    "domain_namespace": item.domain_namespace,
                    "sensitivity_label": item.sensitivity_label.value if hasattr(item.sensitivity_label, "value") else str(item.sensitivity_label),
                    "sensitivity_level": item.sensitivity_level,
                    "status": item.status.value if hasattr(item.status, "value") else str(item.status),
                    "version": item.version,
                    "is_latest_approved": item.is_latest_approved,
                    "ingested_by_id": str(item.ingested_by_id),
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                })
            return results
        except sqlalchemy.exc.SQLAlchemyError as err:
            raise GovernanceError(f"Database query failure during list_pending_items: {err}") from err


__all__ = ["GovernanceService"]
