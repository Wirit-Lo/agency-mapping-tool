"""Apply small, version-controlled exceptions to enriched agency data."""
from __future__ import annotations

import json
import os


_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "overrides",
    "agency_scheme.json",
)

_ALLOWED_FIELDS = {
    "WorkflowId",
    "PrimaryBarcode",
    "SchemeIdStart",
    "SchemeIdString",
    "EmitActualCopy",
    "AccountCode",
}

# Not an AgencyRawData attribute: redirects the main (Amount) posting to another
# account, e.g. a second barcode prefix whose money belongs to an existing service.
_POSTING_ACCOUNT = "PostingAccount"


def apply_agency_scheme_overrides(agency_data, path: str = _DEFAULT_PATH) -> list[str]:
    """Apply overrides by service id and return the ids that were changed."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        overrides = json.load(fh)
    if not isinstance(overrides, dict):
        raise ValueError("Agency scheme overrides must be a JSON object keyed by service id.")

    by_id = {agency.ObjectId: agency for agency in agency_data}
    applied: list[str] = []
    for service_id, values in overrides.items():
        if not isinstance(values, dict):
            raise ValueError(f"Agency scheme override {service_id} must be an object.")
        unknown = set(values) - _ALLOWED_FIELDS - {_POSTING_ACCOUNT}
        if unknown:
            raise ValueError(f"Unsupported override fields for {service_id}: {sorted(unknown)}")
        # A source snapshot may legitimately contain only a subset of services.
        if service_id not in by_id:
            continue
        agency = by_id[service_id]
        for field, value in values.items():
            if field == _POSTING_ACCOUNT:
                for posting in agency.PostingData:
                    if posting.Attribute == "Amount":
                        posting.Account = value
            else:
                setattr(agency, field, value)
        applied.append(service_id)
    return applied
