from __future__ import annotations

import argparse
import io
import re
import zipfile
from pathlib import Path


FORBIDDEN_SUFFIXES = (
    "/.env.local",
    "/firmware/secrets.h",
    "/thingsboard/.env.local",
)

REQUIRED_SUFFIXES = (
    "/README.md",
    "/firmware/sketch.ino",
    "/thingsboard/setup.py",
    "/tests/results/metrics.json",
    "/tests/results/stability-metrics.json",
    "/report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.docx",
    "/report/output/Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf",
    "/slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pptx",
    "/slides/output/Thuyet_trinh_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf",
)


def local_secret_values(project: Path) -> set[str]:
    values: set[str] = set()
    env_path = project / ".env.local"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if re.search(r"TOKEN|API_KEY|PASSWORD|SECRET", key, re.I):
                value = value.strip().strip('"\'')
                if len(value) >= 6 and not value.startswith("<"):
                    values.add(value)

    secrets_header = project / "firmware" / "secrets.h"
    if secrets_header.exists():
        for raw in secrets_header.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not re.search(r"TOKEN|API_KEY|PASSWORD|SECRET", raw, re.I):
                continue
            match = re.search(r'["\']([^"\']{6,})["\']', raw)
            if match and not match.group(1).startswith("<"):
                values.add(match.group(1))
    return values


def secret_hits(data: bytes, secrets: set[str]) -> bool:
    for secret in secrets:
        if secret.encode("utf-8") in data or secret.encode("utf-16-le") in data:
            return True
    return False


def nested_archive_has_secret(data: bytes, secrets: set[str]) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as nested:
            for name in nested.namelist():
                if name.endswith("/"):
                    continue
                if secret_hits(nested.read(name), secrets):
                    return True
    except zipfile.BadZipFile:
        return False
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the clean submission ZIP.")
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()

    package = args.zip_path.resolve()
    project = args.project.resolve()
    errors: list[str] = []
    secrets = local_secret_values(project)

    with zipfile.ZipFile(package) as archive:
        bad_crc = archive.testzip()
        if bad_crc:
            errors.append(f"CRC error: {bad_crc}")

        names = archive.namelist()
        for name in names:
            normalized = "/" + name.replace("\\", "/").lstrip("/")
            if normalized.endswith(FORBIDDEN_SUFFIXES):
                errors.append(f"Forbidden file: {name}")
            if re.search(r"(^|/)(\.pio|\.runtime|\.rendered|rendered|__pycache__|node_modules)(/|$)", normalized):
                errors.append(f"Runtime/build artifact: {name}")

        for required in REQUIRED_SUFFIXES:
            if not any(("/" + name.lstrip("/")).endswith(required) for name in names):
                errors.append(f"Missing required file: {required}")

        for name in names:
            if name.endswith("/"):
                continue
            data = archive.read(name)
            if secret_hits(data, secrets):
                errors.append(f"Local secret value found in: {name}")
            if Path(name).suffix.lower() in {".docx", ".pptx", ".xlsx", ".zip"}:
                if nested_archive_has_secret(data, secrets):
                    errors.append(f"Local secret value found inside archive: {name}")

    if errors:
        print("FAIL")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1

    print("PASS")
    print(f"Entries: {len(names)}")
    print(f"Local secret values checked: {len(secrets)}")
    print("Forbidden credential files: absent")
    print("Required report, slides, source and test results: present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
