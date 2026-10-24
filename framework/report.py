"""Dependency-free reporting for the suite (no Allure, no pytest-html).

* `--junitxml` (pytest built-in) is enabled through pytest.ini.
* This plugin additionally writes a self-contained HTML report (reports/report.html), a JSON
  dump (reports/results.json) and a Markdown plan-coverage matrix (reports/plan_coverage.md).
* Failed UI tests get a screenshot (and a Playwright trace when available) linked in the report.
"""
import datetime
import html
import json
import os
import platform
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from framework import config
from framework.plan_ids import PLAN

REPORT_DIR: Path = config.REPORT_DIR
_results: dict = {}
_artifacts: dict = defaultdict(dict)
_started = time.time()

STATUS_ORDER = ["failed", "error", "xpassed", "xfailed", "skipped", "passed"]
STATUS_COLOR = {"passed": "#1a7f37", "failed": "#cf222e", "error": "#a40e26", "skipped": "#6e7781",
                "xfailed": "#9a6700", "xpassed": "#8250df"}


def attach(nodeid: str, key: str, value: str) -> None:
    """Called by fixtures to link artifacts (e.g. trace.zip) to a test."""
    _artifacts[nodeid][key] = value


def _layer(path: str) -> str:
    for name in ("api", "ui", "e2e", "meta"):
        if f"/tests/{name}/" in path.replace("\\", "/"):
            return name
    return "other"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:150]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)

    rec = _results.setdefault(item.nodeid, {
        "nodeid": item.nodeid,
        "name": item.name,
        "layer": _layer(str(item.fspath)),
        "plan": sorted({i for m in item.iter_markers("plan") for i in m.args}),
        "markers": sorted({m.name for m in item.iter_markers()
                           if m.name in ("known_issue", "characterization", "security", "slow", "concurrency")}),
        "doc": (item.function.__doc__ or "").strip().split("\n")[0] if hasattr(item, "function") else "",
        "status": "passed", "duration": 0.0, "message": "", "screenshot": "",
    })
    rec["duration"] += getattr(rep, "duration", 0.0)

    if rep.when == "setup":
        if rep.failed:
            rec["status"], rec["message"] = "error", rep.longreprtext
        elif rep.skipped:
            rec["status"] = "skipped"
            rec["message"] = str(rep.longrepr[2]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
    elif rep.when == "call":
        if hasattr(rep, "wasxfail"):
            rec["status"] = "xfailed" if rep.skipped else "xpassed"
            rec["message"] = f"known issue: {rep.wasxfail}"
        elif rep.failed:
            rec["status"], rec["message"] = "failed", rep.longreprtext
            page = item.funcargs.get("page") if hasattr(item, "funcargs") else None
            if page is not None:
                try:
                    shots = REPORT_DIR / "screenshots"
                    shots.mkdir(parents=True, exist_ok=True)
                    path = shots / f"{_safe(item.nodeid)}.png"
                    page.screenshot(path=str(path), full_page=True)
                    rec["screenshot"] = f"screenshots/{path.name}"
                except Exception:  # noqa: BLE001 - never break reporting
                    pass
        elif rep.skipped:
            rec["status"] = "skipped"
            rec["message"] = str(rep.longrepr[2]) if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
    elif rep.when == "teardown" and rep.failed and rec["status"] == "passed":
        rec["status"], rec["message"] = "error", "teardown: " + rep.longreprtext


def _summarise():
    counts = Counter(r["status"] for r in _results.values())
    by_layer = defaultdict(Counter)
    for r in _results.values():
        by_layer[r["layer"]][r["status"]] += 1
    return counts, by_layer


def _coverage():
    """plan id -> {tests: [...], status: str}"""
    cov = {pid: {"desc": desc, "tests": []} for pid, desc in PLAN.items()}
    for r in _results.values():
        for pid in r["plan"]:
            cov.setdefault(pid, {"desc": "(not in PLAN registry)", "tests": []})["tests"].append(r)
    for pid, c in cov.items():
        sts = [t["status"] for t in c["tests"]]
        if not sts:
            c["status"] = "not covered"
        elif any(s in ("failed", "error") for s in sts):
            c["status"] = "failed"
        elif any(s == "xfailed" for s in sts):
            c["status"] = "known issue"
        elif all(s == "skipped" for s in sts):
            c["status"] = "skipped"
        else:
            c["status"] = "passed"
    return cov


def _pill(status: str) -> str:
    color = STATUS_COLOR.get(status, {"known issue": "#9a6700", "not covered": "#6e7781"}.get(status, "#555"))
    return f'<span class="pill" style="background:{color}">{html.escape(status)}</span>'


def _write_html(counts, by_layer, cov, duration):
    total = sum(counts.values())
    rows = []
    for r in sorted(_results.values(), key=lambda x: (STATUS_ORDER.index(x["status"]), x["nodeid"])):
        extra = ""
        if r["message"]:
            extra += f"<pre>{html.escape(r['message'][-6000:])}</pre>"
        if r["screenshot"]:
            extra += f'<a href="{html.escape(r["screenshot"])}"><img class="shot" src="{html.escape(r["screenshot"])}"></a>'
        art = _artifacts.get(r["nodeid"], {})
        for k, v in art.items():
            extra += f'<div><a href="{html.escape(v)}">{html.escape(k)}</a></div>'
        tags = "".join(f'<span class="tag">{html.escape(p)}</span>' for p in r["plan"])
        tags += "".join(f'<span class="tag warn">{html.escape(m)}</span>' for m in r["markers"])
        rows.append(
            f'<tr class="row" data-status="{r["status"]}" data-layer="{r["layer"]}">'
            f'<td>{_pill(r["status"])}</td><td>{html.escape(r["layer"])}</td>'
            f'<td><div class="nid">{html.escape(r["nodeid"])}</div>'
            f'<div class="doc">{html.escape(r["doc"])}</div>{tags}{extra}</td>'
            f'<td class="num">{r["duration"]:.2f}s</td></tr>')

    cov_rows = []
    for pid, c in cov.items():
        links = ", ".join(html.escape(t["name"]) for t in c["tests"][:6]) + (" …" if len(c["tests"]) > 6 else "")
        cov_rows.append(f'<tr><td><b>{html.escape(pid)}</b></td><td>{html.escape(c["desc"])}</td>'
                        f'<td>{_pill(c["status"])}</td><td class="num">{len(c["tests"])}</td>'
                        f'<td class="small">{links}</td></tr>')
    covered = sum(1 for c in cov.values() if c["tests"])

    cards = "".join(
        f'<div class="card"><div class="big" style="color:{STATUS_COLOR[s]}">{counts.get(s, 0)}</div>{s}</div>'
        for s in ["passed", "failed", "error", "xfailed", "xpassed", "skipped"])
    layer_rows = "".join(
        f'<tr><td>{html.escape(l)}</td>' + "".join(f'<td class="num">{c.get(s, 0)}</td>' for s in
                                                    ["passed", "failed", "error", "xfailed", "xpassed", "skipped"]) + "</tr>"
        for l, c in sorted(by_layer.items()))

    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Rapid Task — automated test report</title>
<style>
body{{font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f8fa;color:#1f2328}}
header{{background:#0d1117;color:#fff;padding:20px 32px}} header h1{{margin:0 0 4px;font-size:22px}}
header .meta{{color:#9da7b3;font-size:12.5px}}
main{{padding:24px 32px;max-width:1300px;margin:auto}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.card{{background:#fff;border:1px solid #d0d7de;border-radius:8px;padding:12px 20px;min-width:110px;text-align:center}}
.big{{font-size:28px;font-weight:700}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d0d7de;border-radius:8px;margin-bottom:28px}}
th,td{{padding:8px 10px;border-bottom:1px solid #eaeef2;text-align:left;vertical-align:top}}
th{{background:#f6f8fa;font-size:12.5px}} .num{{text-align:right;white-space:nowrap}} .small{{font-size:12px;color:#57606a}}
.pill{{color:#fff;border-radius:10px;padding:2px 9px;font-size:12px;white-space:nowrap}}
.tag{{display:inline-block;background:#ddf4ff;color:#0550ae;border-radius:4px;padding:0 6px;margin:4px 4px 0 0;font-size:11.5px}}
.tag.warn{{background:#fff8c5;color:#7d4e00}}
.nid{{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;word-break:break-all}} .doc{{color:#57606a;font-size:12.5px}}
pre{{background:#0d1117;color:#e6edf3;padding:10px;border-radius:6px;overflow:auto;max-height:320px;font-size:12px;white-space:pre-wrap}}
.shot{{max-width:420px;border:1px solid #d0d7de;border-radius:6px;margin-top:6px}}
.filters button{{margin:0 6px 10px 0;padding:5px 12px;border:1px solid #d0d7de;background:#fff;border-radius:16px;cursor:pointer}}
.filters button.on{{background:#0969da;color:#fff;border-color:#0969da}}
h2{{margin:28px 0 10px}}
</style></head><body>
<header><h1>Rapid Task — automated test report</h1>
<div class="meta">{datetime.datetime.now():%Y-%m-%d %H:%M:%S} · {total} tests in {duration:.1f}s · Python {platform.python_version()} · {platform.system()} · plan coverage {covered}/{len(cov)} identifiers</div></header>
<main>
<div class="cards">{cards}</div>
<table><tr><th>Layer</th><th>passed</th><th>failed</th><th>error</th><th>xfailed (known issues)</th><th>xpassed</th><th>skipped</th></tr>{layer_rows}</table>
<h2>TEST_PLAN coverage</h2>
<table><tr><th>ID</th><th>Scenario</th><th>Status</th><th>Tests</th><th>Test names</th></tr>{''.join(cov_rows)}</table>
<h2>Results</h2>
<div class="filters" id="filters"></div>
<table id="results"><tr><th>Status</th><th>Layer</th><th>Test</th><th>Time</th></tr>{''.join(rows)}</table>
</main>
<script>
const rows=[...document.querySelectorAll('tr.row')];const statuses=['all',...new Set(rows.map(r=>r.dataset.status))];
const box=document.getElementById('filters');
statuses.forEach(s=>{{const b=document.createElement('button');b.textContent=s;if(s==='all')b.className='on';
b.onclick=()=>{{[...box.children].forEach(x=>x.className='');b.className='on';rows.forEach(r=>r.style.display=(s==='all'||r.dataset.status===s)?'':'none');}};box.appendChild(b);}});
</script></body></html>"""
    (REPORT_DIR / "report.html").write_text(doc, encoding="utf-8")


def _write_markdown(cov):
    lines = ["# TEST_PLAN coverage", "", "| ID | Scenario | Status | Tests |", "|---|---|---|---|"]
    for pid, c in cov.items():
        lines.append(f"| {pid} | {c['desc']} | {c['status']} | {len(c['tests'])} |")
    (REPORT_DIR / "plan_coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def pytest_sessionfinish(session, exitstatus):
    if not _results:
        return
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    counts, by_layer = _summarise()
    cov = _coverage()
    duration = time.time() - _started
    _write_html(counts, by_layer, cov, duration)
    _write_markdown(cov)
    (REPORT_DIR / "results.json").write_text(json.dumps(
        {"summary": dict(counts), "duration": duration, "results": list(_results.values()),
         "coverage": {k: {"status": v["status"], "tests": [t["nodeid"] for t in v["tests"]]} for k, v in cov.items()}},
        indent=2, default=str), encoding="utf-8")


def pytest_terminal_summary(terminalreporter):
    if _results:
        terminalreporter.write_sep("-", f"HTML report: {REPORT_DIR / 'report.html'}")
