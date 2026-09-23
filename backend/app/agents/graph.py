"""The controlled analysis workflow.

    validate -> ingest -> coverage_gate -> document_map -> model -> verify -> output_gate

A state machine, not an autonomous agent: the sequence is fixed, the model
occupies exactly one node, and it chooses nothing about its own control flow.
It cannot call a tool, revisit a stage, or decide it has read enough.

Two routing rules give the graph its safety properties:

* After every node, a failure ends the run. A node that recorded an error is
  never followed by another node working on unusable state.
* After `coverage_gate`, the run continues only if coverage is complete. The
  model node is unreachable otherwise - the gate is a property of the graph's
  edges, not a check the model node performs on itself and could lose.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    analyze_node,
    build_document_map_node,
    coverage_gate_node,
    ingest_node,
    output_gate_node,
    validate_node,
    verify_node,
)
from app.agents.state import AnalysisState, has_failed
from app.models.provider import ModelProvider

# Node names, used by the graph and asserted in tests.
VALIDATE = "validate"
INGEST = "ingest"
COVERAGE_GATE = "coverage_gate"
DOCUMENT_MAP = "document_map"
MODEL = "model"
VERIFY = "verify"
OUTPUT_GATE = "output_gate"

#: The workflow's fixed order. Tests assert the graph matches it.
NODE_SEQUENCE = [
    VALIDATE,
    INGEST,
    COVERAGE_GATE,
    DOCUMENT_MAP,
    MODEL,
    VERIFY,
    OUTPUT_GATE,
]


def _continue_or_stop(state: AnalysisState, *, next_node: str) -> str:
    """End the run if the previous node failed; otherwise proceed."""
    return END if has_failed(state) else next_node


def _coverage_route(state: AnalysisState) -> str:
    """The hard gate's branch.

    Anything other than complete coverage ends the run here, before the model
    node. `blocked_repaired`, `incomplete`, `failed` and unreadable pages all
    take the END branch.
    """
    if has_failed(state) or not state.get("coverage_complete"):
        return END
    return DOCUMENT_MAP


def build_graph(provider: ModelProvider):
    """Compile the workflow around a provider.

    The provider arrives as the `ModelProvider` interface and is bound to the
    model node only. Nothing else in the graph can reach it, and no vendor
    class is imported here.
    """
    graph = StateGraph(AnalysisState)

    graph.add_node(VALIDATE, validate_node)
    graph.add_node(INGEST, ingest_node)
    graph.add_node(COVERAGE_GATE, coverage_gate_node)
    graph.add_node(DOCUMENT_MAP, build_document_map_node)
    graph.add_node(MODEL, partial(analyze_node, provider=provider))
    graph.add_node(VERIFY, verify_node)
    graph.add_node(OUTPUT_GATE, output_gate_node)

    graph.add_edge(START, VALIDATE)

    # Every transition can end the run early on failure.
    for source, target in [
        (VALIDATE, INGEST),
        (INGEST, COVERAGE_GATE),
        (DOCUMENT_MAP, MODEL),
        (MODEL, VERIFY),
        (VERIFY, OUTPUT_GATE),
    ]:
        graph.add_conditional_edges(
            source,
            partial(_continue_or_stop, next_node=target),
            {target: target, END: END},
        )

    # The gate.
    graph.add_conditional_edges(
        COVERAGE_GATE,
        _coverage_route,
        {DOCUMENT_MAP: DOCUMENT_MAP, END: END},
    )

    graph.add_edge(OUTPUT_GATE, END)

    return graph.compile()
