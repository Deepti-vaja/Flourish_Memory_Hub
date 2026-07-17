"""
Audit Verification Response DTO (`Stage 2 Engine / Section 12`).
Encapsulates cryptographic HMAC-SHA256 ledger integrity verification results.
"""
from typing import Optional
from pydantic import Field
from app.schemas.common import BaseDTOSchema


class VerifyLedgerResponse(BaseDTOSchema):
    """
    Response DTO confirming whether the cryptographic audit ledger is uncompromised.
    """
    compromised: bool = Field(..., description="True if any HMAC-SHA256 chain breaks or tampering is detected")
    verified_records: int = Field(..., description="Number of sequential records scanned and certified")
    last_verified_seal: Optional[str] = Field(default=None, description="HMAC-SHA256 seal of the most recent verified event")
    message: str = Field(..., description="Forensic summary report")
