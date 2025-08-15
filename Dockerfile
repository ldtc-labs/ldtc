FROM python:3.11-slim

WORKDIR /app

# Copy project files (exclude with .dockerignore as needed)
COPY pyproject.toml README.md LICENSE CITATION.cff ./
COPY src ./src
COPY configs ./configs
COPY scripts ./scripts
COPY examples ./examples
COPY docs ./docs

# Install runtime dependencies and the package
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

# Prepare artifact directories (persist via volume on docker-run)
RUN mkdir -p artifacts/audits artifacts/indicators artifacts/figures artifacts/keys artifacts/calibration

# Expose CLI entrypoint
ENTRYPOINT ["ldtc"]
