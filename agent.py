"""Bounded research agent over a small, curated Microsoft earnings corpus."""

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

CORPUS = json.loads(Path(__file__).with_name("evidence.json").read_text(encoding="utf-8-sig"))
FACTS = {row["period"]: row for row in CORPUS["facts"]}
METRICS = {
    "revenue": "Revenue",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "diluted_eps": "Diluted EPS",
    "operating_margin": "Operating margin",
}
TOPICS = {
    "azure_growth": "azure growth",
    "capital_spending": "capex",
    "capacity_outlook": "capacity",
    "cloud_revenue": "microsoft cloud",
}
UNSUPPORTED = "The demo covers Microsoft FY24 Q4 and FY25 Q4 financials and selected FY25 Q4 call topics."
MAX_ROUNDS = 3
MAX_CALLS = 6


def evidence(row):
    return {key: row[key] for key in ("id", "period", "section", "url")}


def lookup(metric, period):
    row = FACTS[period]
    if metric == "operating_margin":
        value = 100 * row["operating_income"] / row["revenue"]
        detail = f"${row['operating_income']:,}m ÷ ${row['revenue']:,}m × 100"
        unit = "%"
    else:
        value = row[metric]
        unit = "USD per share" if metric == "diluted_eps" else "USD millions"
        detail = f"{value:,} {unit}"
    return value, unit, detail, evidence(row)


def execute(name, args):
    if name == "search_notes":
        query = TOPICS[args["topic"]]
        terms = set(query.split())
        ranked = sorted(CORPUS["notes"], key=lambda row: -len(terms & set(row["keywords"].split())))
        best = ranked[0]
        return {"text": best["text"], "sources": [evidence(best)]}
    metric = args["metric"]
    label = METRICS[metric]
    if name == "lookup_metric":
        period = args["period"]
        value, unit, detail, source = lookup(metric, period)
        formatted = f"{value:,.2f}%" if unit == "%" else detail
        return {"text": f"{period} {label.lower()} was {formatted}.", "calculation": detail,
                "sources": [source]}
    if name == "compare_yoy":
        current, unit, now, current_source = lookup(metric, "FY25 Q4")
        previous, _, then, previous_source = lookup(metric, "FY24 Q4")
        if unit == "%":
            change = current - previous
            result = f"{previous:.2f}% → {current:.2f}% ({change:+.2f} percentage points)"
            formula = f"FY25 Q4 ({now}) − FY24 Q4 ({then})"
        else:
            change = 100 * (current / previous - 1)
            result = f"{change:+.2f}% YoY"
            formula = f"(({current:,} ÷ {previous:,}) − 1) × 100. Inputs in {unit}."
        return {"text": f"{label}, FY25 Q4 versus FY24 Q4: {result}.", "calculation": formula,
                "sources": [current_source, previous_source]}
    raise ValueError("Unknown tool")


def tool(name, description, **options):
    return {"type": "function", "function": {
        "name": name, "description": description, "strict": True,
        "parameters": {"type": "object", "additionalProperties": False,
                       "required": list(options), "properties": {
                           key: {"type": "string", "enum": list(values)}
                           for key, values in options.items()
                       }},
    }}


TOOLS = [
    tool("lookup_metric", "Get a quarterly financial metric or compute operating margin.",
         metric=METRICS, period=FACTS),
    tool("compare_yoy", "Compare Microsoft FY25 Q4 with FY24 Q4; margin uses percentage points.",
         metric=METRICS),
    tool("search_notes", "Retrieve a source-linked, curated earnings note for a FY25 Q4 topic.",
         topic=TOPICS),
]
SCHEMAS = {item["function"]["name"]: item["function"]["parameters"]["properties"] for item in TOOLS}


def run_tool(name, args):
    schema = SCHEMAS.get(name)
    if (schema is None or not isinstance(args, dict) or args.keys() != schema.keys()
            or any(args[key] not in rule["enum"] for key, rule in schema.items())):
        return {"error": "Unsupported tool or arguments."}
    return execute(name, args)


def offline_plan(question):
    q = question.lower()
    if (not re.search(r"\b(microsoft|msft|fy\s*(?:20)?2[45])\b", q)
            or re.search(r"\b(apple|google|amazon|nvidia|meta|tesla|aapl|nvda|202[0-36-9]|fy2[0-36-9]|q[1-3]|forecast|price|stock|beat|consensus)\b", q)):
        return []
    period = "FY24 Q4" if re.search(r"fy\s*(?:20)?24|\b2024\b", q) else "FY25 Q4"
    compare = bool(re.search(r"\b(yoy|year.over.year|compare|change|grew|growth|versus|vs)\b", q))
    notes = []
    if period == "FY25 Q4":
        for topic, pattern in {
            "azure_growth": r"\bazure\b.*\b(growth|grow|grew|revenue)\b|\b(growth|grow|grew|revenue)\b.*\bazure\b",
            "capital_spending": r"\b(capex|capital spending|capital expenditure[s]?|finance lease[s]?)\b",
            "capacity_outlook": r"\b(capacity|datacenter|data center)\b",
            "cloud_revenue": r"\bmicrosoft cloud\b",
        }.items():
            if re.search(pattern, q):
                notes.append(("search_notes", {"topic": topic}))
    metrics = []
    for metric, pattern in {
        "operating_margin": r"\boperating margin\b",
        "operating_income": r"\boperating (?:income|profit)\b",
        "net_income": r"\bnet income\b",
        "diluted_eps": r"\b(?:eps|earnings per share)\b",
        "revenue": r"\b(?:total|company) revenue\b|\brevenue\b",
    }.items():
        if re.search(pattern, q) and (metric != "revenue" or not notes):
            args = {"metric": metric}
            if not compare:
                args["period"] = period
            metrics.append(("compare_yoy" if compare else "lookup_metric", args))
    return (notes + metrics)[:MAX_CALLS]


def chat_completion(messages):
    payload = {"model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), "messages": messages,
               "tools": TOOLS, "max_completion_tokens": 500}
    request = Request("https://api.openai.com/v1/chat/completions",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                               "Content-Type": "application/json"})
    with urlopen(request, timeout=25) as response:
        return json.load(response)["choices"][0]["message"]


def investigate(question, complete=None):
    if not question.strip() or len(question) > 600:
        raise ValueError("Enter a question of 1–600 characters.")
    trace = []

    def record(name, args):
        result = run_tool(name, args)
        trace.append({"tool": name, "arguments": args, "result": result})
        return result

    if complete is None:
        for name, args in offline_plan(question):
            record(name, args)
    else:
        messages = [
            {"role": "system", "content":
             "Plan evidence requests for a historical Microsoft earnings demo. Scope: FY24 Q4 "
             "and FY25 Q4 corporate financials, and FY25 Q4 call notes. Use the tools only for "
             "facts explicitly requested. Stop without a tool call for unsupported requests. "
             "Do not repeat calls. Do not produce a narrative answer; the app renders tool results."},
            {"role": "user", "content": question},
        ]
        for _ in range(MAX_ROUNDS):
            if len(trace) == MAX_CALLS:
                break
            message = complete(messages)
            calls = message.get("tool_calls") or []
            if not calls:
                break
            calls = calls[:MAX_CALLS - len(trace)]
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call in calls:
                function = call["function"]
                try:
                    args = json.loads(function["arguments"])
                except json.JSONDecodeError:
                    args = None
                result = record(function["name"], args)
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result)})
    results = [step["result"] for step in trace if "text" in step["result"]]
    return {"results": results, "trace": trace, "message": None if results else UNSUPPORTED}
