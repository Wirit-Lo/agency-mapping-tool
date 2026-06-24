"""CLI: generate WebObject files from Excel or Google Sheets.

Examples:
    # from local xlsx
    python -m app.cli --source tests/fixtures/source \
        --config "tests/fixtures/THP Agency Data Mapping.json" --out ./out

    # from Google Sheets
    python -m app.cli --google-sheets --service-account sa.json \
        --config "tests/fixtures/THP Agency Data Mapping.json" --out ./out
"""
import argparse

from app.runner import generate


def main() -> None:
    p = argparse.ArgumentParser(description="Generate THP Agency WebObject files")
    p.add_argument("--source", default="tests/fixtures/source",
                   help="Directory of source .xlsx (ignored for --google-sheets "
                        "except for config-referenced filenames)")
    p.add_argument("--config", required=True, help="Path to mapping config JSON")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--google-sheets", action="store_true",
                   help="Read from Google Sheets instead of local xlsx")
    p.add_argument("--service-account", help="Service account JSON (for --google-sheets)")
    args = p.parse_args()

    outputs = generate(
        source_dir=args.source,
        config_path=args.config,
        out_dir=args.out,
        use_google_sheets=args.google_sheets,
        service_account_file=args.service_account,
    )
    for name, content in outputs.items():
        print(f"{name}: {content.count(chr(10))} lines")
    print(f"Wrote {len(outputs)} files to {args.out}")


if __name__ == "__main__":
    main()
