# The watchdog as a deployable resident service (ESSENCE §2.11, Appendix I).
#
# This image ships THREE things the service needs at runtime, none borrowed from a laptop:
#   1. the watchdog code + its deps,
#   2. the watched app's full runtime + test deps (so the smoke gate is real),
#   3. the autonomous coding-agent CLI, headless (Claude Code), + git for sandboxes.
FROM python:3.12-slim

# git: provision pristine sandbox copies. nodejs/npm: install the coding-agent CLI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# The coding agent runs headless INSIDE the service image (never a tool on a terminal).
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /srv

COPY watchdog/requirements.txt ./watchdog-requirements.txt
RUN pip install --no-cache-dir -r watchdog-requirements.txt

# Ship the watched app's source + tests so the service can clone a pristine copy per fix
# attempt and run the smoke command against it.
COPY app ./app
COPY watchdog ./watchdog

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# A resident service started ONCE and supervised forever — not a script a human runs.
CMD ["python", "-m", "watchdog.service"]
