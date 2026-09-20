FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    libcairo2 \
    libfreetype6-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libwebp-dev \
    libzxing-dev \
    pkg-config \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN make -C benchmark/jabcode-runtime/jabcode clean \
    && make -C benchmark/jabcode-runtime/jabcodeWriter clean \
    && make -C benchmark/jabcode-runtime/jabcodeReader clean \
    && mkdir -p benchmark/jabcode-runtime/jabcode/build \
      benchmark/jabcode-runtime/jabcodeWriter/bin \
      benchmark/jabcode-runtime/jabcodeReader/bin \
    && make -C benchmark/jabcode-runtime/jabcode CFLAGS="-O2 -std=c11 -no-pie" \
    && make -C benchmark/jabcode-runtime/jabcodeWriter CFLAGS="-O2 -std=c11 -no-pie" \
    && make -C benchmark/jabcode-runtime/jabcodeReader CFLAGS="-O2 -std=c11 -no-pie" \
    && make -C server/python/native \
    && make -C benchmark/native

RUN npm install -g corepack@latest \
    && corepack pnpm install \
    && corepack pnpm run build

ENV NODE_ENV=production \
    ORBIQO_JAB_ROOT=/app/benchmark/jabcode-runtime \
    ORBIQO_NATIVE_PATH=/app/server/python/native/orbiqo_native \
    ORBIQO_EXTERNAL_COMPARE_PATH=/app/benchmark/native/orbiqo_external_compare

CMD ["node", "dist/index.js"]
