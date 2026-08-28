FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    libcairo2 \
    libpng-dev \
    libtiff-dev \
    python3 \
    python3-venv \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN python3 -m venv /opt/orbiqo-venv \
    && /opt/orbiqo-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/orbiqo-venv/bin/pip install --no-cache-dir \
      -e "/app/server/python/vendor/radialcode[vision]" \
      requests \
      zxing-cpp

RUN make -C benchmark/jabcode-runtime/jabcode clean \
    && make -C benchmark/jabcode-runtime/jabcodeWriter clean \
    && make -C benchmark/jabcode-runtime/jabcodeReader clean \
    && mkdir -p benchmark/jabcode-runtime/jabcode/build \
      benchmark/jabcode-runtime/jabcodeWriter/bin \
      benchmark/jabcode-runtime/jabcodeReader/bin \
    && make -C benchmark/jabcode-runtime/jabcode CFLAGS="-O2 -std=c11 -no-pie" \
    && make -C benchmark/jabcode-runtime/jabcodeWriter CFLAGS="-O2 -std=c11 -no-pie" \
    && make -C benchmark/jabcode-runtime/jabcodeReader CFLAGS="-O2 -std=c11 -no-pie" \
    && make -C server/python/native

RUN npm install -g corepack@latest \
    && corepack pnpm install \
    && corepack pnpm run build

ENV NODE_ENV=production \
    ORBIQO_BRIDGE_PATH=/app/server/python/orbiqo_bridge.py \
    ORBIQO_JAB_ROOT=/app/benchmark/jabcode-runtime \
    ORBIQO_RADIALCODE_ROOT=/app/server/python/vendor/radialcode \
    PATH=/opt/orbiqo-venv/bin:$PATH

CMD ["node", "dist/index.js"]
