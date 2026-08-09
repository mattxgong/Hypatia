"""
Spike 0.5.2: Validate LLM structured output parsing.

Tests whether the LLM can reliably produce XML-tagged wiki pages from source
documents, and whether we can parse that output into discrete page objects.

Usage:
    python llm_parsing_test.py [--runs N] [--provider {copilot,ollama}] [--model MODEL]

Requires:
    - github-copilot-sdk (pip install github-copilot-sdk)
    - The GitHub Copilot CLI (`copilot`), on PATH (installed separately, e.g. via winget)

Auth:
    - copilot provider: the SDK drives the local `copilot` CLI over JSON-RPC.
      Authenticate once with `copilot login` (browser device flow), or set a
      `GITHUB_TOKEN`/`COPILOT_GITHUB_TOKEN` env var to a fine-grained PAT with
      "Copilot Requests" permission. Classic PATs (ghp_...) are not supported.
    - ollama provider: no auth needed. Requires a local Ollama server
      (http://localhost:11434) with the target model pulled, e.g.
      `ollama pull qwen2.5:0.5b`. Uses the same SDK session API via a BYOK
      (Bring Your Own Key) provider config pointed at Ollama's OpenAI-compatible
      endpoint.
"""

import argparse
import asyncio
import re
import time
from dataclasses import dataclass

from copilot import CopilotClient, CopilotSession
from copilot.session import ProviderConfig, PermissionHandler

DEFAULT_MODELS = {
    "copilot": "gpt-5.4",
    "ollama": "qwen2.5:0.5b",
}

SAMPLE_SOURCE = """\
# Introduction to Neural Networks

## What Are Neural Networks?

Neural networks are computing systems inspired by biological neural networks in animal brains.
They consist of interconnected nodes (neurons) organized in layers. Each connection can transmit
a signal from one neuron to another, and the receiving neuron processes it and can signal
downstream neurons.

## Key Components

### Neurons (Nodes)
Each neuron receives inputs, applies weights and a bias, passes the result through an
activation function, and produces an output.

### Layers
- **Input Layer**: Receives the raw data
- **Hidden Layers**: Process information through weighted connections
- **Output Layer**: Produces the final result

### Activation Functions
Common activation functions include:
- **ReLU (Rectified Linear Unit)**: f(x) = max(0, x)
- **Sigmoid**: f(x) = 1 / (1 + e^-x)
- **Tanh**: f(x) = (e^x - e^-x) / (e^x + e^-x)

## Training Process

### Forward Propagation
Data flows from input through hidden layers to output. Each neuron computes a weighted sum
of its inputs plus a bias, then applies an activation function.

### Backpropagation
The algorithm that enables learning by computing gradients of the loss function with respect
to each weight. It works backwards from the output layer to adjust weights proportionally
to their contribution to the error.

### Gradient Descent
An optimization algorithm that iteratively adjusts weights to minimize the loss function.
Variants include:
- **Batch Gradient Descent**: Uses entire dataset per update
- **Stochastic Gradient Descent (SGD)**: Uses one sample per update
- **Mini-batch**: Compromise between batch and SGD

## Historical Context

The perceptron was invented by Frank Rosenblatt in 1958. The field experienced "AI winters"
in the 1970s and 1990s when progress stalled. The modern deep learning revolution began
around 2012 with AlexNet winning the ImageNet competition, enabled by GPU computing and
large datasets.

Geoffrey Hinton, Yann LeCun, and Yoshua Bengio are often called the "Godfathers of Deep
Learning" for their foundational contributions to the field.
"""

WIKI_GENERATION_PROMPT = """\
You are a wiki-generation engine. Given a source document, produce multiple wiki pages in
XML-tagged format. Each page should be a self-contained wiki article about a specific concept,
entity, or topic found in the source material.

Rules:
1. Each wiki page must be wrapped in <wiki-page path="..."> tags.
2. Each page must have YAML frontmatter with title, source, and tags fields.
3. Pages should cross-reference each other using markdown links.
4. Extract at least 3 distinct pages from the source material.
5. Include a source-summary page and concept pages.

Output format (produce ONLY the wiki-page tags, no other text):

<wiki-page path="pages/source-summaries/neural-networks-intro.md">
---
title: "Source Summary: Introduction to Neural Networks"
source: "neural-networks-intro.md"
tags: [neural-networks, deep-learning, machine-learning]
---
Content here with [[cross-references]] to other pages...
</wiki-page>

<wiki-page path="pages/concepts/backpropagation.md">
---
title: "Backpropagation"
source: "neural-networks-intro.md"
tags: [training, optimization, gradients]
---
Content here...
</wiki-page>

Now process this source document and produce wiki pages:

---
SOURCE DOCUMENT:
{source}
---
"""


@dataclass
class WikiPage:
    path: str
    title: str
    source: str
    tags: list[str]
    content: str
    raw_frontmatter: str


def parse_wiki_pages(llm_output: str) -> list[WikiPage]:
    """Parse XML-tagged wiki pages from LLM output."""
    pattern = r'<wiki-page\s+path="([^"]+)">\s*(.*?)\s*</wiki-page>'
    matches = re.findall(pattern, llm_output, re.DOTALL)

    pages = []
    for path, body in matches:
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', body.strip(), re.DOTALL)
        if not fm_match:
            pages.append(WikiPage(
                path=path, title="", source="", tags=[], content=body.strip(),
                raw_frontmatter=""
            ))
            continue

        frontmatter_str = fm_match.group(1)
        content = fm_match.group(2).strip()

        title = ""
        source = ""
        tags = []

        for line in frontmatter_str.split("\n"):
            line = line.strip()
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("source:"):
                source = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("tags:"):
                tags_str = line.split(":", 1)[1].strip()
                tag_matches = re.findall(r'[\w-]+', tags_str)
                tags = tag_matches

        pages.append(WikiPage(
            path=path, title=title, source=source, tags=tags,
            content=content, raw_frontmatter=frontmatter_str
        ))

    return pages


async def call_llm(
    client: CopilotClient, model: str, provider_config: ProviderConfig | None, source: str
) -> str:
    """Send the wiki generation prompt to the LLM and return the response."""
    prompt = WIKI_GENERATION_PROMPT.format(source=source)
    session: CopilotSession = await client.create_session(
        model=model,
        provider=provider_config,
        on_permission_request=PermissionHandler.approve_all,
    )
    try:
        response = await session.send_and_wait(prompt, timeout=120.0)
        if response is None:
            return ""
        return getattr(response.data, "content", "") or ""
    finally:
        await session.disconnect()


async def run_single_test(
    client: CopilotClient, model: str, provider_config: ProviderConfig | None, run_num: int
) -> dict:
    """Run a single parse test. Returns result dict."""
    print(f"  Run {run_num}...", end=" ", flush=True)

    start = time.perf_counter()
    try:
        output = await call_llm(client, model, provider_config, SAMPLE_SOURCE)
    except Exception as e:
        print(f"ERROR: {e}")
        return {"success": False, "error": str(e), "pages": 0, "elapsed": 0}

    elapsed = time.perf_counter() - start
    pages = parse_wiki_pages(output)

    success = len(pages) >= 3 and all(p.title for p in pages)
    status = f"OK ({len(pages)} pages, {elapsed:.1f}s)" if success else f"FAIL ({len(pages)} pages)"
    print(status)

    return {
        "success": success,
        "pages": len(pages),
        "elapsed": elapsed,
        "output_len": len(output),
        "page_titles": [p.title for p in pages],
        "has_frontmatter": all(p.title and p.source for p in pages),
        "has_content": all(len(p.content) > 50 for p in pages),
        "raw_output": output,
    }


async def main():
    parser = argparse.ArgumentParser(description="Spike 0.5.2: LLM parsing validation")
    parser.add_argument("--runs", type=int, default=10, help="Number of test runs (default: 10)")
    parser.add_argument(
        "--provider", choices=["copilot", "ollama"], default="copilot",
        help="Backend to use (default: copilot)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model name (default: gpt-5.4 for copilot, qwen2.5:0.5b for ollama; "
             "run `client.list_models()` or `copilot --help` to see valid IDs for your CLI/account)",
    )
    args = parser.parse_args()

    model = args.model or DEFAULT_MODELS[args.provider]
    provider_config: ProviderConfig | None = None
    if args.provider == "ollama":
        provider_config = {"type": "openai", "base_url": "http://localhost:11434/v1"}

    print("=== Spike 0.5.2: LLM structured output parsing ===")
    print(f"Provider: {args.provider}")
    print(f"Model: {model}")
    print()

    results = []
    async with CopilotClient() as client:
        print(f"Running {args.runs} tests:")
        for i in range(1, args.runs + 1):
            result = await run_single_test(client, model, provider_config, i)
            results.append(result)

    successes = sum(1 for r in results if r["success"])
    success_rate = successes / len(results) * 100

    print()
    print("=== Results ===")
    print(f"Success rate: {successes}/{len(results)} ({success_rate:.0f}%)")
    print(f"Go/No-go: {'GO' if success_rate > 90 else 'NO-GO'} (target: >90%)")
    print()

    successful_runs = [r for r in results if r["success"]]
    if successful_runs:
        avg_pages = sum(r["pages"] for r in successful_runs) / len(successful_runs)
        avg_time = sum(r["elapsed"] for r in successful_runs) / len(successful_runs)
        avg_tokens = sum(r["output_len"] for r in successful_runs) / len(successful_runs)
        print(f"Avg pages per run: {avg_pages:.1f}")
        print(f"Avg response time: {avg_time:.1f}s")
        print(f"Avg output length: {avg_tokens:.0f} chars")

    failed_runs = [r for r in results if not r["success"]]
    if failed_runs:
        print()
        print(f"Failures ({len(failed_runs)}):")
        for i, r in enumerate(failed_runs):
            error = r.get("error", f"Only {r['pages']} pages parsed")
            print(f"  #{i+1}: {error}")

    if successful_runs:
        print()
        print("=== Sample parsed output (first successful run) ===")
        sample = successful_runs[0]
        for title in sample["page_titles"]:
            print(f"  - {title}")


if __name__ == "__main__":
    asyncio.run(main())
