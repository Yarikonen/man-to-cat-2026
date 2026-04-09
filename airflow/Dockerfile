FROM apache/airflow:2.10.4-python3.12

USER root

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libxrender1 \
    libice6 \
    && rm -rf /var/lib/apt/lists/*

USER airflow

COPY requirements-airflow.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY dags/ /opt/airflow/dags/

ENV AIRFLOW__CORE__EXECUTOR=LocalExecutor
ENV AIRFLOW__CORE__SQL_ALCHEMY_CONN=postgresql+psycopg2://app:secure_password@postgres:5432/man2cat
ENV AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://app:secure_password@postgres:5432/man2cat
ENV AIRFLOW__CORE__LOAD_EXAMPLES=false
ENV AIRFLOW__WEBSERVER__EXPOSE_CONFIG=true
ENV AIRFLOW__CORE__DAGBAG_IMPORT_TIMEOUT=600