FROM debian:13
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* /usr/lib/python3.13/ensurepip /usr/share/python-wheels \
    && rm -f /usr/bin/apt /usr/bin/apt-get \
    && rm -f /usr/lib/x86_64-linux-gnu/libstdc++.so.6* /usr/lib/x86_64-linux-gnu/libgomp.so.1* /usr/lib/x86_64-linux-gnu/libgmp.so.10* \
    && useradd -m -u 1000 tester
ENV HOME=/home/tester PYTHONDONTWRITEBYTECODE=1
USER tester
WORKDIR /src
CMD ["python3", "/src/agent-controls/tests/offline_smoke.py"]
