"""
Flourish Governed Memory Hub - Core Domain Enumerations & Constants
Matches exactly with Blueprint Section 11 SQL ENUM types:
- knowledge_status_enum
- sensitivity_label_enum
- audit_action_enum
"""

from enum import Enum, unique


@unique
class KnowledgeStatusEnum(str, Enum):
    """
    Status values for organizational knowledge items.
    Mandated by Blueprint Section 11.0 (L1005) & Brief P6/P10.
    """
    PENDING = "PENDING"      # Initial quarantine state; zero search visibility
    APPROVED = "APPROVED"    # Cleared by domain steward; retrievable via role-scoped search
    REJECTED = "REJECTED"    # Adjudicated as invalid or sensitive; permanently blocked
    ARCHIVED = "ARCHIVED"    # Blue-Green historical version (EDR-07) replaced by version N+1


@unique
class SensitivityLabelEnum(str, Enum):
    """
    Sensitivity classification labels.
    Mandated by Blueprint Section 11.0 (L1006) & Brief P12.
    """
    PUBLIC = "PUBLIC"              # Level 1: Open organizational knowledge
    INTERNAL = "INTERNAL"          # Level 2: Standard employee access
    CONFIDENTIAL = "CONFIDENTIAL"  # Level 3: Department-restricted access
    RESTRICTED = "RESTRICTED"      # Level 4: Highly restricted / executive access

    @property
    def level_value(self) -> int:
        """Returns numeric sensitivity level (1-4) for SQL predicate inequality comparisons."""
        mapping = {
            SensitivityLabelEnum.PUBLIC: 1,
            SensitivityLabelEnum.INTERNAL: 2,
            SensitivityLabelEnum.CONFIDENTIAL: 3,
            SensitivityLabelEnum.RESTRICTED: 4,
        }
        return mapping[self]


@unique
class AuditActionEnum(str, Enum):
    """
    Categorization of actions recorded in the tamper-evident audit ledger.
    Mandated by Blueprint Section 11.0 (L1007) & Brief P13.
    """
    INGEST = "INGEST"                      # New knowledge item submitted to quarantine
    APPROVE = "APPROVE"                    # Steward approved pending item
    REJECT = "REJECT"                      # Steward rejected pending item
    RETRIEVE_SUCCESS = "RETRIEVE_SUCCESS"  # Caller successfully retrieved knowledge
    RETRIEVE_DENIED = "RETRIEVE_DENIED"    # Caller blocked from retrieving knowledge
