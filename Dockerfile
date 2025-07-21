FROM ubuntu:latest as builder

RUN apt update && apt install binutils build-essential python3-dev python3-pip wget zip -y

WORKDIR tmp
RUN wget https://github.com/dodaro/SDL/archive/refs/heads/main.zip && mv main.zip sdl.zip && \
    wget https://github.com/MazzottaG/PyQASP/archive/refs/heads/main.zip && mv main.zip pyqasp.zip && \
    unzip pyqasp.zip && \
    cd PyQASP-main && \
    pip install pyinstaller joblib --break-system-packages && \
    bash clean-install.bash pyqasp


FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

COPY --from=builder /tmp/sdl.zip /tmp/sdl.zip
COPY --from=builder /tmp/PyQASP-main/dist/pyqasp /bin/pyqasp

RUN pip install asp_chef_cli==0.4.15 --upgrade && \
    apt update && apt install gringo python3-poetry zip -y && \
    unzip /tmp/sdl.zip && mv SDL-main SDL && cd SDL && poetry update && cd ..


ENTRYPOINT ["python", "-m", "asp_chef_cli"]
