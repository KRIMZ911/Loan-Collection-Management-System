"""
app/services/audit_log.py
==========================
Phase J.1 — Auto-write audit log entries for tracked models.

Uses SQLAlchemy event listeners on User, LoanProduct, AnnualGoal to capture
CREATE/UPDATE/DELETE operations and write them to the AuditLog table.

Special handling:
    - AnnualGoal soft delete (deleted_at set) → logged as DELETE
    - User deactivation (is_active True→False) → logged as DEACTIVATE
    - Sensitive fields (password_hash) excluded from audit values
"""

import json
import enum
from datetime import datetime, date, timezone
from decimal import Decimal

from flask import g, has_request_context, request
from sqlalchemy import event
from sqlalchemy.orm.attributes import get_history

from app import db
from app.models import AuditLog, User, LoanProduct, AnnualGoal


# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════
# Global kill-switch for audit logging.
# When True, all event listeners become no-ops.
# Use to suppress audit during seeding, migrations, bulk imports.
_AUDIT_DISABLED = False


def disable_audit():
    """Turn audit logging off. Used by seed.py, migrations, bulk imports."""
    global _AUDIT_DISABLED
    _AUDIT_DISABLED = True


def enable_audit():
    """Turn audit logging back on."""
    global _AUDIT_DISABLED
    _AUDIT_DISABLED = False

# Models we audit. Add new model classes here to start tracking them.
AUDITED_MODELS = [User, LoanProduct, AnnualGoal]

# Fields to NEVER include in audit values (sensitive data)
EXCLUDED_FIELDS = {
    "password_hash",
    "created_at",   # noise — every row has it
    "updated_at",   # noise — every row has it
}


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _get_current_user_id():
    """Return user_id from flask.g if in request context, else None."""
    if not has_request_context():
        return None
    user = getattr(g, "user", None)
    return user.id if user else None


def _get_ip_address():
    """Return request IP if in request context, else None."""
    if not has_request_context():
        return None
    return request.remote_addr


def _json_default(obj):
    """JSON serializer for datetime, Decimal, Enum, etc."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, enum.Enum):
        return obj.value if hasattr(obj, "value") else str(obj)
    return str(obj)


def _serialize_model(obj):
    """Convert a SQLAlchemy model instance to a JSON-serializable dict."""
    result = {}
    for col in obj.__table__.columns:
        name = col.name
        if name in EXCLUDED_FIELDS:
            continue
        value = getattr(obj, name, None)
        result[name] = value
    return json.dumps(result, default=_json_default, ensure_ascii=False)


def _changed_fields(obj):
    """
    Return dict of {field: {"old": v1, "new": v2}} for fields that changed.
    Uses SQLAlchemy's get_history to compare before/after values.
    """
    changes = {"old": {}, "new": {}}
    for col in obj.__table__.columns:
        name = col.name
        if name in EXCLUDED_FIELDS:
            continue
        hist = get_history(obj, name)
        if hist.has_changes():
            old = hist.deleted[0] if hist.deleted else None
            new = hist.added[0] if hist.added else None
            changes["old"][name] = old
            changes["new"][name] = new
    return changes


def _serialize_changes(changes):
    """Serialize the changes dict to JSON strings (old, new)."""
    return (
        json.dumps(changes["old"], default=_json_default, ensure_ascii=False),
        json.dumps(changes["new"], default=_json_default, ensure_ascii=False),
    )


def _write_audit_entry(action, entity_type, entity_id, old_value, new_value):
    """Internal: create an AuditLog row in the current session."""
    entry = AuditLog(
        user_id=_get_current_user_id(),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=_get_ip_address(),
        timestamp=datetime.now(timezone.utc),
    )
    db.session.add(entry)


# ════════════════════════════════════════════════════════════════════════════
# EVENT LISTENERS
# ════════════════════════════════════════════════════════════════════════════

def _on_after_insert(mapper, connection, target):
    """Fires after a tracked row is INSERTed."""

    if _AUDIT_DISABLED:
        return

    _write_audit_entry(
        action="CREATE",
        entity_type=target.__tablename__,
        entity_id=target.id,
        old_value=None,
        new_value=_serialize_model(target),
    )


def _on_after_update(mapper, connection, target):
    """Fires after a tracked row is UPDATEd."""
    
    if _AUDIT_DISABLED:
        return 

    changes = _changed_fields(target)
    if not changes["new"]:
        return  # Nothing actually changed

    # Special: AnnualGoal soft delete (deleted_at goes None → datetime)
    if isinstance(target, AnnualGoal):
        if "deleted_at" in changes["new"] and changes["new"]["deleted_at"] is not None:
            _write_audit_entry(
                action="DELETE",
                entity_type=target.__tablename__,
                entity_id=target.id,
                old_value=_serialize_model(target),
                new_value=None,
            )
            return

    # Special: User deactivation (is_active goes True → False)
    if isinstance(target, User):
        if "is_active" in changes["new"] and changes["new"]["is_active"] is False:
            _write_audit_entry(
                action="DEACTIVATE",
                entity_type=target.__tablename__,
                entity_id=target.id,
                old_value=_serialize_model(target),
                new_value=None,
            )
            return

    # Special: LoanProduct retirement (is_active goes True → False)
    if isinstance(target, LoanProduct):
        if "is_active" in changes["new"] and changes["new"]["is_active"] is False:
            _write_audit_entry(
                action="RETIRE",
                entity_type=target.__tablename__,
                entity_id=target.id,
                old_value=_serialize_model(target),
                new_value=None,
            )
            return

    # Default UPDATE
    old_json, new_json = _serialize_changes(changes)
    _write_audit_entry(
        action="UPDATE",
        entity_type=target.__tablename__,
        entity_id=target.id,
        old_value=old_json,
        new_value=new_json,
    )


def _on_after_delete(mapper, connection, target):
    """Fires after a tracked row is hard-DELETEd."""
    
    if _AUDIT_DISABLED:
        return
    
    _write_audit_entry(
        action="HARD_DELETE",
        entity_type=target.__tablename__,
        entity_id=target.id,
        old_value=_serialize_model(target),
        new_value=None,
    )


# ════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ════════════════════════════════════════════════════════════════════════════

def register_audit_listeners():
    """
    Wire up event listeners for all AUDITED_MODELS.
    Call this once at app creation time (from app/__init__.py).
    """
    for model_cls in AUDITED_MODELS:
        event.listen(model_cls, "after_insert", _on_after_insert)
        event.listen(model_cls, "after_update", _on_after_update)
        event.listen(model_cls, "after_delete", _on_after_delete)