#!/bin/bash
set -eu
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
SDK=${SDK:-/srv/sailfishos/sdks/sfossdk}
TARGET=${TARGET:-SailfishOS-latest-aarch64}
VERSION=$(awk '$1 == "Version:" {print $2}' "$ROOT/rpm/harbour-sailconnect.spec")
RELEASE=$(awk '$1 == "Release:" {print $2}' "$ROOT/rpm/harbour-sailconnect.spec")
cd "$SDK"
./sdk-chroot -u pc sb2 -t "$TARGET" bash "/parentroot$ROOT/rpm/build-arm.sh"
STAGE=$(mktemp -d)
trap 'rm -rf -- "$STAGE"' EXIT
mkdir -p "$STAGE/harbour-sailconnect-$VERSION"
tar -C "$ROOT" --exclude=build --exclude=__pycache__ --exclude=.pytest_cache --exclude='*.rpm' -cf - \
    carplay_proto sailconnect app rpm third_party display-source scripts tests design \
    pyproject.toml README.md PLAN.md VALIDATION.md LICENSE THIRD_PARTY.md | tar -C "$STAGE/harbour-sailconnect-$VERSION" -xf -
mkdir -p /home/pc/rpmbuild/SOURCES
tar -C "$STAGE" -czf "/home/pc/rpmbuild/SOURCES/harbour-sailconnect-$VERSION.tar.gz" "harbour-sailconnect-$VERSION"
./sdk-chroot -u pc sb2 -t "$TARGET" rpmbuild -bb "/parentroot$ROOT/rpm/harbour-sailconnect.spec"
cp "/home/pc/rpmbuild/RPMS/aarch64/harbour-sailconnect-$VERSION-$RELEASE.aarch64.rpm" "$ROOT/"
cp "/home/pc/rpmbuild/SOURCES/harbour-sailconnect-$VERSION.tar.gz" "$ROOT/"
