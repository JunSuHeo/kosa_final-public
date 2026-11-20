"""Compare the stored Studio contracts to the API and Pydantic models."""

import argparse
import json
from pathlib import Path
import sys

# This script runs with PRJ/backend's locked Python environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app
from app.role_reviews import AgentResult, ReviewError, evidence_items, validate_evidence
from app.schema import Snapshot, validate_snapshot
from pydantic import ValidationError

SPEC = Path(__file__).resolve().parents[1] / "docs/spec"


def verify():
    errors = []
    generated = {
        "openapi.json": app.openapi(),
        "snapshot.schema.json": Snapshot.model_json_schema(),
        "role-review.schema.json": AgentResult.model_json_schema(),
    }
    for name, expected in generated.items():
        if json.loads((SPEC / name).read_text()) != expected:
            errors.append(f"{name} differs from the generated API/model contract.")
    snapshot = Snapshot.model_validate_json((SPEC / "example-snapshot.json").read_text()).model_dump()
    review = AgentResult.model_validate_json((SPEC / "example-role-review.json").read_text()).model_dump()
    if any(issue["severity"] == "blocking" for issue in validate_snapshot(snapshot)):
        errors.append("Example snapshot has blocking validation errors.")
    validate_evidence(review, evidence_items(snapshot))
    return errors


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        errors = verify()
    except (OSError, ValueError, ValidationError, ReviewError) as exc:
        print(f"Contract check could not validate the stored files: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print("3 generated contracts and 2 examples verified.")
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
