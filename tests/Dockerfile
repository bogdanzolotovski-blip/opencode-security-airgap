FROM debian:13
RUN apt-get update && apt-get install -y --no-install-recommends python3 git gcc libc6-dev ca-certificates \
    && printf 'int f(void){return 0;}\n' >/tmp/missing.c \
    && gcc -shared -fPIC /tmp/missing.c -Wl,-soname,libairgapmissing.so -o /tmp/libairgapmissing.so \
    && printf 'extern int f(void); int main(void){return f();}\n' >/tmp/main.c \
    && gcc /tmp/main.c -L/tmp -lairgapmissing -o /opt/missing-so-fixture \
    && rm /tmp/libairgapmissing.so /tmp/missing.c /tmp/main.c \
    && apt-get purge -y gcc libc6-dev && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 tester
ENV HOME=/home/tester PYTHONDONTWRITEBYTECODE=1
USER tester
WORKDIR /src
CMD ["python3", "/src/tests/offline_smoke.py"]
