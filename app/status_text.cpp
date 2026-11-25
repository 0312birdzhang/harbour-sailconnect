#include "status_text.h"
#include <QRegularExpression>

QString StatusText::phase(const QString &value) {
    if (value == "connect") return tr("Connection");
    if (value == "public-info") return tr("Receiver information");
    if (value == "pair-setup") return tr("Pair setup");
    if (value == "pair-verify") return tr("Pair verification");
    if (value == "initial-setup") return tr("Session setup");
    if (value == "encrypted-info") return tr("Encrypted receiver information");
    if (value == "event-connect") return tr("Control channel");
    if (value == "capture") return tr("Screen capture");
    if (value == "record") return tr("Recording");
    if (value == "screen-setup") return tr("Video setup");
    if (value == "streaming") return tr("Video streaming");
    return value;
}

QString StatusText::error(const QString &value) {
    if (value == "one powered Bluetooth adapter required for wireless CarPlay") return tr("Turn on Bluetooth on the phone before connecting.");
    if (value == "connect Bluetooth to exactly one paired WinPlay computer first") return tr("Pair the phone with the receiving computer in system Bluetooth settings. Connect that computer if several devices are paired.");
    if (value.contains("org.bluez")) return tr("The Bluetooth service is unavailable. Turn on Bluetooth and search again.");
    if (value == "receiver must have a LAN address") return tr("Enter a local network IP address for WinPlay.");
    if (value == "invalid network interface") return tr("Invalid network interface.");
    if (value == "invalid port or native screen size") return tr("Invalid port or native screen size.");
    if (value == "invalid rotation or quality") return tr("Invalid rotation or resolution setting.");
    if (value == "invalid frame rate or bitrate") return tr("Invalid frame rate or bitrate.");
    if (value == "session already active") return tr("A connection is already active.");
    if (value == "no active session") return tr("No active connection.");
    if (value == "control belongs to the session owner") return tr("Remote control belongs to the app that started this connection.");
    if (value == "unlock phone and wait for video first") return tr("Unlock the phone and wait for video before enabling remote control.");
    if (value == "receiver control channel disconnected") return tr("The receiver control channel disconnected.");
    if (value == "phone capture exited" || value == "capture exited") return tr("Screen capture stopped unexpectedly.");
    if (value == "capture produced no frames") return tr("Screen capture produced no frames.");
    if (value == "capture did not report native geometry") return tr("The phone screen size could not be detected. Enter it in advanced settings.");
    if (value == "no local network interface") return tr("Connect the phone to a local network before searching.");
    if (value == "local discovery unavailable") return tr("Local network discovery is unavailable. You can enter the receiver address manually.");
    if (value == "timed out") return tr("The connection timed out.");
    if (value.contains("Connection refused")) return tr("WinPlay is not accepting connections. Start receiving on the computer.");
    if (value.contains("No route to host") || value.contains("Network is unreachable")) return tr("WinPlay is unreachable. Check the phone's network connection.");
    if (value.contains("does not appear to be an IPv4 or IPv6 address")) return tr("Invalid IP address.");
    return value;
}

QString StatusText::state(const QString &value) {
    if (value == "stopped") return tr("Stopped");
    if (value == "stopping") return tr("Stopping");
    if (value == "waiting for WinPlay; start receiving on computer") return tr("Waiting for WinPlay. Start receiving on the computer.");
    if (value == "waiting to reconnect" || value == "waiting to reconnect; remote control revoked") return tr("Waiting to reconnect");
    const auto streaming = QRegularExpression("^streaming (\\d+)x(\\d+) target (\\d+)fps$").match(value);
    if (streaming.hasMatch())
        return tr("Streaming %1 × %2 · target %3 fps").arg(streaming.captured(1), streaming.captured(2), streaming.captured(3));
    const bool reconnecting = value.startsWith("reconnecting after ");
    if (reconnecting || value.startsWith("failed at ")) {
        const QString detail = value.mid(reconnecting ? 19 : 10);
        const int separator = detail.indexOf(": ");
        const QString stage = phase(separator < 0 ? detail : detail.left(separator));
        const QString reason = separator < 0 ? QString() : error(detail.mid(separator + 2));
        return (reconnecting ? tr("Reconnecting after %1: %2") : tr("Connection failed at %1: %2")).arg(stage, reason);
    }
    return value;
}
