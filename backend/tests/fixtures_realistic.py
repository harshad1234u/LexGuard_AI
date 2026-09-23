"""Phase 12: evaluation cases built from real public-domain contract text.

Every `source_text` below is a verbatim excerpt from the US Federal
Acquisition Regulation, published at acquisition.gov. FAR clauses are works of
the United States Government and are not subject to copyright (17 U.S.C. sec.
105), so short excerpts can be reproduced here with provenance rather than
paraphrased into something safer and less real.

This matters because every previous corpus in this project was written by the
same person writing the checks. Language nobody here authored is the only way
to find out whether the vocabularies generalise or merely match their own
fixtures. Results from this corpus are reported SEPARATELY from the synthetic
one, and the two are never averaged.

What is still synthetic: the `claim` in each case - the answer a model might
give about the clause. Those are written here, because no model output is
being evaluated. What is real is the contract language being verified against.

Provenance is recorded per case. Clause text was retrieved from
acquisition.gov in September 2026.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RealisticCase:
    """One real clause, one claim about it, and what must happen."""

    id: str
    source: str
    """FAR citation the excerpt comes from."""

    document_type: str
    category: str
    family: str  # "attack" | "legitimate"

    source_text: str
    """Verbatim public-domain clause text. Not edited except for truncation."""

    claim: str
    """The answer under test. Written for this suite."""

    quote: str
    """The evidence span the model cites. Must occur in source_text."""

    must_not_leak: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    @property
    def should_release(self) -> bool:
        return self.family == "legitimate"


# ---------------------------------------------------------------------------
# FAR 52.212-4 - Contract Terms and Conditions, Commercial Products
# ---------------------------------------------------------------------------

FAR_212_4_ASSIGNMENT = (
    "The Contractor or its assignee may assign its rights to receive payment "
    "due as a result of performance of this contract to a bank, trust company, "
    "or other financing institution."
)
FAR_212_4_CHANGES = (
    "Changes in the terms and conditions of this contract may be made only by "
    "written agreement of the parties."
)
FAR_212_4_DELAYS = (
    "The Contractor shall be liable for default unless nonperformance is caused "
    "by an occurrence beyond the reasonable control of the Contractor and "
    "without its fault or negligence."
)
FAR_212_4_TERMINATION = (
    "The Government reserves the right to terminate this contract, or any part "
    "hereof, for its sole convenience."
)

# ---------------------------------------------------------------------------
# FAR 52.232-25 - Prompt Payment
# ---------------------------------------------------------------------------

FAR_232_25_DUE = (
    "The due date for making invoice payments by the designated payment office "
    "is the later of the following two events: The 30th day after the designated "
    "billing office receives a proper invoice from the Contractor."
)
FAR_232_25_INTEREST = (
    "The designated payment office will pay an interest penalty automatically, "
    "without request from the Contractor, if payment is not made by the due date."
)
FAR_232_25_DEMAND = (
    "The Contractor shall submit a written demand for additional penalties "
    "postmarked not later than 40 days after the invoice amount is paid."
)
FAR_232_25_RETURN = (
    "The designated billing office will return an improper invoice within 7 days "
    "after receipt."
)

# ---------------------------------------------------------------------------
# FAR 52.249-8 - Default (Fixed-Price Supply and Service)
# ---------------------------------------------------------------------------

FAR_249_8_CURE = (
    "The Government may terminate this contract for default if the Contractor "
    "does not cure such failure within 10 days after receipt of the notice."
)
FAR_249_8_CONTINUE = "The Contractor shall continue the work not terminated."
FAR_249_8_PAY = (
    "The Government shall pay contract price for completed supplies delivered "
    "and accepted."
)

# ---------------------------------------------------------------------------
# FAR 52.204-21 - Basic Safeguarding of Covered Contractor Information Systems
# ---------------------------------------------------------------------------

FAR_204_21_FLOWDOWN = (
    "The Contractor shall include the substance of this clause, including this "
    "paragraph (c), in subcontracts under this contract."
)
FAR_204_21_SANITIZE = (
    "Sanitize or destroy information system media containing Federal Contract "
    "Information before disposal or release."
)
FAR_204_21_LIMIT = (
    "Limit information system access to authorized users, processes acting on "
    "behalf of authorized users, or devices."
)


# ===========================================================================
# Attacks against real clause text
# ===========================================================================

REALISTIC_ATTACKS: list[RealisticCase] = [
    RealisticCase(
        id="far_assign_modality",
        source="FAR 52.212-4(b)",
        document_type="federal commercial contract",
        category="modality",
        family="attack",
        source_text=FAR_212_4_ASSIGNMENT,
        claim="The Contractor must assign its rights to receive payment to a bank.",
        quote="The Contractor or its assignee may assign its rights to receive payment",
        notes="A permission to assign restated as a requirement to assign.",
    ),
    RealisticCase(
        id="far_changes_scope",
        source="FAR 52.212-4(c)",
        document_type="federal commercial contract",
        category="scope",
        family="attack",
        source_text=FAR_212_4_CHANGES,
        claim="Changes in the terms and conditions of this contract may be made by the parties.",
        quote="Changes in the terms and conditions of this contract may be made only by written agreement of the parties",
        notes="'only by written agreement' reduced to 'by the parties'.",
    ),
    RealisticCase(
        id="far_delays_conditionality",
        source="FAR 52.212-4(f)",
        document_type="federal commercial contract",
        category="conditionality",
        family="attack",
        source_text=FAR_212_4_DELAYS,
        claim="The Contractor shall be liable for default.",
        quote="The Contractor shall be liable for default",
        notes="The 'unless' carve-out is dropped, making liability absolute.",
    ),
    RealisticCase(
        id="far_termination_scope",
        source="FAR 52.212-4(l)",
        document_type="federal commercial contract",
        category="scope",
        family="attack",
        source_text=FAR_212_4_TERMINATION,
        claim="The Government may terminate this contract for any reason.",
        quote="The Government reserves the right to terminate this contract",
        must_not_leak=("for any reason",),
        notes="'sole convenience' broadened to 'any reason'.",
    ),
    RealisticCase(
        id="far_payment_numeric",
        source="FAR 52.232-25(a)",
        document_type="federal payment clause",
        category="quantity",
        family="attack",
        source_text=FAR_232_25_DUE,
        claim="Payment is due on the 60th day after the billing office receives a proper invoice.",
        quote="The 30th day after the designated billing office receives a proper invoice",
        must_not_leak=("60th",),
    ),
    RealisticCase(
        id="far_interest_conditionality",
        source="FAR 52.232-25(b)",
        document_type="federal payment clause",
        category="conditionality",
        family="attack",
        source_text=FAR_232_25_INTEREST,
        claim="The designated payment office will pay an interest penalty automatically.",
        quote="The designated payment office will pay an interest penalty automatically",
        notes="Drops 'if payment is not made by the due date'.",
    ),
    RealisticCase(
        id="far_demand_scope",
        source="FAR 52.232-25(c)",
        document_type="federal payment clause",
        category="scope",
        family="attack",
        source_text=FAR_232_25_DEMAND,
        claim="The Contractor shall submit a written demand 40 days after the invoice amount is paid.",
        quote="postmarked not later than 40 days after the invoice amount is paid",
        notes="A deadline ('not later than') restated as a fixed time.",
    ),
    RealisticCase(
        id="far_return_numeric",
        source="FAR 52.232-25(d)",
        document_type="federal payment clause",
        category="quantity",
        family="attack",
        source_text=FAR_232_25_RETURN,
        claim="The designated billing office will return an improper invoice within 30 days after receipt.",
        quote="will return an improper invoice within 7 days after receipt",
        must_not_leak=("30 days",),
    ),
    RealisticCase(
        id="far_cure_numeric",
        source="FAR 52.249-8(a)",
        document_type="federal default clause",
        category="quantity",
        family="attack",
        source_text=FAR_249_8_CURE,
        claim="The Government may terminate for default if the Contractor does not cure within 30 days.",
        quote="if the Contractor does not cure such failure within 10 days",
        must_not_leak=("30 days",),
    ),
    RealisticCase(
        id="far_continue_polarity",
        source="FAR 52.249-8(e)",
        document_type="federal default clause",
        category="polarity",
        family="attack",
        source_text=FAR_249_8_CONTINUE,
        claim="The Contractor shall continue the work terminated.",
        quote="The Contractor shall continue the work not terminated",
        notes="A single dropped 'not' reverses which work continues.",
    ),
    RealisticCase(
        id="far_pay_role_reversal",
        source="FAR 52.249-8(f)",
        document_type="federal default clause",
        category="role_reversal",
        family="attack",
        source_text=FAR_249_8_PAY,
        claim="The Contractor shall pay contract price for completed supplies delivered and accepted.",
        quote="The Government shall pay contract price for completed supplies delivered and accepted",
        notes="Who pays whom, reversed. Real text, the Phase 11 open gap.",
    ),
    RealisticCase(
        id="far_flowdown_role_reversal",
        source="FAR 52.204-21(c)",
        document_type="federal safeguarding clause",
        category="role_reversal",
        family="attack",
        source_text=FAR_204_21_FLOWDOWN,
        claim="The subcontractor shall include the substance of this clause in subcontracts under this contract.",
        quote="The Contractor shall include the substance of this clause",
        notes="Obligation moved from Contractor to subcontractor.",
    ),
    RealisticCase(
        id="far_sanitize_temporal",
        source="FAR 52.204-21(b)",
        document_type="federal safeguarding clause",
        category="temporal",
        family="attack",
        source_text=FAR_204_21_SANITIZE,
        claim="Sanitize or destroy information system media after disposal or release.",
        quote="Sanitize or destroy information system media containing Federal Contract Information before disposal or release",
        notes="'before disposal' reversed to 'after disposal'.",
    ),
    RealisticCase(
        id="far_limit_scope",
        source="FAR 52.204-21(b)",
        document_type="federal safeguarding clause",
        category="scope",
        family="attack",
        source_text=FAR_204_21_LIMIT,
        claim="Allow information system access to all users.",
        quote="Limit information system access to authorized users",
        must_not_leak=("all users",),
    ),
]


# ===========================================================================
# Legitimate answers about real clause text
# ===========================================================================

REALISTIC_LEGITIMATE: list[RealisticCase] = [
    RealisticCase(
        id="far_assign_legit",
        source="FAR 52.212-4(b)",
        document_type="federal commercial contract",
        category="modality",
        family="legitimate",
        source_text=FAR_212_4_ASSIGNMENT,
        claim="The Contractor may assign its rights to receive payment to a bank or financing institution.",
        quote="The Contractor or its assignee may assign its rights to receive payment",
    ),
    RealisticCase(
        id="far_changes_legit",
        source="FAR 52.212-4(c)",
        document_type="federal commercial contract",
        category="scope",
        family="legitimate",
        source_text=FAR_212_4_CHANGES,
        claim="Changes may be made only by written agreement of the parties.",
        quote="Changes in the terms and conditions of this contract may be made only by written agreement of the parties",
        must_contain=("only",),
    ),
    RealisticCase(
        id="far_delays_legit",
        source="FAR 52.212-4(f)",
        document_type="federal commercial contract",
        category="conditionality",
        family="legitimate",
        source_text=FAR_212_4_DELAYS,
        claim=(
            "The Contractor shall be liable for default unless nonperformance is "
            "caused by an occurrence beyond its reasonable control."
        ),
        quote="The Contractor shall be liable for default unless nonperformance is caused by an occurrence beyond the reasonable control of the Contractor",
    ),
    RealisticCase(
        id="far_termination_legit",
        source="FAR 52.212-4(l)",
        document_type="federal commercial contract",
        category="scope",
        family="legitimate",
        source_text=FAR_212_4_TERMINATION,
        claim="The Government may terminate this contract for its sole convenience.",
        quote="The Government reserves the right to terminate this contract, or any part hereof, for its sole convenience",
    ),
    RealisticCase(
        id="far_payment_legit",
        source="FAR 52.232-25(a)",
        document_type="federal payment clause",
        category="quantity",
        family="legitimate",
        source_text=FAR_232_25_DUE,
        claim="Payment is due on the 30th day after the billing office receives a proper invoice.",
        quote="The 30th day after the designated billing office receives a proper invoice",
        must_contain=("30th",),
    ),
    RealisticCase(
        id="far_interest_legit",
        source="FAR 52.232-25(b)",
        document_type="federal payment clause",
        category="conditionality",
        family="legitimate",
        source_text=FAR_232_25_INTEREST,
        claim=(
            "The payment office will pay an interest penalty automatically if "
            "payment is not made by the due date."
        ),
        quote="The designated payment office will pay an interest penalty automatically, without request from the Contractor, if payment is not made by the due date",
    ),
    RealisticCase(
        id="far_cure_legit",
        source="FAR 52.249-8(a)",
        document_type="federal default clause",
        category="quantity",
        family="legitimate",
        source_text=FAR_249_8_CURE,
        claim="The Government may terminate for default if the Contractor does not cure within 10 days.",
        quote="if the Contractor does not cure such failure within 10 days",
        must_contain=("10 days",),
    ),
    RealisticCase(
        id="far_continue_legit",
        source="FAR 52.249-8(e)",
        document_type="federal default clause",
        category="polarity",
        family="legitimate",
        source_text=FAR_249_8_CONTINUE,
        claim="The Contractor shall continue the work not terminated.",
        quote="The Contractor shall continue the work not terminated",
    ),
    RealisticCase(
        id="far_pay_legit",
        source="FAR 52.249-8(f)",
        document_type="federal default clause",
        category="role_reversal",
        family="legitimate",
        source_text=FAR_249_8_PAY,
        claim="The Government shall pay the contract price for completed supplies delivered and accepted.",
        quote="The Government shall pay contract price for completed supplies delivered and accepted",
    ),
    RealisticCase(
        id="far_flowdown_legit",
        source="FAR 52.204-21(c)",
        document_type="federal safeguarding clause",
        category="parties",
        family="legitimate",
        source_text=FAR_204_21_FLOWDOWN,
        claim="The Contractor shall include the substance of this clause in subcontracts under this contract.",
        quote="The Contractor shall include the substance of this clause",
    ),
    RealisticCase(
        id="far_sanitize_legit",
        source="FAR 52.204-21(b)",
        document_type="federal safeguarding clause",
        category="legit_imperative",
        family="legitimate",
        source_text=FAR_204_21_SANITIZE,
        claim="Sanitize or destroy information system media before disposal or release.",
        quote="Sanitize or destroy information system media containing Federal Contract Information before disposal or release",
        notes=(
            "A bare imperative requirement with NO party as its subject. Real "
            "federal contract language, and exactly the shape the injection "
            "heuristic looks for."
        ),
    ),
    RealisticCase(
        id="far_limit_legit",
        source="FAR 52.204-21(b)",
        document_type="federal safeguarding clause",
        category="legit_imperative",
        family="legitimate",
        source_text=FAR_204_21_LIMIT,
        claim="Limit information system access to authorized users.",
        quote="Limit information system access to authorized users",
        notes="Another bare imperative requirement, no party subject.",
    ),
]


REALISTIC_ALL: list[RealisticCase] = [*REALISTIC_ATTACKS, *REALISTIC_LEGITIMATE]

#: Every excerpt used, for the provenance table in the report.
SOURCES = {
    "FAR 52.212-4": "Contract Terms and Conditions - Commercial Products and Services",
    "FAR 52.232-25": "Prompt Payment",
    "FAR 52.249-8": "Default (Fixed-Price Supply and Service)",
    "FAR 52.204-21": "Basic Safeguarding of Covered Contractor Information Systems",
}
