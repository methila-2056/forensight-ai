# FORENSIGHT AI — backend runtime image.
#
# The app resolves all of its state relative to the backend directory
# (config.BASE_DIR): the SQLite database under data/, uploaded evidence under
# evidence_store/, and trained artifacts under ml_artifacts/. Those three
# directories are bind-mounted as volumes in production, so they are kept out
# of the image and owned by the unprivileged runtime user.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# numpy/scipy/scikit-learn all publish manylinux wheels for cp312 on both amd64
# and arm64, so no compiler toolchain is needed in the image at all.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY demo ./demo

# Match the unprivileged uid the volumes are created with (compose init).
RUN useradd --create-home --uid 10001 foresight \
    && mkdir -p /app/data /app/evidence_store /app/ml_artifacts \
    && chown -R foresight:foresight /app
USER foresight

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]