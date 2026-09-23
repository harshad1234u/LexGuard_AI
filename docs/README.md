# PromptWars Legal AI — Documentation Pack

**Hackathon problem statement:** *AI for Legal Assistance & Access*
**Status:** Phases 1–15 complete. MVP demo-ready with documented limitations.

This pack describes the system **as built**. Where something was planned and
not built, the document says so rather than leaving the plan in place.

## Documents

| # | File | What it covers |
|---|---|---|
| 01 | `01_PRD.md` | Product positioning, problem, users, the MVP as implemented, what is not implemented |
| 02 | `02_ARCHITECTURE.md` | The as-built architecture, the workflow graph, and the ADRs |
| 03 | `03_AI_AGENT_SPEC.md` | Orchestration, the model's contract, and why the model has no tools |
| 04 | `04_SECURITY_GROUNDING.md` | Threat model, grounding policy, the semantic axes, the limitation registry, the security findings |
| 05 | `05_IMPLEMENTATION_PLAN.md` | The delivered Phase 1–15 record |
| 06 | `06_EVALUATION_PLAN.md` | Evaluation method, the seven corpora, and the measured results |
| 07 | `07_API_SPEC.md` | The API contract, and who decided each field a client sees |
| 08 | `08_REPO_STRUCTURE.md` | The actual repository tree and the dependency rules |
| 09 | `09_DECISIONS.md` | Frozen decisions, Phases 1–15, including what was measured and refused |
| 10 | `10_PHASE_13_REPORT.md` | Phase 13: cross-domain validation and named-entity role safety |
| 11 | `11_PROMPTWARS_ALIGNMENT.md` | **Alignment with the official problem statement** |

Phase reports for the two most recent phases live at the repository root:
`PHASE_14_REPORT.md` and `PHASE_15_REPORT.md`.

## Where to start

- **Evaluating this project against the problem statement?** → `11_PROMPTWARS_ALIGNMENT.md`
- **Want the technical argument?** → `04_SECURITY_GROUNDING.md` §7a–§7b
- **Want to know what is honestly not done?** → `01_PRD.md` §5–§6, and
  `PHASE_15_REPORT.md` §11 and §13

## Product positioning

> An evidence-grounded GenAI legal document intelligence system that helps
> users understand complex legal documents, identify important clauses and
> obligations, and ask questions based on uploaded documents, while
> independently verifying AI-generated findings against document evidence
> before release.

## The differentiator

> **The LLM interprets the document; the application independently verifies
> what the LLM says.**

## Primary architecture

```text
React + Vite + TypeScript + Tailwind
        ↓
      FastAPI
        ↓
LangChain / LangGraph
        ↓
NVIDIA Hosted API → Nemotron 3 Nano Omni 30B-A3B
        ↓
Structured Model Output
        ↓
Deterministic Evidence Verification
        ↓
Semantic Verification
        ↓
Injection / Security Checks
        ↓
Central Output Policy
        ↓
Released User Output
```

## Key invariant

No factual claim is presented as verified unless it can be grounded in the
uploaded document and passes application-level verification.

## What this is not

Not an AI lawyer, not a replacement for legal advice, not legally
authoritative, not guaranteed to be legally correct, and not production-ready.
This system provides **legal information** and **document understanding**.
