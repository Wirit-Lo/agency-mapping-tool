from app.models.raw import ServiceProviderRawData
from app.pipeline.barcode import _get_prompt_from_provider
from app.sheets import loaders


def _with_grid(grid):
    loaders.set_grid_provider(lambda path, idx=0: grid)


def teardown_function(_):
    loaders.set_grid_provider(loaders._excel_grid)


def test_prompt_column_read_when_header_matches():
    _with_grid([
        ["ServiceId", "Type", "ProviderName", "WorkflowId", "Barcode required", "Barcode prompt", "Notes"],
        ["50961", "SBA", "", "", "0", "สแกนบาร์โค้ด (ถ้าไม่มี กดถัดไป)", "note"],
        ["50948", "SBA", "AgencyProvider123_2c2p", "", "0", "", ""],
    ])
    providers = loaders.load_service_providers("AgencyServiceProviders.xlsx")
    assert providers[0].BarcodePrompt == "สแกนบาร์โค้ด (ถ้าไม่มี กดถัดไป)"
    assert providers[1].BarcodePrompt == ""


def test_old_sheet_notes_column_is_not_used_as_prompt():
    _with_grid([
        ["ServiceId", "Type", "ProviderName", "WorkflowId", "Barcode required", "Notes"],
        ["50329", "SBA", "AgencyProvider50329TotalAmount", "", "0", "This will be used to compute"],
    ])
    providers = loaders.load_service_providers("AgencyServiceProviders.xlsx")
    assert providers[0].BarcodePrompt == ""


def test_prompt_falls_back_to_default():
    providers = [
        ServiceProviderRawData(ObjectId="50961", BarcodePrompt="สแกนบาร์โค้ด (ถ้าไม่มี กดถัดไป)"),
        ServiceProviderRawData(ObjectId="50948"),
    ]
    assert _get_prompt_from_provider(50961, providers, "Scan Barcode") == "สแกนบาร์โค้ด (ถ้าไม่มี กดถัดไป)"
    assert _get_prompt_from_provider(50948, providers, "Scan Barcode") == "Scan Barcode"
    assert _get_prompt_from_provider(99999, providers, "Scan Barcode") == "Scan Barcode"
