FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm
# The base image ships a Yarn apt source whose signing key is no longer valid.
# That breaks apt-get update for Dev Container Features (docker-in-docker), so remove it.
USER root
RUN grep -rl "dl.yarnpkg.com" /etc/apt/sources.list.d/ | xargs -r rm -f
