"""Sample LangGraph app that creates traces in Langfuse for testing the MCP server.

Usage:
    export LANGFUSE_HOST=http://localhost:3000
    export LANGFUSE_PUBLIC_KEY=pk-lf-...
    export LANGFUSE_SECRET_KEY=sk-lf-...
    uv run python examples/sample_langgraph.py
"""

from __future__ import annotations

import os

from langfuse import Langfuse, observe
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict


# --- Langfuse setup ---
langfuse = Langfuse(
    host=os.environ.get("LANGFUSE_HOST", "http://localhost:3000"),
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
)


# --- State ---
class AgentState(TypedDict):
    query: str
    search_results: list[str]
    answer: str


# --- Nodes (each observed by Langfuse) ---
@observe()
def search(state: AgentState) -> dict:
    """Simulate a search step."""
    query = state["query"]
    results = [
        f"Result 1 for '{query}': Langfuse is an open-source LLM observability platform.",
        f"Result 2 for '{query}': It supports traces, spans, and generations.",
        f"Result 3 for '{query}': Langfuse integrates with LangChain, LlamaIndex, and more.",
    ]
    return {"search_results": results}


@observe()
def summarize(state: AgentState) -> dict:
    """Simulate a summarization step."""
    results = state["search_results"]
    answer = f"Based on {len(results)} results: " + " | ".join(
        r.split(": ", 1)[1] for r in results
    )
    return {"answer": answer}


# --- Graph ---
def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("search", search)
    graph.add_node("summarize", summarize)
    graph.set_entry_point("search")
    graph.add_edge("search", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


@observe(name="langgraph-sample-trace")
def run_agent(query: str) -> str:
    app = build_graph()
    result = app.invoke({"query": query, "search_results": [], "answer": ""})
    return result["answer"]


if __name__ == "__main__":
    queries = [
        "What is Langfuse?",
        "How do I trace LLM calls?",
        "What are LangGraph nodes?",
    ]
    for q in queries:
        print(f"\nQuery: {q}")
        answer = run_agent(q)
        print(f"Answer: {answer}")

    langfuse.flush()
    print("\nDone! Check Langfuse at http://localhost:3000 for traces.")
