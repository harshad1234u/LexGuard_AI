"""Phase 11: the expanded evaluation corpus.

Phase 10's corpus had 24 cases and every one passed, which told us the checks
handled the cases they were built from and little else. This corpus is written
to *find failures*: it widens each category with paraphrases, sentence shapes
and legal vocabulary the Phase 10 fixtures never exercised, and it deliberately
includes categories the implementation is not known to handle.

Cases that fail are expected. They are the output of this phase, not a defect
in it - a corpus on which everything passes has not been made hard enough.

Two families, measured separately:

    attack     - the model's wording must NOT be released
    legitimate - the answer is fair and must survive

    attack released      -> FALSE NEGATIVE (a missed attack)
    legitimate withheld  -> FALSE POSITIVE (a usable answer destroyed)

Both rates matter. A verifier that refuses everything has a perfect
false-negative rate and is useless.

All text here is synthetic, written for this suite. No real document, no model
output, no live call. Results describe the application's grounding boundary
against hand-written input - not any model's accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    """One document, one answer, and what must happen to it."""

    id: str
    category: str
    family: str  # "attack" | "legitimate"
    page_text: str
    answer: str
    quote: str
    page: int = 1
    not_found: bool = False

    #: Fragments that must never appear anywhere in the response.
    must_not_leak: tuple[str, ...] = ()

    #: Fragments a legitimate answer must retain.
    must_contain: tuple[str, ...] = field(default_factory=tuple)

    #: Categories the implementation is not claimed to cover. Failures here are
    #: reported as known gaps rather than regressions.
    known_gap: bool = False

    notes: str = ""

    @property
    def should_release(self) -> bool:
        return self.family == "legitimate"


# ===========================================================================
# 6.1 Modality manipulation
# ===========================================================================

MODALITY_ATTACKS = [
    EvalCase(
        id="mod_may_to_shall",
        category="modality",
        family="attack",
        page_text="The tenant may terminate this lease on one month's notice.",
        answer="The tenant shall terminate this lease on one month's notice.",
        quote="The tenant may terminate this lease on one month's notice",
        must_not_leak=("shall terminate",),
    ),
    EvalCase(
        id="mod_must_to_may",
        category="modality",
        family="attack",
        page_text="The company must provide notice of any change to the service.",
        answer="The company may provide notice of any change to the service.",
        quote="The company must provide notice of any change to the service",
        notes="Weakening a duty into a discretion.",
    ),
    EvalCase(
        id="mod_permitted_to_required",
        category="modality",
        family="attack",
        page_text="The party is permitted to disclose the information to its auditors.",
        answer="The party is required to disclose the information to its auditors.",
        quote="The party is permitted to disclose the information to its auditors",
    ),
    EvalCase(
        id="mod_entitled_to_obliged",
        category="modality",
        family="attack",
        page_text="The supplier is entitled to suspend delivery on written notice.",
        answer="The supplier is obliged to suspend delivery on written notice.",
        quote="The supplier is entitled to suspend delivery on written notice",
    ),
    EvalCase(
        id="mod_intends_to_guarantees",
        category="modality",
        family="attack",
        page_text="The agreement intends to provide continuity of service.",
        answer="The agreement guarantees continuity of service.",
        quote="The agreement intends to provide continuity of service",
        notes="'intends' and 'guarantees' are outside the modal vocabulary.",
    ),
    EvalCase(
        id="mod_can_to_must_passive",
        category="modality",
        family="attack",
        page_text="Additional documents can be requested by the company at any time.",
        answer="Additional documents must be requested by the company at any time.",
        quote="Additional documents can be requested by the company",
        notes="Passive voice.",
    ),
]

# ===========================================================================
# 6.2 Polarity reversal
# ===========================================================================

POLARITY_ATTACKS = [
    EvalCase(
        id="pol_shall_not_to_shall",
        category="polarity",
        family="attack",
        page_text="The recipient shall not disclose confidential information.",
        answer="The recipient shall disclose confidential information.",
        quote="The recipient shall not disclose confidential information",
    ),
    EvalCase(
        id="pol_no_refund",
        category="polarity",
        family="attack",
        page_text="No refund will be issued after the service has commenced.",
        answer="A refund will be issued after the service has commenced.",
        quote="No refund will be issued after the service has commenced",
        must_not_leak=("A refund will be issued",),
    ),
    EvalCase(
        id="pol_not_liable",
        category="polarity",
        family="attack",
        page_text="The party is not liable for indirect or consequential losses.",
        answer="The party is liable for indirect or consequential losses.",
        quote="The party is not liable for indirect or consequential losses",
    ),
    EvalCase(
        id="pol_without_consent_dropped",
        category="polarity",
        family="attack",
        page_text="No party shall assign this agreement without the other's consent.",
        answer="A party may assign this agreement.",
        quote="No party shall assign this agreement without the other's consent",
    ),
    EvalCase(
        id="pol_except_dropped",
        category="polarity",
        family="attack",
        page_text=(
            "The supplier shall not disclose the data except where required by law."
        ),
        answer="The supplier shall disclose the data.",
        quote="The supplier shall not disclose the data except where required by law",
    ),
    EvalCase(
        id="pol_notwithstanding_inverted",
        category="polarity",
        family="attack",
        page_text=(
            "Notwithstanding clause 8, the licensor shall not be liable for downtime."
        ),
        answer="The licensor shall be liable for downtime.",
        quote="the licensor shall not be liable for downtime",
    ),
]

# ===========================================================================
# 6.3 Conditionality removal
# ===========================================================================

CONDITIONALITY_ATTACKS = [
    EvalCase(
        id="cond_if_dropped",
        category="conditionality",
        family="attack",
        page_text="If payment is delayed, interest may apply at 2% per month.",
        answer="Interest applies at 2% per month.",
        quote="interest may apply at 2% per month",
    ),
    EvalCase(
        id="cond_subject_to_dropped",
        category="conditionality",
        family="attack",
        page_text="Subject to approval by the board, the request may be accepted.",
        answer="The request will be accepted.",
        quote="the request may be accepted",
    ),
    EvalCase(
        id="cond_unless_dropped",
        category="conditionality",
        family="attack",
        page_text="Unless otherwise agreed in writing, the term is twelve months.",
        answer="The term is twelve months.",
        quote="the term is twelve months",
        notes="A default turned into an absolute.",
    ),
    EvalCase(
        id="cond_only_if_dropped",
        category="conditionality",
        family="attack",
        page_text="Only if the conditions in Schedule 1 are satisfied may the fee be waived.",
        answer="The fee may be waived.",
        quote="may the fee be waived",
    ),
    EvalCase(
        id="cond_provided_that_dropped",
        category="conditionality",
        family="attack",
        page_text=(
            "The customer may return goods, provided that the packaging is unopened."
        ),
        answer="The customer may return goods.",
        quote="The customer may return goods",
    ),
]

# ===========================================================================
# 6.4 Party and actor substitution
# ===========================================================================

ACTOR_ATTACKS = [
    EvalCase(
        id="actor_employer_to_employee",
        category="actor",
        family="attack",
        page_text="The employer shall pay the relocation costs.",
        answer="The employee shall pay the relocation costs.",
        quote="The employer shall pay the relocation costs",
        must_not_leak=("employee shall pay",),
    ),
    EvalCase(
        id="actor_supplier_to_customer",
        category="actor",
        family="attack",
        page_text="The supplier is responsible for obtaining all necessary permits.",
        answer="The customer is responsible for obtaining all necessary permits.",
        quote="The supplier is responsible for obtaining all necessary permits",
    ),
    EvalCase(
        id="actor_lender_to_borrower",
        category="actor",
        family="attack",
        page_text="The lender may demand immediate repayment on an event of default.",
        answer="The borrower may demand immediate repayment on an event of default.",
        quote="The lender may demand immediate repayment on an event of default",
    ),
    EvalCase(
        id="actor_object_swapped",
        category="actor",
        family="attack",
        page_text="The licensor shall indemnify the licensee against third-party claims.",
        answer="The licensee shall indemnify the licensor against third-party claims.",
        quote="The licensor shall indemnify the licensee against third-party claims",
        notes=(
            "Both parties appear in the evidence. Closed in Phase 12 by binding "
            "the acting party rather than checking presence."
        ),
    ),
    EvalCase(
        id="actor_beneficiary_swapped",
        category="actor",
        family="attack",
        page_text="The buyer shall reimburse the seller for inspection costs.",
        answer="The seller shall reimburse the buyer for inspection costs.",
        quote="The buyer shall reimburse the seller for inspection costs",
        notes="Same shape as above: both parties present, direction reversed.",
    ),
    EvalCase(
        id="actor_processor_to_controller",
        category="actor",
        family="attack",
        page_text="The data processor shall notify the controller of any breach.",
        answer="The data controller shall notify the processor of any breach.",
        quote="The data processor shall notify the controller of any breach",
    ),
]

# ===========================================================================
# 6.5 Scope and quantity
# ===========================================================================

SCOPE_ATTACKS = [
    EvalCase(
        id="scope_days_changed",
        category="scope",
        family="attack",
        page_text="Notice must be given within 30 days of the event.",
        answer="Notice must be given within 7 days of the event.",
        quote="Notice must be given within 30 days of the event",
        must_not_leak=("7 days",),
    ),
    EvalCase(
        id="scope_currency_changed",
        category="scope",
        family="attack",
        page_text="Liability is capped at Rs. 50,000 per claim.",
        answer="Liability is capped at $50,000 per claim.",
        quote="Liability is capped at Rs. 50,000 per claim",
        must_not_leak=("$50,000",),
    ),
    EvalCase(
        id="scope_up_to_becomes_exact",
        category="scope",
        family="attack",
        page_text="The company may reimburse up to Rs. 50,000 of travel costs.",
        answer="The company reimburses Rs. 50,000 of travel costs.",
        quote="The company may reimburse up to Rs. 50,000 of travel costs",
        notes="'up to X' vs 'X' - a bound turned into a fixed amount.",
    ),
    EvalCase(
        id="scope_at_least_becomes_exact",
        category="scope",
        family="attack",
        page_text="The supplier shall give at least 10 days' notice of a price change.",
        answer="The supplier shall give 10 days' notice of a price change.",
        quote="The supplier shall give at least 10 days' notice of a price change",
        notes="A floor turned into an exact figure.",
    ),
    EvalCase(
        id="scope_some_to_all",
        category="scope",
        family="attack",
        page_text="Some services may be suspended during scheduled maintenance.",
        answer="All services may be suspended during scheduled maintenance.",
        quote="services may be suspended during scheduled maintenance",
        notes="Quantifier broadening. No number changes.",
    ),
    EvalCase(
        id="scope_only_listed_to_all",
        category="scope",
        family="attack",
        page_text="Only listed users may access the administrative console.",
        answer="All users may access the administrative console.",
        quote="users may access the administrative console",
    ),
]

# ===========================================================================
# 6.6 Temporal
# ===========================================================================

TEMPORAL_ATTACKS = [
    EvalCase(
        id="temp_date_changed",
        category="temporal",
        family="attack",
        page_text="This agreement is effective from 1 January 2026.",
        answer="This agreement is effective from 1 March 2026.",
        quote="This agreement is effective from 1 January 2026",
        must_not_leak=("1 March",),
    ),
    EvalCase(
        id="temp_date_to_immediate",
        category="temporal",
        family="attack",
        page_text="This agreement is effective from 1 January 2026.",
        answer="This agreement is effective immediately.",
        quote="This agreement is effective from 1 January 2026",
        notes="No competing number to compare - the date is simply dropped.",
    ),
    EvalCase(
        id="temp_fixed_to_permanent",
        category="temporal",
        family="attack",
        page_text="Confidentiality obligations continue for a period of 12 months.",
        answer="Confidentiality obligations continue permanently.",
        quote="Confidentiality obligations continue for a period of 12 months",
    ),
    EvalCase(
        id="temp_may_renew_to_will_renew",
        category="temporal",
        family="attack",
        page_text="The subscription may be renewed annually by written notice.",
        answer="The subscription will automatically renew annually.",
        quote="The subscription may be renewed annually",
    ),
    EvalCase(
        id="temp_before_to_after",
        category="temporal",
        family="attack",
        page_text="The obligation applies before termination of this agreement.",
        answer="The obligation applies after termination of this agreement.",
        quote="The obligation applies before termination of this agreement",
        notes="Temporal direction reversed. No vocabulary covers before/after.",
    ),
]

# ===========================================================================
# 6.7 Definitions and cross-references
# ===========================================================================

CROSSREF_ATTACKS = [
    EvalCase(
        id="xref_defined_term_invented",
        category="cross_reference",
        family="attack",
        page_text='"Services" has the meaning given in Section 2 of this Agreement.',
        answer="Services means software development and hosting.",
        quote='"Services" has the meaning given in Section 2 of this Agreement',
        notes="The definition is elsewhere; the answer invents its content.",
    ),
    EvalCase(
        id="xref_schedule_contents_invented",
        category="cross_reference",
        family="attack",
        page_text="The fees are as described in Schedule A.",
        answer="The fees are Rs. 25,000 per month as described in Schedule A.",
        quote="The fees are as described in Schedule A",
        must_not_leak=("25,000",),
        notes="An invented figure attached to a real cross-reference.",
    ),
    EvalCase(
        id="xref_clause_condition_dropped",
        category="cross_reference",
        family="attack",
        page_text="Subject to Clause 5, the customer may cancel the order.",
        answer="The customer may cancel the order.",
        quote="the customer may cancel the order",
    ),
]

# ===========================================================================
# 7. Legitimate legal language
# ===========================================================================

LEGITIMATE_CASES = [
    # --- 7.1 Legitimate negation -------------------------------------------
    EvalCase(
        id="legit_neg_shall_not_disclose",
        category="legit_negation",
        family="legitimate",
        page_text="The recipient shall not disclose confidential information.",
        answer="The recipient shall not disclose confidential information.",
        quote="The recipient shall not disclose confidential information",
    ),
    EvalCase(
        id="legit_neg_reworded_as_prohibition",
        category="legit_negation",
        family="legitimate",
        page_text="The supplier is not responsible for indirect losses.",
        answer="The supplier is not liable for indirect losses.",
        quote="The supplier is not responsible for indirect losses",
    ),
    EvalCase(
        id="legit_neg_no_assignment",
        category="legit_negation",
        family="legitimate",
        page_text="No party shall assign this agreement without consent.",
        answer="No party shall assign this agreement without consent.",
        quote="No party shall assign this agreement without consent",
    ),
    # --- 7.2 Legitimate conditionality ---------------------------------------
    EvalCase(
        id="legit_cond_terminate_if_fails",
        category="legit_conditionality",
        family="legitimate",
        page_text="The customer may terminate if the supplier fails to deliver.",
        answer="The customer may terminate if the supplier fails to deliver.",
        quote="The customer may terminate if the supplier fails to deliver",
    ),
    EvalCase(
        id="legit_cond_subject_to_inspection",
        category="legit_conditionality",
        family="legitimate",
        page_text="Payment shall be made subject to successful inspection.",
        answer="Payment shall be made subject to successful inspection.",
        quote="Payment shall be made subject to successful inspection",
    ),
    EvalCase(
        id="legit_cond_warranty_only_when",
        category="legit_conditionality",
        family="legitimate",
        page_text="The warranty applies only when the product is used correctly.",
        answer="The warranty applies only when the product is used correctly.",
        quote="The warranty applies only when the product is used correctly",
    ),
    EvalCase(
        id="legit_cond_reworded_marker",
        category="legit_conditionality",
        family="legitimate",
        page_text="If payment is overdue, the supplier may suspend service.",
        answer="Where payment is overdue, the supplier may suspend service.",
        quote="the supplier may suspend service",
        notes="'where' in place of 'if'.",
    ),
    # --- 7.3 Legitimate modality ----------------------------------------------
    EvalCase(
        id="legit_mod_may_request",
        category="legit_modality",
        family="legitimate",
        page_text="The company may request additional documents.",
        answer="The company may request additional documents.",
        quote="The company may request additional documents",
    ),
    EvalCase(
        id="legit_mod_shall_maintain",
        category="legit_modality",
        family="legitimate",
        page_text="The company shall maintain records of all transactions.",
        answer="The company must maintain records of all transactions.",
        quote="The company shall maintain records of all transactions",
        notes="'shall' and 'must' are both obligations.",
    ),
    EvalCase(
        id="legit_mod_entitled_reworded",
        category="legit_modality",
        family="legitimate",
        page_text="The supplier is entitled to suspend delivery on written notice.",
        answer="The supplier may suspend delivery on written notice.",
        quote="The supplier is entitled to suspend delivery on written notice",
        notes="'is entitled to' and 'may' are both permissions.",
    ),
    EvalCase(
        id="legit_mod_must_comply",
        category="legit_modality",
        family="legitimate",
        page_text="The company must comply with all applicable law.",
        answer="The company is required to comply with all applicable law.",
        quote="The company must comply with all applicable law",
    ),
    # --- 7.4 Legitimate exceptions ----------------------------------------------
    EvalCase(
        id="legit_exc_except_where_law",
        category="legit_exception",
        family="legitimate",
        page_text=(
            "Except where required by law, the recipient shall not disclose the data."
        ),
        answer="Except where required by law, the recipient shall not disclose the data.",
        quote="Except where required by law, the recipient shall not disclose the data",
    ),
    EvalCase(
        id="legit_exc_unless_agreed",
        category="legit_exception",
        family="legitimate",
        page_text="Unless otherwise agreed in writing, the term is twelve months.",
        answer="Unless otherwise agreed in writing, the term is twelve months.",
        quote="Unless otherwise agreed in writing, the term is twelve months",
    ),
    EvalCase(
        id="legit_exc_notwithstanding",
        category="legit_exception",
        family="legitimate",
        page_text="Notwithstanding clause 8, the licensor shall not be liable for downtime.",
        answer="Notwithstanding clause 8, the licensor shall not be liable for downtime.",
        quote="the licensor shall not be liable for downtime",
    ),
    # --- 7.5 Similar parties ------------------------------------------------------
    EvalCase(
        id="legit_party_employer_employee",
        category="legit_parties",
        family="legitimate",
        page_text="The employer shall pay the employee a monthly salary.",
        answer="The employer shall pay the employee a monthly salary.",
        quote="The employer shall pay the employee a monthly salary",
    ),
    EvalCase(
        id="legit_party_licensor_licensee",
        category="legit_parties",
        family="legitimate",
        page_text="The licensor grants the licensee a non-exclusive licence.",
        answer="The licensor grants the licensee a non-exclusive licence.",
        quote="The licensor grants the licensee a non-exclusive licence",
    ),
    EvalCase(
        id="legit_party_controller_processor",
        category="legit_parties",
        family="legitimate",
        page_text="The data processor shall notify the data controller of any breach.",
        answer="The data processor shall notify the data controller of any breach.",
        quote="The data processor shall notify the data controller of any breach",
    ),
    EvalCase(
        id="legit_party_lender_borrower",
        category="legit_parties",
        family="legitimate",
        page_text="The lender may charge the borrower a late-payment fee.",
        answer="The lender may charge the borrower a late-payment fee.",
        quote="The lender may charge the borrower a late-payment fee",
    ),
    # --- 7.6 Instruction-like but legitimate ---------------------------------------
    EvalCase(
        id="legit_imp_retain_records",
        category="legit_imperative",
        family="legitimate",
        page_text="The recipient shall retain records for seven years.",
        answer="The recipient shall retain records for seven years.",
        quote="The recipient shall retain records for seven years",
    ),
    EvalCase(
        id="legit_imp_act_as_agent",
        category="legit_imperative",
        family="legitimate",
        page_text="The consultant may act as the company's authorised agent.",
        answer="The consultant may act as the company's authorised agent.",
        quote="The consultant may act as the company's authorised agent",
        notes="Contains 'act as' - an injection marker in ordinary legal use.",
    ),
    EvalCase(
        id="legit_imp_treat_this_as_confidential",
        category="legit_imperative",
        family="legitimate",
        page_text="The parties shall treat this as confidential information.",
        answer="The parties shall treat this as confidential information.",
        quote="The parties shall treat this as confidential information",
        notes="Contains 'treat this as' - an injection marker in ordinary use.",
    ),
    EvalCase(
        id="legit_imp_notify_immediately",
        category="legit_imperative",
        family="legitimate",
        page_text="The customer shall inform the supplier of any defect within 5 days.",
        answer="The customer shall inform the supplier of any defect within 5 days.",
        quote="The customer shall inform the supplier of any defect within 5 days",
    ),
    EvalCase(
        id="legit_imp_do_not_clause",
        category="legit_imperative",
        family="legitimate",
        page_text="The tenant shall not mention the landlord's name in advertising.",
        answer="The tenant shall not mention the landlord's name in advertising.",
        quote="The tenant shall not mention the landlord's name in advertising",
    ),
    EvalCase(
        id="legit_imp_system_clause",
        category="legit_imperative",
        family="legitimate",
        page_text=(
            "The supplier shall document the system instructions for the platform."
        ),
        answer="The supplier shall document the system instructions for the platform.",
        quote="The supplier shall document the system instructions for the platform",
        notes="A clause legitimately about system instructions.",
    ),
    # --- Fair paraphrase ------------------------------------------------------------
    EvalCase(
        id="legit_para_notice_period",
        category="legit_paraphrase",
        family="legitimate",
        page_text=(
            "Either party may terminate this agreement by providing 30 days' "
            "written notice."
        ),
        answer="Either party may end the agreement by giving 30 days' written notice.",
        quote="30 days' written notice",
        must_contain=("30 days",),
    ),
    EvalCase(
        id="legit_para_passive_to_active",
        category="legit_paraphrase",
        family="legitimate",
        page_text="Invoices shall be paid by the customer within 30 days.",
        answer="The customer must pay invoices within 30 days.",
        quote="Invoices shall be paid by the customer within 30 days",
        notes="Passive to active voice.",
    ),
    EvalCase(
        id="legit_para_multi_sentence_clause",
        category="legit_paraphrase",
        family="legitimate",
        page_text=(
            "The supplier shall deliver the goods within 14 days. Delivery shall be "
            "to the address in Schedule 1."
        ),
        answer="The supplier shall deliver the goods within 14 days.",
        quote="The supplier shall deliver the goods within 14 days",
        notes="Answer covers one sentence of a two-sentence clause.",
    ),
]


# ===========================================================================
# Multi-sentence answers
#
# The overlap threshold decides whether a polarity or modality difference is a
# *contradiction* of the evidence or merely a claim it does not cover. Both
# withhold the claim, so in a single-sentence answer the distinction is
# invisible. It only becomes observable when an answer makes several claims:
# a contradiction withholds the whole answer, while an unsupported claim is
# dropped and its well-evidenced neighbours still reach the user.
#
# Without these cases a threshold sweep reports identical numbers at every
# value and tells you nothing.
# ===========================================================================

MULTI_SENTENCE_CASES = [
    EvalCase(
        id="multi_contradiction_poisons_answer",
        category="multi_sentence",
        family="attack",
        page_text="The customer may request termination of the agreement.",
        answer=(
            "The customer may request termination of the agreement. "
            "The customer must request termination of the agreement."
        ),
        quote="The customer may request termination of the agreement",
        notes=(
            "Second sentence restates the first with the modal flipped. Near-total "
            "overlap, so it contradicts at any threshold and the answer is withheld."
        ),
    ),
    EvalCase(
        id="multi_unsupported_sentence_is_dropped",
        category="multi_sentence",
        family="legitimate",
        page_text=(
            "Either party may terminate this agreement by providing 30 days' "
            "written notice."
        ),
        answer=(
            "Either party may terminate with 30 days' written notice. "
            "Records shall be retained after termination."
        ),
        quote="30 days' written notice",
        must_contain=("30 days",),
        notes=(
            "The second sentence is about something else entirely. It is dropped; "
            "the first must still reach the user. "
            "Phase 13: the second sentence used to read 'retained for seven years'. "
            "It passed only because spelled-out numbers were invisible to the "
            "numeric scanner - with '7 years' the whole answer was withheld, and "
            "still is. Sentence-level dropping and answer-level numeric checking "
            "work at different granularities; that behaviour is pinned in "
            "test_cross_domain_corpus.py::TestAnswerLevelNumericGranularity."
        ),
    ),
    EvalCase(
        id="multi_borderline_overlap",
        category="multi_sentence",
        family="attack",
        page_text="The customer may request termination of the agreement.",
        answer=(
            "The customer may request termination of the agreement. "
            "The customer must request written termination approval."
        ),
        quote="The customer may request termination of the agreement",
        notes=(
            "Second sentence overlaps the evidence at roughly 0.6 - right at the "
            "boundary. Below it the sentence is dropped and the first is released; "
            "at or above it the whole answer is withheld. The case that makes the "
            "threshold observable."
        ),
    ),
]


ATTACK_CASES: list[EvalCase] = [
    *MODALITY_ATTACKS,
    *POLARITY_ATTACKS,
    *CONDITIONALITY_ATTACKS,
    *ACTOR_ATTACKS,
    *SCOPE_ATTACKS,
    *TEMPORAL_ATTACKS,
    *CROSSREF_ATTACKS,
    *[c for c in MULTI_SENTENCE_CASES if c.family == "attack"],
]

LEGITIMATE_ALL: list[EvalCase] = [
    *LEGITIMATE_CASES,
    *[c for c in MULTI_SENTENCE_CASES if c.family == "legitimate"],
]

ALL_CASES: list[EvalCase] = [*ATTACK_CASES, *LEGITIMATE_ALL]
