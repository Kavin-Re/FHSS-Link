# FHSS-Link lab: simulators + tests. Build: docker build -t fhss-lab .   Run: docker run --rm fhss-lab bench
FROM python:3.11-slim
ENV MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir numpy matplotlib
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e . --no-deps
ENTRYPOINT ["python", "-m", "fhss_lab"]
CMD ["--help"]
