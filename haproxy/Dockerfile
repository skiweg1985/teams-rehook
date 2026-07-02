FROM haproxy:lts-alpine@sha256:820658d9303227313f1feb164443f07319d604fed68982c918611dcaea8fb775

USER root

RUN apk add --no-cache openssl

COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
COPY localhost-openssl.cnf /usr/local/etc/haproxy/localhost-openssl.cnf
COPY start-haproxy.sh /usr/local/bin/start-haproxy.sh

RUN chmod +x /usr/local/bin/start-haproxy.sh

CMD ["/usr/local/bin/start-haproxy.sh"]
