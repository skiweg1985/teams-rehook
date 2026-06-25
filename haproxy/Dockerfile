FROM haproxy:lts-alpine

USER root

RUN apk add --no-cache openssl

COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
COPY localhost-openssl.cnf /usr/local/etc/haproxy/localhost-openssl.cnf
COPY start-haproxy.sh /usr/local/bin/start-haproxy.sh

RUN chmod +x /usr/local/bin/start-haproxy.sh

CMD ["/usr/local/bin/start-haproxy.sh"]
