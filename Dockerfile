FROM python:3-slim

COPY . /src

RUN pip install /src && \
    cp /usr/local/bin/xmrig_exporter /xmrig_exporter

EXPOSE 9189

# Example with config file:
# docker run -p 9189:9189 -v /path/to/config.yaml:/config.yaml:ro xmrig_exporter --config /config.yaml

ENTRYPOINT ["/xmrig_exporter"]
