from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from op_tcg_evaluator.graph import nodes
from op_tcg_evaluator.graph.state import EvaluatorState, GeneratorState, PipelineState

MAX_GENERATION_ATTEMPTS = 3


def _stop_on_errors(state: EvaluatorState) -> str:
    return "stop" if state.errors else "continue"


def build_graph(evaluate_node: Callable[[EvaluatorState], dict] | None = None):
    """Build the evaluator graph. `evaluate_node` lets tests swap out the LLM call."""
    graph = StateGraph(EvaluatorState)
    graph.add_node("parse_decklist", nodes.parse_decklist)
    graph.add_node("validate_deck", nodes.validate_deck)
    graph.add_node("evaluate", evaluate_node or nodes.evaluate)

    graph.add_edge(START, "parse_decklist")
    graph.add_conditional_edges(
        "parse_decklist", _stop_on_errors, {"stop": END, "continue": "validate_deck"}
    )
    graph.add_conditional_edges(
        "validate_deck", _stop_on_errors, {"stop": END, "continue": "evaluate"}
    )
    graph.add_edge("evaluate", END)
    return graph.compile()


def _retry_or_stop(state: GeneratorState) -> str:
    if state.decklist is not None:
        return "done"
    return "retry" if state.attempts < MAX_GENERATION_ATTEMPTS else "done"


def build_generator_graph(generate_node: Callable[[GeneratorState], dict] | None = None):
    """Build the deck generation graph. `generate_node` lets tests swap out the LLM call."""
    graph = StateGraph(GeneratorState)
    graph.add_node("generate_deck", generate_node or nodes.generate_deck)
    graph.add_node("check_deck", nodes.check_deck)

    graph.add_edge(START, "generate_deck")
    graph.add_edge("generate_deck", "check_deck")
    graph.add_conditional_edges(
        "check_deck", _retry_or_stop, {"retry": "generate_deck", "done": END}
    )
    return graph.compile()


def build_pipeline_graph(
    generate_node: Callable[[GeneratorState], dict] | None = None,
    evaluate_node: Callable[[EvaluatorState], dict] | None = None,
):
    """Generate a deck, then evaluate it, by running the two graphs above as subgraphs.

    The subgraphs have their own state classes, so each is called from a wrapper node
    that translates PipelineState into the subgraph's state and back.
    """
    generator = build_generator_graph(generate_node)
    evaluator = build_graph(evaluate_node)

    def run_generator(state: PipelineState) -> dict:
        out = GeneratorState.model_validate(
            generator.invoke(GeneratorState(leader_id=state.leader_id))
        )
        return {
            "generation_attempts": out.attempts,
            "decklist": out.decklist,
            "errors": [] if out.decklist is not None else out.errors,
        }

    def run_evaluator(state: PipelineState) -> dict:
        # Hands the deck over as decklist text, the evaluator graph's normal input.
        out = EvaluatorState.model_validate(
            evaluator.invoke(EvaluatorState(raw_decklist=state.decklist.to_text()))
        )
        return {"evaluation": out.evaluation, "errors": out.errors}

    graph = StateGraph(PipelineState)
    graph.add_node("generate", run_generator)
    graph.add_node("evaluate", run_evaluator)

    graph.add_edge(START, "generate")
    graph.add_conditional_edges(
        "generate",
        lambda state: "continue" if state.decklist is not None else "stop",
        {"continue": "evaluate", "stop": END},
    )
    graph.add_edge("evaluate", END)
    return graph.compile()
