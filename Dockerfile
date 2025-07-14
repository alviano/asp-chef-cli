FROM ubuntu:latest as builder

RUN apt update && apt install binutils build-essential python3-dev python3-pip wget zip -y

WORKDIR tmp
RUN wget https://github.com/MazzottaG/PyQASP/archive/refs/heads/main.zip && \
    unzip main.zip && \
    cd PyQASP-main && \
    pip install pyinstaller joblib --break-system-packages && \
    bash clean-install.bash pyqasp


FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

RUN pip install asp_chef_cli==0.4.13 --upgrade && \
    apt update && apt install gringo -y

COPY --from=builder /tmp/PyQASP-main/dist/pyqasp /bin/pyqasp

ENTRYPOINT ["python", "-m", "asp_chef_cli"]