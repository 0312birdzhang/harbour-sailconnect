#!/bin/bash
# Run inside the Sailfish SDK target (sb2).
set -eu
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
X264_OUT="$ROOT/build/x264"
PAYLOAD="$ROOT/rpm/payload"
mkdir -p "$PAYLOAD" "$ROOT/build/capture" "$ROOT/build/app"
if [ ! -f "$X264_OUT/libx264.a" ]; then
    mkdir -p "$X264_OUT"
    tar xzf "$ROOT/third_party/x264.tar.gz" -C "$X264_OUT" --strip-components=1
    cd "$X264_OUT"
    ./configure --enable-static --enable-pic --disable-cli --disable-opencl
    make -j4 libx264.a
fi
cd "$ROOT/build/capture"
CAPTURE="$ROOT/display-source/capture"
g++ -O2 -std=c++11 -I"$CAPTURE/src" "$ROOT/tests/convert_test.cpp" \
    "$CAPTURE/src/convert.cpp" -o "$ROOT/build/convert-test"
gcc -O2 -I"$CAPTURE/protocol" -c "$CAPTURE/protocol/lipstick-recorder-protocol.c" -o protocol.o
g++ -O2 -std=c++11 -pthread -I"$CAPTURE/src" -I"$CAPTURE/protocol" -I"$CAPTURE" -I"$X264_OUT" \
    "$CAPTURE/carlife-capture.cpp" "$CAPTURE/shmsource.cpp" "$CAPTURE/x264_encoder.cpp" \
    "$CAPTURE/src/recorder.cpp" "$CAPTURE/src/convert.cpp" protocol.o \
    "$X264_OUT/libx264.a" $(pkg-config --cflags --libs wayland-client) -lm -ldl -o "$PAYLOAD/carlife-capture"
cd "$ROOT/build/app"
qmake "$ROOT/app/harbour-sailconnect.pro"
make -j2
cp harbour-sailconnect "$PAYLOAD/harbour-sailconnect"
mkdir -p "$PAYLOAD/translations"
for translation in "$ROOT/app/translations/"*.ts; do
    lrelease "$translation" -qm "$PAYLOAD/translations/$(basename "$translation" .ts).qm"
done
