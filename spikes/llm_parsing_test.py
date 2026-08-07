"""
Spike 0.5.2: Validate LLM structured output parsing.

Tests whether the LLM can reliably produce XML-tagged wiki pages from source
documents, and whether we can parse that output into discrete page objects.

Usage:
    python llm_parsing_test.py [--runs N]

Requires:
    - openai (pip install openai)
    - Active GitHub Copilot subscription

Auth: Uses the GitHub device code OAuth flow (same as the VS Code Copilot
extension). On first run, you'll authorize in a browser. The token is cached
in .copilot_token for subsequent runs.
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openai import OpenAI

COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_CHAT_URL = "https://api.individual.githubcopilot.com"
MODEL = "gpt-4o"
TOKEN_CACHE = Path(__file__).parent / ".copilot_token"

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


def device_code_auth() -> str:
    """Run the GitHub device code OAuth flow. Returns an OAuth access token."""
    print("Starting GitHub device code authorization...")
    req = Request(
        "https://github.com/login/device/code",
        data=f"client_id={COPILOT_CLIENT_ID}&scope=copilot".encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data["verification_uri"]
    expires_in = data["expires_in"]
    interval = data["interval"]

    print()
    print(f"  1. Open: {verification_uri}")
    print(f"  2. Enter code: {user_code}")
    print()
    print("Waiting for authorization...", end="", flush=True)

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        print(".", end="", flush=True)

        req = Request(
            "https://github.com/login/oauth/access_token",
            data=(
                f"client_id={COPILOT_CLIENT_ID}"
                f"&device_code={device_code}"
                f"&grant_type=urn:ietf:params:oauth:grant-type:device_code"
            ).encode(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urlopen(req, timeout=15) as resp:
            token_data = json.loads(resp.read())

        if "access_token" in token_data:
            print(" authorized!")
            return token_data["access_token"]

        error = token_data.get("error", "")
        if error == "authorization_pending":
            continue
        elif error == "slow_down":
            interval += 5
        elif error == "expired_token":
            raise RuntimeError("Device code expired. Please re-run the script.")
        elif error == "access_denied":
            raise RuntimeError("Authorization denied by user.")
        else:
            raise RuntimeError(f"Unexpected OAuth error: {error}")

    raise RuntimeError("Authorization timed out.")


def get_or_refresh_oauth_token() -> str:
    """Get a cached OAuth token or run the device code flow."""
    if TOKEN_CACHE.exists():
        try:
            cached = json.loads(TOKEN_CACHE.read_text())
            token = cached.get("oauth_token", "")
            if token:
                req = Request(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {token}", "Accept": "application/json"},
                )
                try:
                    with urlopen(req, timeout=10) as resp:
                        resp.read()
                    return token
                except HTTPError:
                    print("Cached OAuth token expired, re-authenticating...")
        except (json.JSONDecodeError, KeyError):
            pass

    token = device_code_auth()
    TOKEN_CACHE.write_text(json.dumps({"oauth_token": token}))
    return token


def get_copilot_session_token(oauth_token: str) -> str:
    """Exchange an OAuth token for a Copilot session token."""
    req = Request(
        COPILOT_TOKEN_URL,
        headers={
            "Authorization": f"token {oauth_token}",
            "Accept": "application/json",
            "Editor-Version": "vscode/1.90.0",
            "Editor-Plugin-Version": "copilot-chat/0.17.0",
            "User-Agent": "GithubCopilot/1.200.0",
        },
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["token"]
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(
            f"Failed to get Copilot session token (HTTP {e.code}): {body}\n"
            "Make sure you have an active GitHub Copilot subscription."
        ) from e


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


def call_llm(client: OpenAI, source: str) -> str:
    """Send the wiki generation prompt to the LLM and return the response."""
    prompt = WIKI_GENERATION_PROMPT.format(source=source)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4096,
    )
    return response.choices[0].message.content or ""


def run_single_test(client: OpenAI, run_num: int) -> dict:
    """Run a single parse test. Returns result dict."""
    print(f"  Run {run_num}...", end=" ", flush=True)

    start = time.perf_counter()
    try:
        output = call_llm(client, SAMPLE_SOURCE)
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


def main():
    parser = argparse.ArgumentParser(description="Spike 0.5.2: LLM parsing validation")
    parser.add_argument("--runs", type=int, default=10, help="Number of test runs (default: 10)")
    args = parser.parse_args()

    print("=== Spike 0.5.2: LLM structured output parsing ===")
    print(f"Provider: GitHub Copilot")
    print(f"Model: {MODEL}")
    print()

    print("Authenticating with GitHub Copilot...")
    try:
        oauth_token = get_or_refresh_oauth_token()
        print("OAuth token ready.")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("Obtaining Copilot session token...")
    try:
        session_token = get_copilot_session_token(oauth_token)
        print("Session token obtained.")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print()

    client = OpenAI(base_url=COPILOT_CHAT_URL, api_key=session_token)

    results = []
    print(f"Running {args.runs} tests:")
    for i in range(1, args.runs + 1):
        result = run_single_test(client, i)
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
    main()
