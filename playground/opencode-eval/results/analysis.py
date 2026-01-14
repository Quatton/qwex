#!/usr/bin/env python3
import json
import re
from pathlib import Path
import matplotlib.pyplot as plt


def parse_stats(path):
    data = json.loads(Path(path).read_text())
    messages = data.get("messages", [])

    # per-step output tokens mapped by step number
    step_tokens = {}
    # list of bash tool calls with step info
    bash_calls = []
    # overall output tokens (assistant outputs)
    overall_output_tokens = 0

    for msg in messages:
        info = msg.get("info", {})
        role = info.get("role")
        tokens_info = info.get("tokens", {})
        out_tokens = tokens_info.get("output") or 0

        if role == "assistant":
            overall_output_tokens += out_tokens

        for part in msg.get("parts", []):
            if part.get("type") == "tool" and part.get("tool") == "bash":
                state = part.get("state", {})
                # prefer metadata.output then state.output
                output_text = None
                if isinstance(state.get("metadata"), dict):
                    output_text = state["metadata"].get("output")
                if not output_text:
                    output_text = state.get("output")

                step_num = None
                step_desc = None
                if output_text:
                    m = re.search(r"Current step:\s*(\d+):\s*(.+)", output_text)
                    if m:
                        step_num = int(m.group(1))
                        step_desc = m.group(2).strip()

                # attribute tokens for this message to the step if known
                if step_num is not None:
                    step_tokens[step_num] = step_tokens.get(step_num, 0) + out_tokens

                bash_calls.append(
                    {
                        "step": step_num,
                        "desc": step_desc,
                        "output_snippet": (output_text or "")[:1000],
                        "msg_output_tokens": out_tokens,
                    }
                )

    return {
        "step_tokens": step_tokens,
        "bash_calls": bash_calls,
        "overall_output_tokens": overall_output_tokens,
    }


def plot_comparison(a_stats, b_stats, a_label, b_label, out_dir: Path):
    # union of steps
    steps = sorted(
        set(list(a_stats["step_tokens"].keys()) + list(b_stats["step_tokens"].keys()))
    )

    a_vals = [a_stats["step_tokens"].get(s, 0) for s in steps]
    b_vals = [b_stats["step_tokens"].get(s, 0) for s in steps]

    x = range(len(steps))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([xi - width / 2 for xi in x], a_vals, width, label=a_label)
    ax.bar([xi + width / 2 for xi in x], b_vals, width, label=b_label)
    ax.set_xticks(x)
    ax.set_xticklabels([str(s) for s in steps])
    ax.set_xlabel("Step number")
    ax.set_ylabel("Output tokens")
    ax.set_title("Per-step output tokens: {} vs {}".format(a_label, b_label))
    ax.legend()
    fig.tight_layout()
    p = out_dir / "per_step_tokens_comparison.png"
    fig.savefig(p)

    # overall comparison
    fig2, ax2 = plt.subplots(figsize=(4, 4))
    ax2.bar(
        [a_label, b_label],
        [a_stats["overall_output_tokens"], b_stats["overall_output_tokens"]],
        color=["#1f77b4", "#ff7f0e"],
    )
    ax2.set_ylabel("Total output tokens")
    ax2.set_title("Total output tokens: {} vs {}".format(a_label, b_label))
    fig2.tight_layout()
    p2 = out_dir / "total_output_tokens.png"
    fig2.savefig(p2)

    return p, p2


def main():
    base = Path(__file__).resolve().parent
    without = base / "without-qwex-pilot" / "stats.json"
    with_ = base / "with-qwex-pilot" / "stats.json"

    assert without.exists(), f"Missing {without}"
    assert with_.exists(), f"Missing {with_}"

    s_without = parse_stats(str(without))
    s_with = parse_stats(str(with_))

    out_dir = base

    p1, p2 = plot_comparison(s_with, s_without, "with-qwex", "without-qwex", out_dir)

    # print summary
    print("Summary:")
    print("with-qwex total output tokens:", s_with["overall_output_tokens"])
    print("without-qwex total output tokens:", s_without["overall_output_tokens"])
    print()
    print("Bash tool calls (with-qwex):")
    for c in s_with["bash_calls"]:
        print(c["step"], c["desc"])  # concise
    print()
    print("Bash tool calls (without-qwex):")
    for c in s_without["bash_calls"]:
        print(c["step"], c["desc"])  # concise

    print()
    print("Saved per-step plot to:", p1)
    print("Saved total tokens plot to:", p2)


if __name__ == "__main__":
    main()
