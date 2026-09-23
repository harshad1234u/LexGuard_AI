"""Phase 13: definitions, defined terms and cross-references.

A large share of what a contract means is not in the clause you are reading.
"Tenant may use the Premises only for the Permitted Use stated in Section 1.09"
tells you nothing about what the Permitted Use is, and a model asked "what can
the tenant do with the property?" has two honest options: quote the pointer and
say the substance is elsewhere, or decline. It has one dishonest option, which
is to invent a plausible Permitted Use, and that is the failure this corpus
exists to detect.

The required behaviour, from the Phase 13 brief:

    1. Do not silently invent the meaning of an unresolved definition.
    2. Do not release a claim whose meaning depends on unavailable text.
    3. Mark unresolved references explicitly.
    4. Preserve the original quote and its location.
    5. Distinguish verified / partially verified / unverified / rejected /
       withheld-for-unresolved-reference.

Some source text here is real - the lease and DPA clauses carry their citation
- and some is written for this suite where a specific shape was needed
(contradictory definitions, a reference to a section that does not exist).
Synthetic cases say so in `provenance`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DefinitionCase:
    id: str
    construction: str
    family: str  # "attack" | "legitimate"
    provenance: str  # "real" | "synthetic"
    page_text: str
    claim: str
    quote: str
    source: str = ""
    must_not_leak: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    @property
    def should_release(self) -> bool:
        return self.family == "legitimate"


EDGAR_LEASE = (
    "https://www.sec.gov/Archives/edgar/data/949925/000119312507142928/dex1030.htm"
)
EU_SCC = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32021D0914"


# ===========================================================================
# Claims that lean on text the reader was never given
# ===========================================================================

DEFINITION_ATTACKS: list[DefinitionCase] = [
    DefinitionCase(
        id="def_permitted_use_invented",
        construction="defined term, substance elsewhere",
        family="attack",
        provenance="real",
        source=f"Commercial Lease Agreement, Section 6.01 - {EDGAR_LEASE}",
        page_text="Tenant may use the Premises only for the Permitted Use stated in Section 1.09.",
        claim="Tenant may use the Premises for any lawful business purpose.",
        quote="Tenant may use the Premises only for the Permitted Use",
        must_not_leak=("any lawful business purpose",),
        notes="Section 1.09 is not on this page. The Permitted Use is invented.",
    ),
    DefinitionCase(
        id="def_meaning_given_elsewhere",
        construction="'has the meaning given in'",
        family="attack",
        provenance="synthetic",
        page_text=(
            "\"Confidential Information\" has the meaning given in Schedule 2 of "
            "this agreement."
        ),
        claim=(
            "Confidential Information means all technical and commercial "
            "information disclosed by either party."
        ),
        quote="\"Confidential Information\" has the meaning given in Schedule 2",
        must_not_leak=("all technical and commercial information",),
        notes="The clause establishes that a definition exists, not what it says.",
    ),
    DefinitionCase(
        id="def_subject_to_section_dropped",
        construction="'subject to Section ...'",
        family="attack",
        provenance="synthetic",
        page_text=(
            "Subject to Section 9.4, the Supplier shall replace defective goods "
            "at its own cost."
        ),
        claim="The Supplier shall replace defective goods at its own cost.",
        quote="the Supplier shall replace defective goods at its own cost",
        notes=(
            "Section 9.4 may remove the obligation entirely. Dropping the "
            "qualifier states an unconditional duty the document does not."
        ),
    ),
    DefinitionCase(
        id="def_except_as_provided_dropped",
        construction="'except as provided under'",
        family="attack",
        provenance="synthetic",
        page_text=(
            "Except as provided under Article 12, the Licensee shall pay royalties "
            "quarterly."
        ),
        claim="The Licensee shall pay royalties quarterly.",
        quote="the Licensee shall pay royalties quarterly",
        notes="The carve-out in Article 12 is discarded.",
    ),
    DefinitionCase(
        id="def_schedule_contents_asserted",
        construction="schedule contents asserted",
        family="attack",
        provenance="synthetic",
        page_text=(
            "The fees payable under this agreement are set out in Schedule 1."
        ),
        claim="The fees payable under this agreement are 15,000 per month.",
        quote="The fees payable under this agreement are set out in Schedule 1",
        must_not_leak=("15,000",),
        notes="A figure asserted from a schedule that is not in evidence.",
    ),
    DefinitionCase(
        id="def_missing_section_asserted",
        construction="reference to a section not in the document",
        family="attack",
        provenance="synthetic",
        page_text=(
            "Termination rights are governed by Section 22, which forms part of "
            "this agreement."
        ),
        claim="Either party may terminate on 30 days' notice under Section 22.",
        quote="Termination rights are governed by Section 22",
        must_not_leak=("30 days",),
        notes=(
            "Section 22 is referenced and absent. The claim states its contents "
            "anyway, complete with a notice period from nowhere."
        ),
    ),
    DefinitionCase(
        id="def_contradictory_definitions",
        construction="contradictory definitions",
        family="attack",
        provenance="synthetic",
        page_text=(
            "In Part A, \"Business Day\" means a day on which banks are open in "
            "London. In Part B, \"Business Day\" means any day except a Saturday "
            "or Sunday."
        ),
        claim="A Business Day is any day on which banks are open in London.",
        quote="\"Business Day\" means a day on which banks are open in London",
        notes=(
            "Two definitions of one term. Asserting either as THE definition "
            "overstates what the document settles. Recorded whether or not it "
            "is currently detected - see the report."
        ),
    ),
    DefinitionCase(
        id="def_undefined_term_given_meaning",
        construction="undefined term",
        family="attack",
        provenance="synthetic",
        page_text="The Contractor shall deliver the Key Deliverables before the Long Stop Date.",
        claim="The Long Stop Date is 31 December 2026.",
        quote="the Key Deliverables before the Long Stop Date",
        must_not_leak=("31 December 2026",),
        notes="A capitalised term the page never defines, given a date.",
    ),
    DefinitionCase(
        id="def_cross_page_reference",
        construction="cross-page reference",
        family="attack",
        provenance="real",
        source=f"EU SCC Clause 8.5(e) - {EU_SCC}",
        page_text=(
            "In case of a personal data breach, the data importer shall without "
            "undue delay notify both the data exporter and the competent "
            "supervisory authority pursuant to Clause 13."
        ),
        claim=(
            "The data importer shall notify every supervisory authority in the "
            "Union of any personal data breach."
        ),
        quote="the data importer shall without undue delay notify",
        must_not_leak=("every supervisory authority in the Union",),
        notes="Clause 13 governs the manner of notification and is not on the page.",
    ),
]


# ===========================================================================
# Answers that correctly stay on the pointer
# ===========================================================================

DEFINITION_LEGITIMATE: list[DefinitionCase] = [
    DefinitionCase(
        id="def_legit_reports_the_pointer",
        construction="defined term, pointer reported",
        family="legitimate",
        provenance="real",
        source=f"Commercial Lease Agreement, Section 6.01 - {EDGAR_LEASE}",
        page_text="Tenant may use the Premises only for the Permitted Use stated in Section 1.09.",
        claim="Tenant may use the Premises only for the Permitted Use stated in Section 1.09.",
        quote="Tenant may use the Premises only for the Permitted Use stated in Section 1.09",
        must_contain=("Section 1.09",),
        notes="Reports the restriction and where its content lives. The right answer.",
    ),
    DefinitionCase(
        id="def_legit_condition_preserved",
        construction="'subject to Section ...' preserved",
        family="legitimate",
        provenance="synthetic",
        page_text=(
            "Subject to Section 9.4, the Supplier shall replace defective goods "
            "at its own cost."
        ),
        claim=(
            "Subject to Section 9.4, the Supplier shall replace defective goods "
            "at its own cost."
        ),
        must_contain=("Section 9.4",),
        quote="Subject to Section 9.4, the Supplier shall replace defective goods",
    ),
    DefinitionCase(
        id="def_legit_exception_preserved",
        construction="'except as provided under' preserved",
        family="legitimate",
        provenance="synthetic",
        page_text=(
            "Except as provided under Article 12, the Licensee shall pay royalties "
            "quarterly."
        ),
        claim=(
            "Except as provided under Article 12, the Licensee shall pay royalties "
            "quarterly."
        ),
        quote="Except as provided under Article 12, the Licensee shall pay royalties quarterly",
        must_contain=("Article 12",),
    ),
    DefinitionCase(
        id="def_legit_schedule_pointer",
        construction="schedule pointer reported",
        family="legitimate",
        provenance="synthetic",
        page_text="The fees payable under this agreement are set out in Schedule 1.",
        claim="The fees payable under this agreement are set out in Schedule 1.",
        quote="The fees payable under this agreement are set out in Schedule 1",
        must_contain=("Schedule 1",),
        notes="Says where the fees are without saying what they are.",
    ),
    DefinitionCase(
        id="def_legit_definition_on_the_page",
        construction="definition present in evidence",
        family="legitimate",
        provenance="synthetic",
        page_text=(
            "\"Business Day\" means any day other than a Saturday, Sunday or "
            "public holiday in England."
        ),
        claim=(
            "\"Business Day\" means any day other than a Saturday, Sunday or "
            "public holiday in England."
        ),
        quote="\"Business Day\" means any day other than a Saturday, Sunday or public holiday",
        notes="The definition IS the evidence here, so stating it is supported.",
    ),
    DefinitionCase(
        id="def_legit_real_clause_reference_kept",
        construction="cross-reference kept",
        family="legitimate",
        provenance="real",
        source=f"EU SCC Clause 8.5(e) - {EU_SCC}",
        page_text=(
            "In case of a personal data breach, the data importer shall without "
            "undue delay notify both the data exporter and the competent "
            "supervisory authority pursuant to Clause 13."
        ),
        claim=(
            "In case of a personal data breach, the data importer shall without "
            "undue delay notify both the data exporter and the competent "
            "supervisory authority pursuant to Clause 13."
        ),
        quote=(
            "the data importer shall without undue delay notify both the data "
            "exporter and the competent supervisory authority"
        ),
        must_contain=("Clause 13",),
    ),
]

DEFINITION_ALL: list[DefinitionCase] = [*DEFINITION_ATTACKS, *DEFINITION_LEGITIMATE]
