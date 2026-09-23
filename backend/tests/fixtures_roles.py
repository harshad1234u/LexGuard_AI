"""Phase 12: the role-reversal corpus.

Phase 11 closed every semantic category it tested except one. The three
remaining misses shared a shape: both parties appear in the evidence, and only
their grammatical roles were swapped.

    evidence: "The Buyer shall pay the Supplier within 30 days."
    claim:    "The Supplier shall pay the Buyer within 30 days."

A party-presence check cannot see this. Both terms are present in both
sentences; what changed is who is the obligor and who is the obligee.

This corpus isolates that question so it can be answered with evidence rather
than intuition. It deliberately includes constructions that would defeat a
naive word-order rule:

* passive voice, where the agent follows the verb
* clauses where the parties appear in the same order but the verb differs
* single-party clauses, where there is no reversal to find and a role checker
  must not invent one
* legitimate paraphrases that reorder a sentence without changing who owes what

The last two groups matter most. A role checker that flags everything scores
perfectly on reversals and destroys the product.

All text here is written for this suite. Realistic role-reversal cases drawn
from real FAR text live in fixtures_realistic.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleCase:
    id: str
    construction: str
    family: str  # "attack" | "legitimate"
    evidence: str
    claim: str
    notes: str = ""

    @property
    def should_release(self) -> bool:
        return self.family == "legitimate"


# ---------------------------------------------------------------------------
# Reversals that must be caught
# ---------------------------------------------------------------------------

ROLE_ATTACKS: list[RoleCase] = [
    RoleCase(
        id="role_active_simple",
        construction="active, two parties",
        family="attack",
        evidence="The Supplier shall deliver the goods to the Customer.",
        claim="The Customer shall deliver the goods to the Supplier.",
    ),
    RoleCase(
        id="role_active_payment",
        construction="active, two parties",
        family="attack",
        evidence="The Buyer shall pay the Supplier within 30 days.",
        claim="The Supplier shall pay the Buyer within 30 days.",
        notes="Numbers unchanged, so the numeric check cannot help.",
    ),
    RoleCase(
        id="role_passive_delivery",
        construction="passive",
        family="attack",
        evidence="The goods shall be delivered by the Supplier to the Customer.",
        claim="The goods shall be delivered by the Customer to the Supplier.",
        notes="Agent follows the verb. Word order alone is misleading here.",
    ),
    RoleCase(
        id="role_passive_payment",
        construction="passive",
        family="attack",
        evidence="The invoice shall be paid by the Buyer.",
        claim="The invoice shall be paid by the Seller.",
        notes="Single agent in a passive clause, replaced.",
    ),
    RoleCase(
        id="role_indemnity",
        construction="active, two parties",
        family="attack",
        evidence="The Licensor shall indemnify the Licensee against third-party claims.",
        claim="The Licensee shall indemnify the Licensor against third-party claims.",
    ),
    RoleCase(
        id="role_employer_employee",
        construction="active, two parties",
        family="attack",
        evidence="The Employer shall reimburse the Employee for travel expenses.",
        claim="The Employee shall reimburse the Employer for travel expenses.",
    ),
    RoleCase(
        id="role_lender_borrower",
        construction="active, two parties",
        family="attack",
        evidence="The Lender may require the Borrower to provide additional security.",
        claim="The Borrower may require the Lender to provide additional security.",
    ),
    RoleCase(
        id="role_controller_processor",
        construction="active, two parties",
        family="attack",
        evidence="The Processor shall notify the Controller of any personal data breach.",
        claim="The Controller shall notify the Processor of any personal data breach.",
    ),
    RoleCase(
        id="role_contractor_subcontractor",
        construction="active, two parties",
        family="attack",
        evidence="The Contractor shall supervise the Subcontractor on site.",
        claim="The Subcontractor shall supervise the Contractor on site.",
    ),
    RoleCase(
        id="role_named_entities",
        construction="named entities",
        family="attack",
        evidence="ABC Ltd shall notify XYZ Ltd of any change of address.",
        claim="XYZ Ltd shall notify ABC Ltd of any change of address.",
        notes="Named companies, not role nouns. No party vocabulary applies.",
    ),
    RoleCase(
        id="role_entitled_to",
        construction="is entitled to",
        family="attack",
        evidence="The Licensee is entitled to receive quarterly royalty statements.",
        claim="The Licensor is entitled to receive quarterly royalty statements.",
    ),
    RoleCase(
        id="role_responsible_for",
        construction="is responsible for",
        family="attack",
        evidence="The Seller is responsible for obtaining export licences.",
        claim="The Buyer is responsible for obtaining export licences.",
    ),
]


# ---------------------------------------------------------------------------
# Answers that must survive
#
# A role checker that cannot tell these from the reversals above is not usable.
# ---------------------------------------------------------------------------

ROLE_LEGITIMATE: list[RoleCase] = [
    RoleCase(
        id="role_legit_verbatim",
        construction="active, two parties",
        family="legitimate",
        evidence="The Supplier shall deliver the goods to the Customer.",
        claim="The Supplier shall deliver the goods to the Customer.",
    ),
    RoleCase(
        id="role_legit_reworded",
        construction="active, two parties",
        family="legitimate",
        evidence="The Buyer shall pay the Supplier within 30 days.",
        claim="The Buyer must pay the Supplier within 30 days.",
        notes="Modality restated, roles unchanged.",
    ),
    RoleCase(
        id="role_legit_active_to_passive",
        construction="voice change",
        family="legitimate",
        evidence="The Supplier shall deliver the goods.",
        claim="The goods shall be delivered by the Supplier.",
        notes=(
            "Same obligation, opposite word order. A word-order rule would call "
            "this a reversal; it is a faithful paraphrase."
        ),
    ),
    RoleCase(
        id="role_legit_passive_to_active",
        construction="voice change",
        family="legitimate",
        evidence="The invoice shall be paid by the Buyer.",
        claim="The Buyer shall pay the invoice.",
        notes="The mirror of the case above.",
    ),
    RoleCase(
        id="role_legit_single_party",
        construction="single party",
        family="legitimate",
        evidence="The Contractor shall maintain adequate insurance.",
        claim="The Contractor shall maintain adequate insurance.",
        notes="No second party, so there is no reversal to detect.",
    ),
    RoleCase(
        id="role_legit_party_omitted",
        construction="single party",
        family="legitimate",
        evidence="The Employer shall reimburse the Employee for travel expenses.",
        claim="Travel expenses are reimbursed.",
        notes="Names no party at all. Must not be treated as a reversal.",
    ),
    RoleCase(
        id="role_legit_named_entities",
        construction="named entities",
        family="legitimate",
        evidence="ABC Ltd shall notify XYZ Ltd of any change of address.",
        claim="ABC Ltd shall notify XYZ Ltd of any change of address.",
    ),
    RoleCase(
        id="role_legit_synonym_party",
        construction="party synonym",
        family="legitimate",
        evidence="The Client shall pay the Supplier within 30 days.",
        claim="The Customer shall pay the Supplier within 30 days.",
        notes="'Client' and 'Customer' are treated as the same actor.",
    ),
]

ROLE_ALL: list[RoleCase] = [*ROLE_ATTACKS, *ROLE_LEGITIMATE]
