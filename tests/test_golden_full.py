"""Full-pipeline golden test — assert all 8 output files are byte-identical
to the original C# tool's output.

This is the regression guard: any change that alters output fidelity fails here.
Runs the real loaders + 18-step pipeline + barcode state machine against the
snapshotted source workbooks, and compares bytes (including UTF-8 BOM and LF).
"""
import os

import pytest

from app.runner import generate

OUTPUT_FILES = [
    "RA_AgencyScheme.txt",
    "RA_AgencyFieldData.txt",
    "RA_AgencyPostingData.txt",
    "RA_AgencyDerivedData.txt",
    "RA_AgencyValidationData.txt",
    "RA_AgencyLookup.txt",
    "RA_AgencyBarcodeDetails.txt",
    "RA_AgencyBarcodeParsingData.txt",
]

SOURCE_DIR = "tests/fixtures/source"
CONFIG = "tests/fixtures/THP Agency Data Mapping.json"
GOLDEN_DIR = "tests/golden"


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("out")
    generate(SOURCE_DIR, CONFIG, str(out_dir))
    return out_dir


@pytest.mark.parametrize("filename", OUTPUT_FILES)
def test_output_byte_identical(outputs, filename):
    produced = (outputs / filename).read_bytes()
    golden = open(os.path.join(GOLDEN_DIR, filename), "rb").read()
    assert produced == golden, f"{filename} differs from golden output"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
