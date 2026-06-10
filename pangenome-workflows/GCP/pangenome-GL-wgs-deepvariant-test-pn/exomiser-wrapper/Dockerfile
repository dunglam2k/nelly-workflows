# Self-contained Exomiser image: JRE + the exomiser-cli 15.0.0 distribution + a
# real wrapper script. The official exomiser/exomiser-cli image is distroless
# (no shell, fixed jib entrypoint), which can't run our setup script -- so we
# build our own from a JRE base that has bash.
FROM eclipse-temurin:21-jre

RUN apt-get update && apt-get install -y --no-install-recommends \
        gzip grep coreutils && rm -rf /var/lib/apt/lists/*

# The exomiser-cli distribution (jar + lib/) -- copied from the build context
# (unpacked on ws at exomiser/exomiser-cli-15.0.0).
COPY exomiser-cli-15.0.0 /exomiser
COPY run-exomiser.sh /run-exomiser.sh
RUN chmod +x /run-exomiser.sh

WORKDIR /work
# No ENTRYPOINT: CWL supplies the full command (baseCommand: [bash,
# /run-exomiser.sh]). An ENTRYPOINT would be PREPENDED to the CWL command by the
# Arvados runtime, doubling "bash /run-exomiser.sh" and shifting the positional
# args (the data path landed in $3/assembly).
CMD ["bash"]
