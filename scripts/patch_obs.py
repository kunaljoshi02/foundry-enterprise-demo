import io
import os
import re
import sys

BLOCK = '''
# --- Observability: export OpenTelemetry traces/metrics to Application Insights ---
_APPINSIGHTS_CS = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
if _APPINSIGHTS_CS:
    os.environ.setdefault("ENABLE_OTEL", "true")
    os.environ.setdefault("ENABLE_SENSITIVE_DATA", "true")
    _obs_ready = False
    try:
        from agent_framework.observability import setup_observability

        try:
            setup_observability(applicationinsights_connection_string=_APPINSIGHTS_CS)
        except TypeError:
            setup_observability()
        _obs_ready = True
    except Exception as _obs_exc:  # noqa: BLE001
        print("setup_observability unavailable: %s" % _obs_exc, flush=True)
    if not _obs_ready:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=_APPINSIGHTS_CS)
            _obs_ready = True
        except Exception as _mon_exc:  # noqa: BLE001
            print("configure_azure_monitor failed: %s" % _mon_exc, flush=True)
    if _obs_ready:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except Exception as _httpx_exc:  # noqa: BLE001
            print("httpx instrumentation failed: %s" % _httpx_exc, flush=True)
        print("Application Insights telemetry enabled.", flush=True)
'''

DEPS = ["azure-monitor-opentelemetry", "opentelemetry-instrumentation-httpx"]


def patch_main(path):
    src = io.open(path, encoding="utf-8").read()
    if "APPLICATIONINSIGHTS_CONNECTION_STRING" in src:
        print("  main.py already patched:", path)
        return
    lines = src.split("\n")
    last_import = 0
    for i, ln in enumerate(lines):
        if re.match(r"^(import |from )\S", ln):
            last_import = i
    lines.insert(last_import + 1, BLOCK)
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print("  patched main.py after line", last_import + 1, "->", path)


def patch_pyproject(path):
    src = io.open(path, encoding="utf-8").read()
    added = [d for d in DEPS if '"%s"' % d not in src]
    if not added:
        print("  pyproject already has deps:", path)
        return
    ins = "".join('    "%s",\n' % d for d in added)
    src = src.replace("dependencies = [\n", "dependencies = [\n" + ins, 1)
    io.open(path, "w", encoding="utf-8", newline="\n").write(src)
    print("  added deps", added, "->", path)


if __name__ == "__main__":
    for root in sys.argv[1:]:
        print("AGENT:", root)
        for dirpath, _dirnames, filenames in os.walk(root):
            if "main.py" in filenames and "pyproject.toml" in filenames:
                patch_main(os.path.join(dirpath, "main.py"))
                patch_pyproject(os.path.join(dirpath, "pyproject.toml"))
