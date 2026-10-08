FROM node:22-alpine AS frontend

WORKDIR /build

# Install deps first for layer caching
COPY packages/job-engine-dashboard/package.json packages/job-engine-dashboard/package-lock.json ./
RUN npm ci

COPY packages/job-engine-dashboard/vite.config.js ./
COPY packages/job-engine-dashboard/src/ src/

RUN npm run build

FROM python:3.12-slim

WORKDIR /app

# Install system deps (curl for healthcheck, ca-certificates for SSL, git for setuptools scm,
# poppler-utils for pdftotext-based PDF page-count/ATS verification) and Node.js (needed to
# run job-engine-scrapers' dump-metadata.js for the scraper registry)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git gnupg poppler-utils && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install tectonic (LaTeX engine used to compile the CV/cover-letter moderncv PDFs).
# Fetched directly from GitHub releases rather than the upstream install script, which
# only publishes glibc builds for x86_64 — pick the musl build on aarch64 (Apple Silicon
# dev machines) since it runs fine as a static binary on this glibc-based image too.
RUN TECTONIC_VERSION=0.17.0 && \
    ARCH="$(uname -m)" && \
    if [ "$ARCH" = "aarch64" ]; then TECTONIC_TARGET="aarch64-unknown-linux-musl"; else TECTONIC_TARGET="x86_64-unknown-linux-gnu"; fi && \
    curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${TECTONIC_TARGET}.tar.gz" \
      | tar xz -C /usr/local/bin

# Copy package configs first for layer caching
COPY packages/job-engine-core/pyproject.toml packages/job-engine-core/
COPY packages/job-engine-dashboard/pyproject.toml packages/job-engine-dashboard/
COPY packages/job-engine-scrapers/package*.json packages/job-engine-scrapers/

# Create minimal src/ stubs so setuptools editable install doesn't fail
RUN mkdir -p packages/job-engine-core/src packages/job-engine-dashboard/src && \
    touch packages/job-engine-core/src/__init__.py packages/job-engine-dashboard/src/__init__.py

# Install Python deps (editable installs)
RUN pip install --no-cache-dir -e packages/job-engine-core -e packages/job-engine-dashboard

# Install job-engine-scrapers' Node deps (needed for dump-metadata.js registry queries
# and for the dashboard's own "Run scraper" button, which launches run.js in-process)
RUN cd packages/job-engine-scrapers && npm install

# Install Chromium + its OS-level shared libraries for in-process scraper runs
RUN npx --prefix packages/job-engine-scrapers playwright install --with-deps chromium

# Copy application code (overwrites stub src/ directories)
COPY .project-root VERSION ./
COPY packages/job-engine-core/src/ packages/job-engine-core/src/
COPY packages/job-engine-dashboard/src/ packages/job-engine-dashboard/src/
COPY packages/job-engine-scrapers/ packages/job-engine-scrapers/
COPY config/ config/
COPY scripts/ scripts/

# Built Vue SPA (served by FastAPI from dist/)
COPY --from=frontend /build/dist/ packages/job-engine-dashboard/dist/

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1
CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "8000"]
