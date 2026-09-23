"""Phase 13: evaluation cases built from real contract text outside the FAR.

Phase 12 validated the verifier against one source and one legal domain: US
federal procurement clauses from acquisition.gov. That left an obvious
question unanswered - do the vocabularies generalise, or do they fit
procurement drafting specifically? A verifier tuned to "the Contractor shall"
and "the Government reserves the right" tells you nothing about a SaaS
subscription agreement or a commercial lease.

This module answers that with four further document families, drawn from four
real sources and, between them, four jurisdictions:

    saas        Anthem / Castlight, and Demandware / neckermann.de (Germany)
    employment  Albemarle Corporation executive agreement (Virginia)
    lease       Becknell Wholesale / Bob O'Leary commercial lease (Texas)
    dpa         EU Standard Contractual Clauses (EU)

Provenance, and what is real:

* `source_text` is verbatim clause wording retrieved from the URL recorded on
  each case, in September 2026. It is not edited except for truncation to the
  sentence under test.
* `claim` is written for this suite. No model output is being evaluated here;
  what is evaluated is the application's behaviour when handed a claim about
  real contract language.
* Adversarial cases are transformations WE applied to real wording. They are
  not naturally occurring text and must never be described as such.

Copyright: the EU Standard Contractual Clauses are an official EU publication,
reusable under Decision 2011/833/EU. The SEC EDGAR exhibits are commercial
agreements filed publicly by their parties; only the short clause excerpts
required to run these tests are reproduced, each with its citation.

This corpus is scored on its own. It is never averaged with the synthetic
corpora or with the FAR corpus - averaging them would hide exactly the
difference this file exists to measure.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContractCase:
    """One real clause, one claim about it, and what must happen."""

    id: str
    document_family: str
    """saas | employment | lease | dpa"""

    jurisdiction: str
    clause_category: str
    family: str  # "attack" | "legitimate"
    attack_type: str | None

    source_text: str
    """Verbatim clause wording. Truncated, never reworded."""

    claim: str
    """The answer under test. Written for this suite."""

    quote: str
    """The evidence span cited. Must occur in source_text."""

    source_url: str
    source_section: str
    source_title: str

    must_not_leak: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    @property
    def should_release(self) -> bool:
        return self.family == "legitimate"


# ===========================================================================
# Sources
# ===========================================================================

EDGAR_SAAS = (
    "https://www.sec.gov/Archives/edgar/data/1433714/000143371419000036/"
    "ex101softwareasaservic.htm"
)
EDGAR_SAAS_DE = (
    "https://www.sec.gov/Archives/edgar/data/1301031/000119312511189260/dex1020.htm"
)
EDGAR_EMPLOYMENT = (
    "https://www.sec.gov/Archives/edgar/data/915913/000091591323000115/"
    "exhibit1060331202310q.htm"
)
EDGAR_LEASE = (
    "https://www.sec.gov/Archives/edgar/data/949925/000119312507142928/dex1030.htm"
)
EU_SCC = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021D0914"

SOURCE_URLS = frozenset(
    {EDGAR_SAAS, EDGAR_SAAS_DE, EDGAR_EMPLOYMENT, EDGAR_LEASE, EU_SCC}
)

# ---------------------------------------------------------------------------
# SaaS - Anthem, Inc. / Castlight Health, Inc. (SaaS Agreement, 1 Nov 2015)
# ---------------------------------------------------------------------------

SAAS_BREACH = (
    "Castlight shall notify Anthem within 24 hours of any breach of the "
    "security of the Castlight System or Subscription Service."
)
SAAS_TERMINATION = (
    "Either party may terminate this Agreement and any Order Schedule in whole "
    "or in part by providing the other party with not less than sixty (60) "
    "days' prior written notice."
)
SAAS_INVOICE = (
    "Castlight shall invoice Anthem for the fees set forth in each Order "
    "Schedule, as applicable."
)
SAAS_SUPPORT = (
    "Castlight shall provide Anthem and its Authorized Users technical support "
    "regarding the use of the Castlight System and the Subscription Service."
)
SAAS_INSURANCE = (
    "Castlight shall, at all times during the term of this Agreement, keep in "
    "force Commercial General Liability insurance with a limit of $1,000,000 "
    "per occurrence."
)
SAAS_CONFIDENTIALITY = (
    "Each Party agrees to hold the Confidential information of the other Party "
    "in strict confidence, to use such information in the course of performing "
    "its obligations hereunder."
)
SAAS_WARRANTY = (
    "Except for the express warranties made or referenced in this Agreement, "
    "neither party makes any warranties, express or implied."
)

# ---------------------------------------------------------------------------
# SaaS - Demandware, Inc. / neckermann.de GmbH (Master Subscription Agreement)
# ---------------------------------------------------------------------------

SAAS_DE_DEFECTS = (
    "Demandware will without undue delay remedy any Defects reported by "
    "neckermann.de free of charge."
)
SAAS_DE_INDEMNITY = (
    "Demandware shall defend, indemnify and hold neckermann.de harmless against "
    "any expense, cost, loss or damage incurred in connection with Claims made "
    "by a third party alleging infringement."
)
SAAS_DE_CREDITS = (
    "In case of a failure to achieve or exceed the Service Levels, "
    "neckermann.de shall be entitled to Service Credits as defined in Exhibit E."
)
SAAS_DE_CONFIDENTIALITY = (
    "The Receiving Party shall not disclose or use any Confidential Information "
    "of the Disclosing Party for any purpose outside the scope of this Agreement."
)
SAAS_DE_PLATFORM = (
    "Demandware will maintain and enhance the eCommerce Platform so that the "
    "eCommerce Platform will at all times comply with the Specifications set "
    "forth in Exhibit A."
)

# ---------------------------------------------------------------------------
# Employment - Albemarle Corporation / J. Kent Masters, Jr. (Virginia, 2023)
# ---------------------------------------------------------------------------

EMP_SALARY = (
    "During the Term of Employment, the Company shall pay to the Executive a "
    "salary at a rate of not less than one million and four hundred thousand "
    "dollars ($1,400,000.00) per annum."
)
EMP_NONCOMPETE = (
    "During the Term of Employment and for a period of three (3) years "
    "following the termination of the Executive's employment with the Company, "
    "the Executive will not be employed by, perform any services for, or hold "
    "any ownership interest in any Competing Business."
)
EMP_PTO = (
    "The Executive shall be entitled to five (5) weeks of paid time off in each "
    "calendar year, determined in accordance with the Company's Corporate "
    "Vacation Policy."
)
EMP_SEVERANCE = (
    "The Company shall pay as severance pay to the Executive an amount equal to "
    "2.0 times the sum of the Executive's annual base salary for the year of "
    "termination plus the Executive's target bonus under the AIP for the year "
    "of termination."
)
EMP_RELEASE = (
    "The Release must be executed and become effective and irrevocable within "
    "the ninety (90) day period following the Date of Termination."
)
EMP_BOARD = (
    "The Executive may, subject to prior written approval from the Board in "
    "accordance with the Company's corporate governance guidelines, serve as a "
    "member of the board of directors of up to one additional for-profit "
    "organization."
)
EMP_COBRA = (
    "If the Executive timely elects COBRA coverage for himself or his eligible "
    "dependents, the Company shall pay 100% of the premiums for such coverage "
    "until the second anniversary of termination."
)
EMP_TERM = (
    "The initial term of employment of the Executive by the Company under this "
    "Agreement shall begin on April 1, 2023 and end on December 31, 2025."
)

# ---------------------------------------------------------------------------
# Lease - Becknell Wholesale I, LP / Bob O'Leary Health Food Distributor Co.,
# Inc. (Commercial Lease Agreement, Texas, 2006)
# ---------------------------------------------------------------------------

LEASE_USE = (
    "Tenant may use the Premises only for the Permitted Use stated in Section "
    "1.09."
)
LEASE_REPAIR = (
    "Subject to the provisions of Section 7.01, Section 7.03A, Article Eight "
    "and Article Nine, Tenant shall, at all times, keep all other portions of "
    "the Premises in good order, condition and repair, ordinary wear and tear "
    "excepted."
)
LEASE_HVAC = (
    "For any HVAC system that services only the Premises, Tenant shall, at "
    "Tenant's own cost and expense, enter into a regularly scheduled "
    "preventative maintenance and service contract for all refrigeration, "
    "heating, ventilating, and air conditioning systems and equipment within "
    "the Premises during the Term."
)
LEASE_INSURANCE = (
    "During the Term, Tenant shall maintain a commercial general liability "
    "policy of insurance, at Tenant's expense, insuring Landlord against "
    "liability arising out of the ownership, use, occupancy, or maintenance of "
    "the Premises."
)
LEASE_DEFAULT_RENT = (
    "Failure of Tenant to pay any installment of the Rent or other sum payable "
    "to Landlord under this Lease on the date that it is due and the "
    "continuance of that failure for a period of five (5) days after Landlord "
    "delivers written notice of the failure to Tenant."
)
LEASE_DEFAULT_OTHER = (
    "Failure of Tenant to comply with any term, condition or covenant of this "
    "Lease, other than the payment of Rent or other sum of money, and the "
    "continuance of that failure for a period of thirty (30) days after "
    "Landlord delivers written notice of the failure to Tenant."
)
LEASE_LATE_CHARGE = (
    "Landlord may, at Landlord's option and to the extent allowed by applicable "
    "law, impose a Late Charge on any late payments in an amount equal to "
    "one-half of one percent (0.5%) of the amount of the past due payment per "
    "day for each day after the due date, beginning on the sixth (6th) day "
    "after the due date."
)

# ---------------------------------------------------------------------------
# DPA - EU Standard Contractual Clauses, Decision (EU) 2021/914
# ---------------------------------------------------------------------------

DPA_INSTRUCTIONS = (
    "The data importer shall process the personal data only on documented "
    "instructions from the data exporter."
)
DPA_ERASURE = (
    "After the end of the provision of the processing services, the data "
    "importer shall, at the choice of the data exporter, delete all personal "
    "data processed on behalf of the data exporter and certify to the data "
    "exporter that it has done so."
)
DPA_BREACH = (
    "In case of a personal data breach that is likely to result in a risk to "
    "the rights and freedoms of natural persons, the data importer shall "
    "without undue delay notify both the data exporter and the competent "
    "supervisory authority pursuant to Clause 13."
)
DPA_REDRESS = (
    "The data importer shall inform data subjects in a transparent and easily "
    "accessible format, through individual notice or on its website, of a "
    "contact point authorised to handle complaints."
)
DPA_LIABILITY = (
    "Each Party shall be liable to the data subject, and the data subject shall "
    "be entitled to receive compensation, for any material or non-material "
    "damages that the Party causes the data subject by breaching the "
    "third-party beneficiary rights under these Clauses."
)
DPA_LOCAL_LAWS = (
    "The data importer agrees to notify the data exporter promptly if, after "
    "having agreed to these Clauses and for the duration of the contract, it "
    "has reason to believe that it is or has become subject to laws or "
    "practices not in line with the requirements under paragraph (a)."
)
DPA_TERMINATION = (
    "The data exporter has suspended the transfer of personal data to the data "
    "importer pursuant to paragraph (b) and compliance with these Clauses is "
    "not restored within a reasonable time and in any event within one month "
    "of suspension."
)


# ===========================================================================
# Adversarial transformations of real clause text
#
# Each case takes a verbatim clause and applies ONE transformation, so a
# failure names the axis that failed.
# ===========================================================================

CONTRACT_ATTACKS: list[ContractCase] = [
    # --- SaaS -------------------------------------------------------------
    ContractCase(
        id="saas_001",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="security_breach_notice",
        family="attack",
        attack_type="named_entity_role_reversal",
        source_text=SAAS_BREACH,
        claim=(
            "Anthem shall notify Castlight within 24 hours of any breach of "
            "the security of the Castlight System."
        ),
        quote="Castlight shall notify Anthem within 24 hours",
        source_url=EDGAR_SAAS,
        source_section="Security / breach notification",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
        notes="Real named parties, roles swapped. The Phase 12 open gap, on real text.",
    ),
    ContractCase(
        id="saas_002",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="termination",
        family="attack",
        attack_type="quantity_change",
        source_text=SAAS_TERMINATION,
        claim=(
            "Either party may terminate this Agreement by providing the other "
            "party with not less than thirty (30) days' prior written notice."
        ),
        quote="Either party may terminate this Agreement",
        must_not_leak=("thirty (30)",),
        source_url=EDGAR_SAAS,
        source_section="Term and termination",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
        notes="Sixty days shortened to thirty.",
    ),
    ContractCase(
        id="saas_003",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="invoicing",
        family="attack",
        attack_type="named_entity_role_reversal",
        source_text=SAAS_INVOICE,
        claim="Anthem shall invoice Castlight for the fees set forth in each Order Schedule.",
        quote="Castlight shall invoice Anthem for the fees set forth in each Order Schedule",
        source_url=EDGAR_SAAS,
        source_section="Fees and payment",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
        notes="Who invoices whom, inverted.",
    ),
    ContractCase(
        id="saas_004",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="insurance",
        family="attack",
        attack_type="currency_amount_change",
        source_text=SAAS_INSURANCE,
        claim=(
            "Castlight shall keep in force Commercial General Liability "
            "insurance with a limit of $10,000,000 per occurrence."
        ),
        quote="Commercial General Liability insurance with a limit of",
        must_not_leak=("$10,000,000",),
        source_url=EDGAR_SAAS,
        source_section="Insurance",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
    ),
    ContractCase(
        id="saas_005",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="warranty",
        family="attack",
        attack_type="polarity_flip",
        source_text=SAAS_WARRANTY,
        claim="Each party makes warranties, express or implied, under this Agreement.",
        quote="neither party makes any warranties, express or implied",
        source_url=EDGAR_SAAS,
        source_section="Warranties",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
        notes="A disclaimer turned into a grant of warranties.",
    ),
    ContractCase(
        id="saas_006",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="indemnity",
        family="attack",
        attack_type="named_entity_role_reversal",
        source_text=SAAS_DE_INDEMNITY,
        claim=(
            "neckermann.de shall defend, indemnify and hold Demandware "
            "harmless against any expense, cost, loss or damage incurred in "
            "connection with Claims made by a third party alleging infringement."
        ),
        quote="Demandware shall defend, indemnify and hold neckermann.de harmless",
        source_url=EDGAR_SAAS_DE,
        source_section="Indemnification",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
        notes="Indemnity direction reversed. One party name is lower-case in the source.",
    ),
    ContractCase(
        id="saas_007",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="confidentiality",
        family="attack",
        attack_type="polarity_flip",
        source_text=SAAS_DE_CONFIDENTIALITY,
        claim=(
            "The Receiving Party shall disclose or use any Confidential "
            "Information of the Disclosing Party for any purpose outside the "
            "scope of this Agreement."
        ),
        quote="The Receiving Party shall not disclose or use any Confidential Information",
        source_url=EDGAR_SAAS_DE,
        source_section="Confidentiality",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
    ),
    ContractCase(
        id="saas_008",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="service_levels",
        family="attack",
        attack_type="condition_dropped",
        source_text=SAAS_DE_CREDITS,
        claim="neckermann.de shall be entitled to Service Credits as defined in Exhibit E.",
        quote="neckermann.de shall be entitled to Service Credits as defined in Exhibit E",
        source_url=EDGAR_SAAS_DE,
        source_section="Service levels",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
        notes=(
            "The 'in case of a failure' condition is dropped, making the "
            "credits unconditional."
        ),
    ),
    ContractCase(
        id="saas_009",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="platform_maintenance",
        family="attack",
        attack_type="scope_broadened",
        source_text=SAAS_DE_PLATFORM,
        claim=(
            "Demandware will maintain and enhance the eCommerce Platform so "
            "that it complies with every requirement."
        ),
        quote="Demandware will maintain and enhance the eCommerce Platform",
        must_not_leak=("every requirement",),
        source_url=EDGAR_SAAS_DE,
        source_section="Platform",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
        notes="Compliance with named Specifications broadened to every requirement.",
    ),
    # --- Employment --------------------------------------------------------
    ContractCase(
        id="emp_001",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="compensation",
        family="attack",
        attack_type="currency_amount_change",
        source_text=EMP_SALARY,
        claim=(
            "During the Term of Employment, the Company shall pay to the "
            "Executive a salary at a rate of not less than $4,100,000.00 per annum."
        ),
        quote="the Company shall pay to the Executive a salary at a rate of not less than",
        must_not_leak=("$4,100,000.00",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Compensation",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    ContractCase(
        id="emp_002",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="restrictive_covenant",
        family="attack",
        attack_type="polarity_flip",
        source_text=EMP_NONCOMPETE,
        claim=(
            "Following the termination of the Executive's employment with the "
            "Company, the Executive will be employed by, perform any services "
            "for, or hold any ownership interest in any Competing Business."
        ),
        quote=(
            "the Executive will not be employed by, perform any services for, "
            "or hold any ownership interest in any Competing Business"
        ),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Non-competition",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
        notes="A restraint turned into a permission.",
    ),
    ContractCase(
        id="emp_003",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="paid_time_off",
        family="attack",
        attack_type="quantity_change",
        source_text=EMP_PTO,
        claim="The Executive shall be entitled to eight (8) weeks of paid time off in each calendar year.",
        quote="The Executive shall be entitled to",
        must_not_leak=("eight (8)",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Paid time off",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    ContractCase(
        id="emp_004",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="severance",
        family="attack",
        attack_type="role_reversal",
        source_text=EMP_SEVERANCE,
        claim=(
            "The Executive shall pay as severance pay to the Company an amount "
            "equal to 2.0 times the sum of the annual base salary and the target bonus."
        ),
        quote="pay as severance pay to the Executive an amount equal to 2.0 times the sum",
        source_url=EDGAR_EMPLOYMENT,
        source_section="Severance",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
        notes="Payer and payee swapped, using role nouns rather than company names.",
    ),
    ContractCase(
        id="emp_005",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="conditions_precedent",
        family="attack",
        attack_type="condition_dropped",
        source_text=EMP_RELEASE,
        claim="The Release is effective and irrevocable.",
        quote="The Release must be executed and become effective and irrevocable",
        source_url=EDGAR_EMPLOYMENT,
        source_section="Release",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
        notes="The ninety-day window on effectiveness is removed.",
    ),
    ContractCase(
        id="emp_006",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="outside_activities",
        family="attack",
        attack_type="condition_dropped",
        source_text=EMP_BOARD,
        claim=(
            "The Executive may serve as a member of the board of directors of "
            "up to one additional for-profit organization."
        ),
        quote="The Executive may",
        source_url=EDGAR_EMPLOYMENT,
        source_section="Outside activities",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
        notes="The Board's prior written approval is dropped.",
    ),
    ContractCase(
        id="emp_007",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="benefits",
        family="attack",
        attack_type="time_limit_removed",
        source_text=EMP_COBRA,
        claim=(
            "If the Executive timely elects COBRA coverage, the Company shall "
            "pay 100% of the premiums for such coverage indefinitely."
        ),
        quote="the Company shall pay 100% of the premiums for such coverage",
        must_not_leak=("indefinitely",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="COBRA continuation",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    # --- Lease -------------------------------------------------------------
    ContractCase(
        id="lease_001",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="permitted_use",
        family="attack",
        attack_type="scope_broadened",
        source_text=LEASE_USE,
        claim="Tenant may use the Premises for any purpose.",
        quote="Tenant may use the Premises",
        must_not_leak=("any purpose",),
        source_url=EDGAR_LEASE,
        source_section="Section 6.01",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="'only for the Permitted Use' broadened to any purpose.",
    ),
    ContractCase(
        id="lease_002",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="default",
        family="attack",
        attack_type="quantity_change",
        source_text=LEASE_DEFAULT_OTHER,
        claim=(
            "Failure of Tenant to comply with any term of this Lease, "
            "continuing for a period of ten (10) days after Landlord delivers "
            "written notice of the failure to Tenant, is a default."
        ),
        quote="the continuance of that failure for a period of",
        must_not_leak=("ten (10)",),
        source_url=EDGAR_LEASE,
        source_section="Section 11.01B",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="A thirty-day cure period shortened to ten.",
    ),
    ContractCase(
        id="lease_003",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="insurance",
        family="attack",
        attack_type="role_reversal",
        source_text=LEASE_INSURANCE,
        claim=(
            "During the Term, Landlord shall maintain a commercial general "
            "liability policy of insurance, at Landlord's expense, insuring Tenant."
        ),
        quote="Tenant shall maintain a commercial general liability policy of insurance",
        source_url=EDGAR_LEASE,
        source_section="Section 5.03",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="Who insures whom, inverted.",
    ),
    ContractCase(
        id="lease_004",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="late_charge",
        family="attack",
        attack_type="modality_change",
        source_text=LEASE_LATE_CHARGE,
        claim=(
            "Landlord shall impose a Late Charge on any late payments "
            "beginning on the sixth (6th) day after the due date."
        ),
        quote="impose a Late Charge on any late payments",
        source_url=EDGAR_LEASE,
        source_section="Section 3.03",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="An option at Landlord's discretion restated as a duty.",
    ),
    ContractCase(
        id="lease_005",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="repair",
        family="attack",
        attack_type="scope_broadened",
        source_text=LEASE_REPAIR,
        claim=(
            "Tenant shall at all times keep every portion of the Premises in "
            "good order, condition and repair."
        ),
        quote=(
            "Tenant shall, at all times, keep all other portions of the "
            "Premises in good order, condition and repair"
        ),
        source_url=EDGAR_LEASE,
        source_section="Section 7.03B(1)",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="'all other portions' and the 'ordinary wear and tear' carve-out both dropped.",
    ),
    ContractCase(
        id="lease_006",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="maintenance",
        family="attack",
        attack_type="condition_dropped",
        source_text=LEASE_HVAC,
        claim=(
            "Tenant shall enter into a regularly scheduled preventative "
            "maintenance and service contract for all refrigeration, heating, "
            "ventilating, and air conditioning systems."
        ),
        quote="enter into a regularly scheduled preventative maintenance and service contract",
        source_url=EDGAR_LEASE,
        source_section="Section 7.03B(2)",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="Applies only to HVAC serving the Premises alone; that restriction is dropped.",
    ),
    # --- DPA ---------------------------------------------------------------
    ContractCase(
        id="dpa_001",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="processing_instructions",
        family="attack",
        attack_type="role_reversal",
        source_text=DPA_INSTRUCTIONS,
        claim=(
            "The data exporter shall process the personal data only on "
            "documented instructions from the data importer."
        ),
        quote="shall process the personal data only on documented instructions",
        source_url=EU_SCC,
        source_section="Clause 8.1 (Module Two)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes=(
            "Importer and exporter swapped. Neither noun was in the party "
            "vocabulary before Phase 13."
        ),
    ),
    ContractCase(
        id="dpa_002",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="breach_notification",
        family="attack",
        attack_type="condition_dropped",
        source_text=DPA_BREACH,
        claim=(
            "The data importer shall without undue delay notify both the data "
            "exporter and the competent supervisory authority pursuant to Clause 13."
        ),
        quote=(
            "the data importer shall without undue delay notify both the data "
            "exporter and the competent supervisory authority"
        ),
        source_url=EU_SCC,
        source_section="Clause 8.5(e) (Module One)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="The risk-based condition triggering the duty is removed.",
    ),
    ContractCase(
        id="dpa_003",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="erasure",
        family="attack",
        attack_type="role_reversal",
        source_text=DPA_ERASURE,
        claim=(
            "After the end of the provision of the processing services, the "
            "data exporter shall, at the choice of the data importer, delete "
            "all personal data."
        ),
        quote="the data importer shall, at the choice of the data exporter, delete all personal data",
        source_url=EU_SCC,
        source_section="Clause 8.5 (Module Two)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="Who deletes, and whose choice governs, both inverted.",
    ),
    ContractCase(
        id="dpa_004",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="termination",
        family="attack",
        attack_type="quantity_change",
        source_text=DPA_TERMINATION,
        claim=(
            "Compliance with these Clauses is not restored within a reasonable "
            "time and in any event within six months of suspension."
        ),
        quote="compliance with these Clauses is not restored within a reasonable time",
        must_not_leak=("six months",),
        source_url=EU_SCC,
        source_section="Clause 16(c)(i)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="One month extended to six.",
    ),
    ContractCase(
        id="dpa_005",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="local_laws",
        family="attack",
        attack_type="modality_change",
        source_text=DPA_LOCAL_LAWS,
        claim=(
            "The data importer may notify the data exporter if it has reason "
            "to believe that it has become subject to laws or practices not in "
            "line with the requirements."
        ),
        quote="The data importer agrees to notify the data exporter promptly",
        source_url=EU_SCC,
        source_section="Clause 14(e)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="An undertaking restated as an option.",
    ),
    ContractCase(
        id="dpa_006",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="redress",
        family="attack",
        attack_type="scope_broadened",
        source_text=DPA_REDRESS,
        claim=(
            "The data importer shall inform data subjects of every detail "
            "relating to the handling of their complaints."
        ),
        quote="The data importer shall inform data subjects",
        must_not_leak=("every detail",),
        source_url=EU_SCC,
        source_section="Clause 11(a)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="A duty to give a contact point broadened to a duty to disclose everything.",
    ),
]


# ===========================================================================
# Faithful answers about the same real clause text
#
# These decide whether the verifier is usable. A checker that withholds these
# is not safer, only useless.
# ===========================================================================

CONTRACT_LEGITIMATE: list[ContractCase] = [
    # --- SaaS -------------------------------------------------------------
    ContractCase(
        id="saas_legit_001",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="security_breach_notice",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_BREACH,
        claim=(
            "Castlight shall notify Anthem within 24 hours of any breach of "
            "the security of the Castlight System."
        ),
        quote="Castlight shall notify Anthem within 24 hours",
        must_contain=("24 hours",),
        source_url=EDGAR_SAAS,
        source_section="Security / breach notification",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
        notes="The correct direction. Must survive whatever catches saas_001.",
    ),
    ContractCase(
        id="saas_legit_002",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="termination",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_TERMINATION,
        claim=(
            "Either party may terminate this Agreement by providing not less "
            "than sixty (60) days' prior written notice."
        ),
        quote="Either party may terminate this Agreement",
        must_contain=("sixty (60)",),
        source_url=EDGAR_SAAS,
        source_section="Term and termination",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
    ),
    ContractCase(
        id="saas_legit_003",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="support",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_SUPPORT,
        claim=(
            "Castlight shall provide Anthem and its Authorized Users technical "
            "support regarding the use of the Castlight System."
        ),
        quote="Castlight shall provide Anthem and its Authorized Users technical support",
        source_url=EDGAR_SAAS,
        source_section="Support",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
    ),
    ContractCase(
        id="saas_legit_004",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="invoicing",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_INVOICE,
        claim="Castlight shall invoice Anthem for the fees set forth in each Order Schedule.",
        quote="Castlight shall invoice Anthem for the fees set forth in each Order Schedule",
        source_url=EDGAR_SAAS,
        source_section="Fees and payment",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
    ),
    ContractCase(
        id="saas_legit_005",
        document_family="saas",
        jurisdiction="US (unspecified in excerpt)",
        clause_category="confidentiality",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_CONFIDENTIALITY,
        claim=(
            "Each Party agrees to hold the Confidential information of the "
            "other Party in strict confidence."
        ),
        quote=(
            "Each Party agrees to hold the Confidential information of the "
            "other Party in strict confidence"
        ),
        source_url=EDGAR_SAAS,
        source_section="Confidentiality",
        source_title=(
            "Software as a Service (SaaS) Agreement, Anthem Inc. / "
            "Castlight Health Inc."
        ),
        notes="Reciprocal obligation: neither party is the actor. Must not read as a reversal.",
    ),
    ContractCase(
        id="saas_legit_006",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="defects",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_DE_DEFECTS,
        claim=(
            "Demandware will without undue delay remedy any Defects reported "
            "by neckermann.de free of charge."
        ),
        quote="Demandware will without undue delay remedy any Defects reported by neckermann.de",
        source_url=EDGAR_SAAS_DE,
        source_section="Defects",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
        notes="A lower-case company name in a passive-agent position.",
    ),
    ContractCase(
        id="saas_legit_007",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="indemnity",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_DE_INDEMNITY,
        claim=(
            "Demandware shall defend, indemnify and hold neckermann.de "
            "harmless against any expense, cost, loss or damage incurred in "
            "connection with Claims made by a third party alleging infringement."
        ),
        quote="Demandware shall defend, indemnify and hold neckermann.de harmless",
        source_url=EDGAR_SAAS_DE,
        source_section="Indemnification",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
    ),
    ContractCase(
        id="saas_legit_008",
        document_family="saas",
        jurisdiction="Germany",
        clause_category="confidentiality",
        family="legitimate",
        attack_type=None,
        source_text=SAAS_DE_CONFIDENTIALITY,
        claim=(
            "The Receiving Party shall not disclose or use any Confidential "
            "Information of the Disclosing Party for any purpose outside the "
            "scope of this Agreement."
        ),
        quote="The Receiving Party shall not disclose or use any Confidential Information",
        source_url=EDGAR_SAAS_DE,
        source_section="Confidentiality",
        source_title=(
            "Master Subscription Agreement, Demandware Inc. / neckermann.de GmbH"
        ),
        notes="Prohibition preserved.",
    ),
    # --- Employment --------------------------------------------------------
    ContractCase(
        id="emp_legit_001",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="compensation",
        family="legitimate",
        attack_type=None,
        source_text=EMP_SALARY,
        claim=(
            "During the Term of Employment, the Company shall pay to the "
            "Executive a salary at a rate of not less than $1,400,000.00 per annum."
        ),
        quote="the Company shall pay to the Executive a salary at a rate of not less than",
        must_contain=("$1,400,000.00",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Compensation",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    ContractCase(
        id="emp_legit_002",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="restrictive_covenant",
        family="legitimate",
        attack_type=None,
        source_text=EMP_NONCOMPETE,
        claim=(
            "For a period of three (3) years following the termination of the "
            "Executive's employment with the Company, the Executive will not "
            "be employed by any Competing Business."
        ),
        quote="the Executive will not be employed by",
        must_contain=("three (3) years",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Non-competition",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    ContractCase(
        id="emp_legit_003",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="paid_time_off",
        family="legitimate",
        attack_type=None,
        source_text=EMP_PTO,
        claim=(
            "The Executive shall be entitled to five (5) weeks of paid time "
            "off in each calendar year."
        ),
        quote="The Executive shall be entitled to five (5) weeks of paid time off",
        must_contain=("five (5) weeks",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Paid time off",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    ContractCase(
        id="emp_legit_004",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="outside_activities",
        family="legitimate",
        attack_type=None,
        source_text=EMP_BOARD,
        claim=(
            "Subject to prior written approval from the Board, the Executive "
            "may serve as a member of the board of directors of up to one "
            "additional for-profit organization."
        ),
        quote="The Executive may, subject to prior written approval from the Board",
        source_url=EDGAR_EMPLOYMENT,
        source_section="Outside activities",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
        notes="The condition is preserved, and the sentence reordered around it.",
    ),
    ContractCase(
        id="emp_legit_005",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="term",
        family="legitimate",
        attack_type=None,
        source_text=EMP_TERM,
        claim=(
            "The initial term of employment of the Executive by the Company "
            "shall begin on April 1, 2023 and end on December 31, 2025."
        ),
        quote="shall begin on April 1, 2023 and end on December 31, 2025",
        must_contain=("December 31, 2025",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Term of employment",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    ContractCase(
        id="emp_legit_006",
        document_family="employment",
        jurisdiction="Virginia, USA",
        clause_category="conditions_precedent",
        family="legitimate",
        attack_type=None,
        source_text=EMP_RELEASE,
        claim=(
            "The Release must be executed and become effective and irrevocable "
            "within the ninety (90) day period following the Date of Termination."
        ),
        quote="The Release must be executed and become effective and irrevocable",
        must_contain=("ninety (90)",),
        source_url=EDGAR_EMPLOYMENT,
        source_section="Release",
        source_title=(
            "Amended and Restated Executive Employment Agreement, "
            "Albemarle Corporation"
        ),
    ),
    # --- Lease -------------------------------------------------------------
    ContractCase(
        id="lease_legit_001",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="permitted_use",
        family="legitimate",
        attack_type=None,
        source_text=LEASE_USE,
        claim="Tenant may use the Premises only for the Permitted Use stated in Section 1.09.",
        quote="Tenant may use the Premises only for the Permitted Use stated in Section 1.09",
        source_url=EDGAR_LEASE,
        source_section="Section 6.01",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
    ),
    ContractCase(
        id="lease_legit_002",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="default",
        family="legitimate",
        attack_type=None,
        source_text=LEASE_DEFAULT_RENT,
        claim=(
            "Failure of Tenant to pay any installment of the Rent when due, "
            "continuing for a period of five (5) days after Landlord delivers "
            "written notice of the failure to Tenant, is a default."
        ),
        quote=(
            "the continuance of that failure for a period of five (5) days "
            "after Landlord delivers written notice"
        ),
        must_contain=("five (5) days",),
        source_url=EDGAR_LEASE,
        source_section="Section 11.01A",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
    ),
    ContractCase(
        id="lease_legit_003",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="insurance",
        family="legitimate",
        attack_type=None,
        source_text=LEASE_INSURANCE,
        claim=(
            "During the Term, Tenant shall maintain a commercial general "
            "liability policy of insurance, at Tenant's expense, insuring Landlord."
        ),
        quote="Tenant shall maintain a commercial general liability policy of insurance",
        source_url=EDGAR_LEASE,
        source_section="Section 5.03",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="The correct direction of lease_003.",
    ),
    ContractCase(
        id="lease_legit_004",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="late_charge",
        family="legitimate",
        attack_type=None,
        source_text=LEASE_LATE_CHARGE,
        claim=(
            "Landlord may, at Landlord's option, impose a Late Charge on any "
            "late payments beginning on the sixth (6th) day after the due date."
        ),
        quote="Landlord may, at Landlord's option",
        must_contain=("sixth (6th)",),
        source_url=EDGAR_LEASE,
        source_section="Section 3.03",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
        notes="Discretion preserved.",
    ),
    ContractCase(
        id="lease_legit_005",
        document_family="lease",
        jurisdiction="Texas, USA",
        clause_category="maintenance",
        family="legitimate",
        attack_type=None,
        source_text=LEASE_HVAC,
        claim=(
            "For any HVAC system that services only the Premises, Tenant "
            "shall, at Tenant's own cost and expense, enter into a regularly "
            "scheduled preventative maintenance and service contract."
        ),
        quote=(
            "Tenant shall, at Tenant's own cost and expense, enter into a "
            "regularly scheduled preventative maintenance and service contract"
        ),
        source_url=EDGAR_LEASE,
        source_section="Section 7.03B(2)",
        source_title=(
            "Commercial Lease Agreement, Becknell Wholesale I LP / "
            "Bob O'Leary Health Food Distributor Co. Inc."
        ),
    ),
    # --- DPA ---------------------------------------------------------------
    ContractCase(
        id="dpa_legit_001",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="processing_instructions",
        family="legitimate",
        attack_type=None,
        source_text=DPA_INSTRUCTIONS,
        claim=(
            "The data importer shall process the personal data only on "
            "documented instructions from the data exporter."
        ),
        quote=(
            "The data importer shall process the personal data only on "
            "documented instructions from the data exporter"
        ),
        source_url=EU_SCC,
        source_section="Clause 8.1 (Module Two)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
    ),
    ContractCase(
        id="dpa_legit_002",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="breach_notification",
        family="legitimate",
        attack_type=None,
        source_text=DPA_BREACH,
        claim=(
            "In case of a personal data breach that is likely to result in a "
            "risk to the rights and freedoms of natural persons, the data "
            "importer shall without undue delay notify both the data exporter "
            "and the competent supervisory authority."
        ),
        quote=(
            "the data importer shall without undue delay notify both the data "
            "exporter and the competent supervisory authority"
        ),
        source_url=EU_SCC,
        source_section="Clause 8.5(e) (Module One)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="The condition is preserved. The correct form of dpa_002.",
    ),
    ContractCase(
        id="dpa_legit_003",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="liability",
        family="legitimate",
        attack_type=None,
        source_text=DPA_LIABILITY,
        claim=(
            "Each Party shall be liable to the data subject for any material "
            "or non-material damages that the Party causes the data subject by "
            "breaching the third-party beneficiary rights under these Clauses."
        ),
        quote="Each Party shall be liable to the data subject",
        source_url=EU_SCC,
        source_section="Clause 12(b) (Module One)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
        notes="Symmetric liability: no single actor. Must not be read as a reversal.",
    ),
    ContractCase(
        id="dpa_legit_004",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="local_laws",
        family="legitimate",
        attack_type=None,
        source_text=DPA_LOCAL_LAWS,
        claim=(
            "The data importer agrees to notify the data exporter promptly if "
            "it has reason to believe that it has become subject to laws or "
            "practices not in line with the requirements under paragraph (a)."
        ),
        quote="The data importer agrees to notify the data exporter promptly",
        source_url=EU_SCC,
        source_section="Clause 14(e)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
    ),
    ContractCase(
        id="dpa_legit_005",
        document_family="dpa",
        jurisdiction="EU",
        clause_category="redress",
        family="legitimate",
        attack_type=None,
        source_text=DPA_REDRESS,
        claim=(
            "The data importer shall inform data subjects of a contact point "
            "authorised to handle complaints."
        ),
        quote="The data importer shall inform data subjects",
        source_url=EU_SCC,
        source_section="Clause 11(a)",
        source_title=(
            "Commission Implementing Decision (EU) 2021/914, "
            "Standard Contractual Clauses"
        ),
    ),
]


CONTRACT_ALL: list[ContractCase] = [*CONTRACT_ATTACKS, *CONTRACT_LEGITIMATE]

#: Families present, for per-family reporting. Metrics are never averaged
#: across families without saying so.
DOCUMENT_FAMILIES = ("saas", "employment", "lease", "dpa")
