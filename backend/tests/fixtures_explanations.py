"""Phase 15: the explanation corpus.

A finding is more than its claim. The `explanation` field carries two or three
sentences of plain-language interpretation, it is rendered in larger type than
the quote, and until Phase 15 nothing checked it. Measured: an explanation
reading *"the Employee is free to share the information with anyone"* was
released beneath a verbatim-correct claim that the Employee must **not**
disclose it, under a green verified badge.

The rule Phase 15 adds is deliberately narrow. An explanation is interpretation
and will usually not be a restatement of the clause, so it is not required to
be *supported* - it is required not to say the opposite. A rule that withholds
findings can only be trusted if its cost is measured, and that is what this
module is for.

`PLAIN_EXPLANATIONS` are written the way `prompts.py` instructs the model to
write them: short, concrete, for a non-lawyer. They are what correct model
output looks like, and every one of them must survive.

`ADVERSARIAL_EXPLANATIONS` attach to claims that are themselves correct. The
claim passes every Phase 14 check; the explanation is the thing that would
mislead a reader.

Each case names an `IndependentCase` and reuses its document, claim and quote,
so the explanation is the only variable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExplanationCase:
    """One finding's explanation, and whether it may be released."""

    case_id: str
    """The `IndependentCase` this explains."""

    explanation: str
    family: str
    """legitimate | attack"""

    rationale: str


PLAIN_EXPLANATIONS: tuple[ExplanationCase, ...] = (
    ExplanationCase(
        "hc_polarity_prohibition_reworded",
        "The Provider cannot send a Service User to an outside clinic on its own. "
        "It has to get the Payer's written agreement first.",
        "legitimate",
        "Restates the prohibition in everyday words.",
    ),
    ExplanationCase(
        "hc_modality_entitled_to_permission",
        "The Payer is allowed to check the Provider's compliance, but only once a year, "
        "and it has to give at least twenty working days' notice first.",
        "legitimate",
        "A permission restated as a permission, with the limits kept.",
    ),
    ExplanationCase(
        "hc_actor_passive_restatement",
        "The Payer has forty-five days from receiving a validated invoice to pay it.",
        "legitimate",
        "Same duty, same party, said from the other direction.",
    ),
    ExplanationCase(
        "hc_scope_faithful_restriction",
        "Only clinicians whose professional registration is current may deliver these "
        "services. The Provider has to check that registration before anyone starts.",
        "legitimate",
        "Keeps the restriction and adds the verification duty from the same clause.",
    ),
    ExplanationCase(
        "hc_numeric_written_form_kept",
        "Invoices are due forty-five days after they arrive.",
        "legitimate",
        "A short explanation using the same period.",
    ),
    ExplanationCase(
        "cn_conditionality_faithful",
        "If the Contractor finishes late, it owes the Employer 2,500 pounds for every "
        "week of delay. The total cannot go above 75,000 pounds however late the work is.",
        "legitimate",
        "Condition, rate and cap all carried into plain language.",
    ),
    ExplanationCase(
        "cn_exception_faithful",
        "The Contractor has to fix defects that show up during the Rectification Period "
        "at its own expense. It does not have to fix damage the Employer caused by using "
        "the Works.",
        "legitimate",
        "The carve-out is explained rather than dropped.",
    ),
    ExplanationCase(
        "cn_legit_payment_paraphrase",
        "The Employer has fourteen days after the due date to pay what the certificate "
        "says. It can pay less only if it has served a valid Pay Less Notice.",
        "legitimate",
        "Keeps the exception and the deadline.",
    ),
    ExplanationCase(
        "cn_legit_insurance_figure",
        "The Contractor must carry public liability cover of at least 5,000,000 pounds "
        "for any single incident.",
        "legitimate",
        "Same figure, same floor.",
    ),
    ExplanationCase(
        "in_numeric_faithful_lakh",
        "The most the Insurer will pay out in one policy year is Rs 10,00,000 across all "
        "admissible claims taken together.",
        "legitimate",
        "Explains what 'in the aggregate' means without changing the figure.",
    ),
    ExplanationCase(
        "in_temporal_faithful",
        "Once the Insured knows about something that might lead to a claim, it has thirty "
        "days to tell the Insurer in writing.",
        "legitimate",
        "Same window, same trigger.",
    ),
    ExplanationCase(
        "in_modality_faithful_option",
        "The Policy can be renewed if both sides agree and the renewal premium is paid "
        "before it expires. It does not renew on its own.",
        "legitimate",
        "States the option and the absence of automatic renewal, both in the clause.",
    ),
    ExplanationCase(
        "in_legit_deductible_restated",
        "The Insured pays the first Rs 25,000 of every claim itself before the Insurer "
        "pays anything.",
        "legitimate",
        "A deductible explained.",
    ),
    ExplanationCase(
        "ed_legit_fee_restated",
        "Tuition is S$12,400.00 a year, split into two equal payments due on 1 February "
        "2027 and 1 August 2027.",
        "legitimate",
        "Both dates and the amount kept.",
    ),
    ExplanationCase(
        "ed_legit_consent_restriction",
        "The Institution cannot pass the Student's academic records to an employer unless "
        "the Student has agreed in writing beforehand.",
        "legitimate",
        "A limited permission explained as a restriction - it reads negatively while the "
        "clause reads positively, which is the shape most likely to trip a polarity check.",
    ),
    ExplanationCase(
        "ed_legit_refund_paraphrase",
        "A student who withdraws in writing more than fourteen (14) days before the "
        "semester starts gets seventy-five per cent (75%) of that semester's fees back.",
        "legitimate",
        "Condition and proportion kept.",
    ),
    ExplanationCase(
        "inj_legit_disregard_prior_agreements",
        "Anything the parties agreed about the Works before this contract no longer "
        "counts. Only this document does.",
        "legitimate",
        "An entire-agreement clause explained.",
    ),
    ExplanationCase(
        "inj_legit_instruction_to_party",
        "If something happens that affects patient safety, the Provider has to tell the "
        "Payer within twenty-four (24) hours.",
        "legitimate",
        "A reporting duty explained.",
    ),
    ExplanationCase(
        "inj_legit_mark_records",
        "Examination scripts have to be marked within twenty-one (21) days of the "
        "examination.",
        "legitimate",
        "A deadline explained.",
    ),
    ExplanationCase(
        "ms_legit_two_supported_sentences",
        "The Insured covers the first Rs 25,000 of any claim. Anything below that amount "
        "is not the Insurer's responsibility at all.",
        "legitimate",
        "Two sentences, both drawn from the quoted clause.",
    ),
)


ADVERSARIAL_EXPLANATIONS: tuple[ExplanationCase, ...] = (
    ExplanationCase(
        "hc_polarity_prohibition_reworded",
        "In practice the Provider may refer a Service User to a third-party clinic "
        "without the prior written consent of the Payer.",
        "attack",
        "Reverses the prohibition the claim correctly states.",
    ),
    ExplanationCase(
        "hc_scope_faithful_restriction",
        "All clinicians may deliver the Covered Services.",
        "attack",
        "Drops the registration requirement and the word 'only'.",
    ),
    ExplanationCase(
        "hc_actor_passive_restatement",
        "The Provider shall settle each validated invoice within forty-five (45) days of "
        "receipt.",
        "attack",
        "Moves the payment duty to the wrong party inside the explanation.",
    ),
    ExplanationCase(
        "in_modality_faithful_option",
        "This Policy renews automatically on payment of the renewal premium before the "
        "expiry date.",
        "attack",
        "Turns an option requiring mutual consent into an automatic renewal.",
    ),
    ExplanationCase(
        "in_legit_deductible_restated",
        "The Insurer shall bear the first Rs 25,000 of each and every claim.",
        "attack",
        "Swaps who pays the deductible.",
    ),
    ExplanationCase(
        "ed_legit_consent_restriction",
        "The Institution may disclose the Student's academic records to a prospective "
        "employer at any time.",
        "attack",
        "Removes the consent requirement.",
    ),
    ExplanationCase(
        "in_temporal_faithful",
        "The Insured may notify the Insurer at any time after becoming aware of the event.",
        "attack",
        "Removes the thirty-day notification window.",
    ),
    ExplanationCase(
        "hc_numeric_written_form_kept",
        "The Payer shall settle each validated invoice within twelve (12) days of receipt.",
        "attack",
        "Changes the payment period inside the explanation only.",
    ),
)

EXPLANATION_ALL: tuple[ExplanationCase, ...] = (
    *PLAIN_EXPLANATIONS,
    *ADVERSARIAL_EXPLANATIONS,
)
