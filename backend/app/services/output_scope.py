from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Output
from app.services.domain.compliance.constants import PRIMARY_DELIVERABLE_TYPES

_PRIMARY_OUTPUT_ORDER = {output_type: index for index, output_type in enumerate(PRIMARY_DELIVERABLE_TYPES)}


def primary_outputs(db: Session, **filters: object) -> list[Output]:
    outputs = (
        db.query(Output)
        .filter_by(**filters)
        .filter(Output.output_type.in_(PRIMARY_DELIVERABLE_TYPES))
        .order_by(Output.created_at.asc(), Output.id.asc())
        .all()
    )
    return sorted(
        outputs,
        key=lambda output: (
            _PRIMARY_OUTPUT_ORDER.get(output.output_type, len(_PRIMARY_OUTPUT_ORDER)),
            output.created_at,
            output.id,
        ),
    )


def primary_output_count(db: Session, **filters: object) -> int:
    return (
        db.query(Output)
        .filter_by(**filters)
        .filter(Output.output_type.in_(PRIMARY_DELIVERABLE_TYPES))
        .count()
    )
