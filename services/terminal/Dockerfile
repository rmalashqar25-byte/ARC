FROM alpine:3.24.3
RUN apk add --no-cache python3 py3-pytest git ripgrep
COPY runner.py /opt/arc/runner.py
USER 65534:65534
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/python3", "-I", "/opt/arc/runner.py"]
