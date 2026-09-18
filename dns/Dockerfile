FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends dnsmasq \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/log/dnsmasq

COPY dnsmasq.conf /etc/dnsmasq.conf

EXPOSE 53/udp 53/tcp

CMD ["dnsmasq", "-k", "--conf-file=/etc/dnsmasq.conf"]
