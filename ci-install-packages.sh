#!/bin/bash

source ci-common.source.sh

export DEBIAN_FRONTEND=noninteractive 

# mono 6 image is based on debian buster, which moved its sources to archive
sed -i 's/deb.debian.org/archive.debian.org/g' /etc/apt/sources.list

apt update
apt install -y git zip || die "apt install failed"
