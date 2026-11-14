# Everything the project needs: Python, the Gemini packages, and the compiled C++ trader.
# The project folder itself is mounted at /app when the container runs (see compose.yaml).
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ libcurl4-openssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY ai/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY trading/trader.cpp /tmp/trader.cpp
RUN g++ -std=c++11 /tmp/trader.cpp -o /usr/local/bin/trader -lcurl -pthread

# sed strips Windows line endings in case Git checked the script out with CRLF.
COPY run.sh /usr/local/bin/run.sh
RUN sed -i 's/\r$//' /usr/local/bin/run.sh

WORKDIR /app
ENTRYPOINT ["bash", "/usr/local/bin/run.sh"]
