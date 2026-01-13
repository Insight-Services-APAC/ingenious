"""Pre-built criteria templates."""

from datetime import datetime

from soca.models import CriteriaSet, Criterion


def get_templates() -> list[CriteriaSet]:
    """Get pre-built criteria templates."""
    now = datetime.utcnow().isoformat() + "Z"
    return [
        CriteriaSet(
            id="template-grant",
            name="Grant Proposal Evaluation",
            description="Standard criteria for evaluating grant proposals",
            created_at=now,
            criteria=[
                Criterion(
                    id="c1",
                    name="Scientific Merit",
                    description="Quality and significance of the scientific approach",
                    weight=25,
                    max_score=5,
                ),
                Criterion(
                    id="c2",
                    name="Innovation",
                    description="Novelty and creativity of the proposed work",
                    weight=20,
                    max_score=5,
                ),
                Criterion(
                    id="c3",
                    name="Methodology",
                    description="Soundness of the research methodology",
                    weight=20,
                    max_score=5,
                ),
                Criterion(
                    id="c4",
                    name="Team Qualifications",
                    description="Experience and expertise of the research team",
                    weight=15,
                    max_score=5,
                ),
                Criterion(
                    id="c5",
                    name="Budget Justification",
                    description="Appropriateness of budget to proposed work",
                    weight=10,
                    max_score=5,
                ),
                Criterion(
                    id="c6",
                    name="Broader Impact",
                    description="Potential societal and scientific impact",
                    weight=10,
                    max_score=5,
                ),
            ],
        ),
        CriteriaSet(
            id="template-rfp",
            name="RFP Response Evaluation",
            description="Criteria for evaluating vendor RFP responses",
            created_at=now,
            criteria=[
                Criterion(
                    id="c1",
                    name="Technical Approach",
                    description="Quality of proposed technical solution",
                    weight=30,
                    max_score=5,
                ),
                Criterion(
                    id="c2",
                    name="Relevant Experience",
                    description="Past performance on similar projects",
                    weight=25,
                    max_score=5,
                ),
                Criterion(
                    id="c3",
                    name="Cost Effectiveness",
                    description="Value for money and budget alignment",
                    weight=20,
                    max_score=5,
                ),
                Criterion(
                    id="c4",
                    name="Timeline Feasibility",
                    description="Realistic and achievable schedule",
                    weight=15,
                    max_score=5,
                ),
                Criterion(
                    id="c5",
                    name="Risk Mitigation",
                    description="Identification and handling of risks",
                    weight=10,
                    max_score=5,
                ),
            ],
        ),
        CriteriaSet(
            id="template-code",
            name="Code Review Criteria",
            description="Criteria for evaluating code submissions",
            created_at=now,
            criteria=[
                Criterion(
                    id="c1",
                    name="Correctness",
                    description="Code produces correct results",
                    weight=30,
                    max_score=5,
                ),
                Criterion(
                    id="c2",
                    name="Code Quality",
                    description="Clean, readable, and maintainable code",
                    weight=25,
                    max_score=5,
                ),
                Criterion(
                    id="c3",
                    name="Performance",
                    description="Efficiency and optimization",
                    weight=20,
                    max_score=5,
                ),
                Criterion(
                    id="c4",
                    name="Documentation",
                    description="Quality of comments and documentation",
                    weight=15,
                    max_score=5,
                ),
                Criterion(
                    id="c5",
                    name="Test Coverage",
                    description="Presence and quality of tests",
                    weight=10,
                    max_score=5,
                ),
            ],
        ),
        CriteriaSet(
            id="template-paper",
            name="Academic Paper Review",
            description="Criteria for reviewing academic papers",
            created_at=now,
            criteria=[
                Criterion(
                    id="c1",
                    name="Originality",
                    description="Novel contribution to the field",
                    weight=25,
                    max_score=5,
                ),
                Criterion(
                    id="c2",
                    name="Significance",
                    description="Importance and impact of the work",
                    weight=20,
                    max_score=5,
                ),
                Criterion(
                    id="c3",
                    name="Technical Quality",
                    description="Soundness of methodology and analysis",
                    weight=25,
                    max_score=5,
                ),
                Criterion(
                    id="c4",
                    name="Clarity",
                    description="Quality of writing and presentation",
                    weight=15,
                    max_score=5,
                ),
                Criterion(
                    id="c5",
                    name="References",
                    description="Appropriate citation of related work",
                    weight=15,
                    max_score=5,
                ),
            ],
        ),
    ]
