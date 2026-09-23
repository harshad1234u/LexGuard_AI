"""Phase 13: the named-entity role corpus.

Phase 12 closed role reversal for role nouns ("the Buyer", "the Supplier") and
left one category open: two named companies whose roles are swapped. That gap
was recorded with a single fixture. One fixture is not a measurement, and the
Phase 12 report's own limitation list said so.

This module is the matrix that was missing. It covers, deliberately:

    active voice                 permission vs obligation
    passive voice                actor / recipient reversal
    named organisations          multiple parties (three sides)
    similar organisation names   names containing role nouns
    defined short forms          repeated mentions of one entity
    pronouns and back-references negated clauses
    conditional obligations      multi-sentence claims
    individuals                  entity substitution

All text here is written for this suite, and is labelled synthetic wherever it
is reported. Named-entity cases drawn from REAL agreements - Anthem/Castlight
and Demandware/neckermann.de - live in fixtures_contracts.py and are scored
separately. Synthetic results are not evidence that this works on real
contracts; the real corpus is.

Cases carrying `known_gap=True` are ones this implementation is NOT claimed to
handle. They are asserted as currently failing rather than skipped, so that the
limitation list in the Phase 13 report cannot quietly go stale.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityCase:
    id: str
    construction: str
    family: str  # "attack" | "legitimate"
    evidence: str
    claim: str
    known_gap: bool = False
    notes: str = ""

    @property
    def should_release(self) -> bool:
        return self.family == "legitimate"


# ---------------------------------------------------------------------------
# Reversals and substitutions that must be caught
# ---------------------------------------------------------------------------

ENTITY_ATTACKS: list[EntityCase] = [
    EntityCase(
        id="ent_active_named",
        construction="active, two named organisations",
        family="attack",
        evidence="Northwind Ltd shall reimburse Contoso Ltd for all approved expenses.",
        claim="Contoso Ltd shall reimburse Northwind Ltd for all approved expenses.",
        notes="The base case. No role noun anywhere in the sentence.",
    ),
    EntityCase(
        id="ent_active_no_suffix",
        construction="active, defined short forms",
        family="attack",
        evidence="Northwind shall reimburse Contoso for all approved expenses.",
        claim="Contoso shall reimburse Northwind for all approved expenses.",
        notes=(
            "How real agreements actually read: the corporate suffix appears "
            "once in the preamble and never again in the body."
        ),
    ),
    EntityCase(
        id="ent_passive_named",
        construction="passive, named agent",
        family="attack",
        evidence="The monthly report shall be prepared by Northwind Ltd.",
        claim="The monthly report shall be prepared by Contoso Ltd.",
        notes="Agent follows the verb. Word order is no help here.",
    ),
    EntityCase(
        id="ent_permission_reversed",
        construction="permission, reversed",
        family="attack",
        evidence="Northwind may audit the records of Contoso once per year.",
        claim="Contoso may audit the records of Northwind once per year.",
        notes="Who holds the right, inverted. Modality unchanged.",
    ),
    EntityCase(
        id="ent_prohibition_reversed",
        construction="negated clause, reversed",
        family="attack",
        evidence="Northwind shall not disclose the pricing schedule to Contoso.",
        claim="Contoso shall not disclose the pricing schedule to Northwind.",
        notes="Polarity identical on both sides; only the roles moved.",
    ),
    EntityCase(
        id="ent_conditional_reversed",
        construction="conditional obligation, reversed",
        family="attack",
        evidence="If the service fails, Northwind shall credit Contoso within 10 days.",
        claim="If the service fails, Contoso shall credit Northwind within 10 days.",
        notes="The condition survives intact, so only the role check can see this.",
    ),
    EntityCase(
        id="ent_substitution",
        construction="entity substitution",
        family="attack",
        evidence="Northwind Ltd shall indemnify Contoso Ltd against third-party claims.",
        claim="Fabrikam Ltd shall indemnify Contoso Ltd against third-party claims.",
        notes=(
            "Not a swap - a party that is not in the document at all. Must be "
            "caught by presence, not by role binding."
        ),
    ),
    EntityCase(
        id="ent_name_contains_role_noun",
        construction="name containing a role noun",
        family="attack",
        evidence="Contractor Services Ltd shall invoice Supplier Holdings Ltd monthly.",
        claim="Supplier Holdings Ltd shall invoice Contractor Services Ltd monthly.",
        notes=(
            "Both company names contain a word that is itself a party term. A "
            "checker keying on the role noun alone picks the wrong entity."
        ),
    ),
    EntityCase(
        id="ent_three_parties",
        construction="three parties",
        family="attack",
        evidence="Northwind shall pay Contoso, and Fabrikam shall guarantee the payment.",
        claim="Contoso shall pay Northwind, and Fabrikam shall guarantee the payment.",
        notes="A third party is present and unmoved; the other two are swapped.",
    ),
    EntityCase(
        id="ent_repeated_mentions",
        construction="repeated mentions of one entity",
        family="attack",
        evidence=(
            "Northwind shall maintain the platform and Northwind shall bear the "
            "cost of doing so."
        ),
        claim=(
            "Contoso shall maintain the platform and Contoso shall bear the cost "
            "of doing so."
        ),
        notes="The whole obligation moved to a different company.",
    ),
    EntityCase(
        id="ent_multi_sentence",
        construction="multi-sentence claim",
        family="attack",
        evidence=(
            "Northwind shall deliver the goods. Contoso shall inspect them within "
            "five days."
        ),
        claim=(
            "Northwind shall deliver the goods. Northwind shall inspect them "
            "within five days."
        ),
        notes="First sentence faithful, second reversed. Claims are judged apart.",
    ),
    EntityCase(
        id="ent_individual_honorific",
        construction="individuals",
        family="attack",
        evidence="Mr Alvarez shall notify Ms Chen of any change in circumstances.",
        claim="Ms Chen shall notify Mr Alvarez of any change in circumstances.",
        notes="Named individuals rather than organisations.",
    ),
    EntityCase(
        id="ent_similar_names",
        construction="similar organisation names",
        family="attack",
        evidence="Northwind Holdings Ltd shall pay Northwind Services Ltd a management fee.",
        claim="Northwind Services Ltd shall pay Northwind Holdings Ltd a management fee.",
        notes=(
            "Two entities sharing a leading token. Distinguishing them needs the "
            "whole name, not its first word."
        ),
    ),
    EntityCase(
        id="ent_pronoun_backreference",
        construction="pronoun back-reference",
        family="attack",
        evidence="Northwind shall issue the invoice, and it shall bear the processing cost.",
        claim="Contoso shall issue the invoice, and it shall bear the processing cost.",
        notes=(
            "Caught because the named subject moved. Nothing here resolves what "
            "'it' refers to - see ent_pronoun_referent_is_ambiguous for what "
            "happens when the pronoun is the only thing identifying the party."
        ),
    ),
    EntityCase(
        id="ent_pronoun_referent_is_ambiguous",
        construction="pronoun as the only identifier",
        family="attack",
        evidence="Northwind shall notify Contoso. It shall then have ten days to respond.",
        claim="Northwind shall notify Contoso. Contoso shall then have ten days to respond.",
        notes=(
            "The document does not say who 'it' is, and neither does this "
            "system - no anaphora resolution is attempted anywhere. The naming "
            "of a party the evidence sentence does not contain is what withholds "
            "the answer, which is the required behaviour: decline rather than "
            "pick a referent. Asserted so that 'fails closed on pronouns' is a "
            "measured property and not a claim in a report."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Faithful answers that must survive
#
# This half decides whether the role binding is usable at all.
# ---------------------------------------------------------------------------

ENTITY_LEGITIMATE: list[EntityCase] = [
    EntityCase(
        id="ent_legit_verbatim",
        construction="active, two named organisations",
        family="legitimate",
        evidence="Northwind Ltd shall reimburse Contoso Ltd for all approved expenses.",
        claim="Northwind Ltd shall reimburse Contoso Ltd for all approved expenses.",
    ),
    EntityCase(
        id="ent_legit_suffix_dropped",
        construction="defined short form",
        family="legitimate",
        evidence="Northwind Ltd shall reimburse Contoso Ltd for all approved expenses.",
        claim="Northwind shall reimburse Contoso for all approved expenses.",
        notes=(
            "The short form of the same two companies. Treating 'Northwind' and "
            "'Northwind Ltd' as different parties would withhold most correct "
            "answers about any real agreement."
        ),
    ),
    EntityCase(
        id="ent_legit_active_to_passive",
        construction="voice change",
        family="legitimate",
        evidence="Northwind Ltd shall prepare the monthly report.",
        claim="The monthly report shall be prepared by Northwind Ltd.",
        notes="Faithful paraphrase with the word order reversed.",
    ),
    EntityCase(
        id="ent_legit_passive_to_active",
        construction="voice change",
        family="legitimate",
        evidence="The monthly report shall be prepared by Northwind Ltd.",
        claim="Northwind Ltd shall prepare the monthly report.",
    ),
    EntityCase(
        id="ent_legit_modality_reworded",
        construction="modality restated",
        family="legitimate",
        evidence="Northwind shall reimburse Contoso for all approved expenses.",
        claim="Northwind must reimburse Contoso for all approved expenses.",
        notes="Shall to must. Roles unchanged.",
    ),
    EntityCase(
        id="ent_legit_single_entity",
        construction="single named party",
        family="legitimate",
        evidence="Northwind Ltd shall maintain adequate professional indemnity insurance.",
        claim="Northwind Ltd shall maintain adequate professional indemnity insurance.",
        notes="No second party, so there is no reversal to find.",
    ),
    EntityCase(
        id="ent_legit_no_party_named",
        construction="no party named",
        family="legitimate",
        evidence="Northwind shall reimburse Contoso for all approved expenses.",
        claim="Approved expenses are reimbursed.",
        notes="Names nobody. Must not be read as a reversal.",
    ),
    EntityCase(
        id="ent_legit_conditional_preserved",
        construction="conditional obligation",
        family="legitimate",
        evidence="If the service fails, Northwind shall credit Contoso within 10 days.",
        claim="If the service fails, Northwind shall credit Contoso within 10 days.",
    ),
    EntityCase(
        id="ent_legit_prohibition_preserved",
        construction="negated clause",
        family="legitimate",
        evidence="Northwind shall not disclose the pricing schedule to Contoso.",
        claim="Northwind shall not disclose the pricing schedule to Contoso.",
    ),
    EntityCase(
        id="ent_legit_three_parties",
        construction="three parties",
        family="legitimate",
        evidence="Northwind shall pay Contoso, and Fabrikam shall guarantee the payment.",
        claim="Northwind shall pay Contoso, and Fabrikam shall guarantee the payment.",
    ),
    EntityCase(
        id="ent_legit_name_contains_role_noun",
        construction="name containing a role noun",
        family="legitimate",
        evidence="Contractor Services Ltd shall invoice Supplier Holdings Ltd monthly.",
        claim="Contractor Services Ltd shall invoice Supplier Holdings Ltd monthly.",
    ),
    EntityCase(
        id="ent_legit_individual",
        construction="individuals",
        family="legitimate",
        evidence="Mr Alvarez shall notify Ms Chen of any change in circumstances.",
        claim="Mr Alvarez shall notify Ms Chen of any change in circumstances.",
    ),
    EntityCase(
        id="ent_legit_similar_names",
        construction="similar organisation names",
        family="legitimate",
        evidence="Northwind Holdings Ltd shall pay Northwind Services Ltd a management fee.",
        claim="Northwind Holdings Ltd shall pay Northwind Services Ltd a management fee.",
    ),
    EntityCase(
        id="ent_legit_reciprocal",
        construction="reciprocal obligation",
        family="legitimate",
        evidence="Each party shall keep the other party's information confidential.",
        claim="Each party shall keep the other party's information confidential.",
        notes="Symmetric: neither side is the actor. Must not be read as a reversal.",
    ),
    EntityCase(
        id="ent_legit_defined_term_not_a_party",
        construction="capitalised non-party term",
        family="legitimate",
        evidence="This Agreement shall commence on 1 April 2026 and run for two years.",
        claim="This Agreement shall commence on 1 April 2026 and run for two years.",
        notes=(
            "'Agreement' is a capitalised defined term and not a side of the "
            "contract. Reading it as a party would put a spurious actor into "
            "every clause that mentions the agreement itself."
        ),
    ),
    EntityCase(
        id="ent_legit_multi_sentence",
        construction="multi-sentence claim",
        family="legitimate",
        evidence=(
            "Northwind shall deliver the goods. Contoso shall inspect them within "
            "five days."
        ),
        claim=(
            "Northwind shall deliver the goods. Contoso shall inspect them within "
            "five days."
        ),
    ),
]

ENTITY_ALL: list[EntityCase] = [*ENTITY_ATTACKS, *ENTITY_LEGITIMATE]
