import json

import pytest

from app.models.raw import AgencyRawData
from app.overrides import apply_agency_scheme_overrides
from app.serialize.webobjects import serialize_agency_scheme


def test_override_replaces_values_and_emits_actual(tmp_path):
    agency = AgencyRawData(
        ObjectId="30078", SchemeName="30078", SchemeDescription="DPost",
        AccountCode="30078", AllowInvokeList=1, PrimaryBarcode="Barcode_30078",
        TxnType="AgencySaleOnline", ExtractId="AgencyPayment", AllowInvokeButton=1,
    )
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({"30078": {
        "WorkflowId": "THP.Counters.Agency.CODBlue30078",
        "EmitActualCopy": True,
    }}), encoding="utf-8")

    assert apply_agency_scheme_overrides([agency], str(path)) == ["30078"]
    lines = serialize_agency_scheme(agency)
    assert len(lines) == 2
    assert "<WorkflowId:THP.Counters.Agency.CODBlue30078>" in lines[0]
    assert lines[0].index("<WorkflowId:") < lines[0].index("<StartDate:") if "<StartDate:" in lines[0] else True
    assert "/30078_Actual>" in lines[1]
    assert "<AllowInvokeList:0>" in lines[1]
    assert "<WorkflowId:" not in lines[1]


def test_unknown_override_field_fails(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text('{"30078": {"TypoField": "x"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported override fields"):
        apply_agency_scheme_overrides([AgencyRawData(ObjectId="30078")], str(path))
