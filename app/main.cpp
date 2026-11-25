#include <QtQuick>
#include <QtDBus>
#include <sailfishapp.h>
#include "status_text.h"

class Backend : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(bool allowed READ allowed NOTIFY changed)
    Q_PROPERTY(bool active READ active NOTIFY changed)
    Q_PROPERTY(QVariantList receivers READ receivers NOTIFY receiversChanged)
    Q_PROPERTY(bool discovering READ discovering NOTIFY discoveryChanged)
    Q_PROPERTY(QString discoveryStatus READ discoveryStatus NOTIFY discoveryChanged)
    Q_PROPERTY(int nativeWidth READ nativeWidth NOTIFY changed)
    Q_PROPERTY(int nativeHeight READ nativeHeight NOTIFY changed)
    Q_PROPERTY(QString bluetoothStatus READ bluetoothStatus NOTIFY changed)
    Q_PROPERTY(QString coverStatus READ coverStatus NOTIFY changed)
    Q_PROPERTY(QString coverDetails READ coverDetails NOTIFY changed)
    Q_PROPERTY(QVariantMap setupState READ setupState NOTIFY changed)
    Q_PROPERTY(bool guideCompleted READ guideCompleted NOTIFY changed)
    Q_PROPERTY(bool streaming READ streaming NOTIFY changed)
    Q_PROPERTY(QString packageVersion READ packageVersion CONSTANT)
public:
    Backend() : api("org.sailconnect.Control", "/org/sailconnect/Control",
                    "org.sailconnect.Control", QDBusConnection::systemBus()) {
        api.setTimeout(70000); // Sailplay may need 45 seconds for service cleanup.
        connect(&timer, &QTimer::timeout, this, &Backend::poll);
        timer.start(1000);
        poll();
    }
    QString status() const { return text; }
    bool allowed() const { return control; }
    bool active() const { return sessionActive; }
    QVariantList receivers() const { return receiverList; }
    bool discovering() const { return scanning; }
    QString discoveryStatus() const { return discoveryText; }
    int nativeWidth() const { return detectedWidth; }
    int nativeHeight() const { return detectedHeight; }
    QString bluetoothStatus() const { return bluetoothText; }
    QString coverStatus() const { return coverText; }
    QString coverDetails() const { return coverInfo; }
    QVariantMap setupState() const { return setupInfo; }
    bool guideCompleted() const { return QSettings().value("guideCompleted", false).toBool(); }
    bool streaming() const { return videoReady; }
    QString packageVersion() const {
        QFile version("/usr/share/harbour-sailconnect/version");
        return version.open(QIODevice::ReadOnly) ? QString::fromUtf8(version.readAll()).trimmed() : QString();
    }
    Q_INVOKABLE void prepareBluetooth() {
        const QDBusMessage prepared = api.call("PrepareBluetooth");
        bluetoothText = prepared.type() == QDBusMessage::ErrorMessage
            ? tr("Bluetooth setup needed: %1").arg(StatusText::error(prepared.errorMessage()))
            : tr("Bluetooth ready for iAP2. Video uses the local network.");
        emit changed();
        refreshSetup();
    }
    Q_INVOKABLE void scan() {
        prepareBluetooth();
        const QDBusMessage reply = api.call("ScanReceivers");
        if (reply.type() == QDBusMessage::ErrorMessage) {
            discoveryText = tr("Cannot search for receivers: %1").arg(StatusText::error(reply.errorMessage()));
            scanning = false;
            emit discoveryChanged();
        } else { pollDiscovery(); }
    }
    Q_INVOKABLE void refreshSetup() {
        QDBusReply<QString> reply = api.call("SetupStatus");
        setupInfo = reply.isValid()
            ? QJsonDocument::fromJson(reply.value().toUtf8()).object().toVariantMap()
            : QVariantMap();
        emit changed();
    }
    Q_INVOKABLE void finishGuide(bool completed) {
        if (completed) {
            QSettings().setValue("guideCompleted", true);
            emit changed();
        }
    }
    Q_INVOKABLE void openSystemSettings(QString section) {
        if (section != "bluetooth" && section != "wlan") return;
        QDBusInterface settingsApi("com.jolla.settings", "/com/jolla/settings/ui",
                                   "com.jolla.settings.ui", QDBusConnection::sessionBus());
        const auto reply = settingsApi.call("showPage", "system_settings/connectivity/" + section);
        if (reply.type() == QDBusMessage::ErrorMessage)
            check(reply);
    }
    Q_INVOKABLE void startReceiver(QVariantMap receiver) {
        QSettings saved;
        saved.setValue("host", receiver.value("host"));
        saved.setValue("port", receiver.value("port"));
        saved.setValue("iface", receiver.value("interface"));
        saved.setValue("manualAddress", false);
        const int rotationIndex = qBound(0, saved.value("rotation", 0).toInt(), 3);
        const int fpsIndex = qBound(0, saved.value("fps", 1).toInt(), 2);
        const int rates[] = {15, 30, 60};
        const bool nativeAuto = saved.value("nativeAuto", true).toBool();
        start(receiver.value("host").toString(), receiver.value("port").toInt(),
              receiver.value("interface").toString(),
              nativeAuto ? 0 : saved.value("nativeWidth", 1080).toInt(),
              nativeAuto ? 0 : saved.value("nativeHeight", 2160).toInt(),
              rotationIndex * 90, qBound(0, saved.value("quality", 3).toInt(), 3),
              rates[fpsIndex], saved.value("bitrate", 4000000).toInt());
    }
    Q_INVOKABLE void start(QString host, int port, QString iface, int nw, int nh,
                            int rotation, int quality, int fps, int bitrate) {
        check(api.callWithArgumentList(QDBus::Block, "StartWithControl",
              QVariantList() << host << port << iface << nw << uint(nh) << rotation << quality << fps << bitrate << control));
    }
    Q_INVOKABLE void stop() { check(api.call("Stop")); }
    Q_INVOKABLE void allow(bool enabled) {
        if (sessionActive) check(api.call("AllowControl", enabled));
        else { control = enabled; emit changed(); }
    }
    Q_INVOKABLE QVariantMap settings() {
        QSettings saved;
        QVariantMap result;
        for (const QString &key : saved.allKeys()) result[key] = saved.value(key);
        if (!result.contains("nativeHeight")) {
            QFile modes("/sys/class/drm/card0-DSI-1/modes");
            if (modes.open(QIODevice::ReadOnly)) {
                const QString mode = QString::fromUtf8(modes.readLine()).trimmed();
                QRegExp size("^(\\d+)x(\\d+)$");
                if (size.exactMatch(mode)) {
                    result["nativeWidth"] = size.cap(1);
                    result["nativeHeight"] = size.cap(2);
                }
            }
        }
        return result;
    }
    Q_INVOKABLE void saveSettings(QVariantMap values) {
        QSettings saved;
        for (auto i = values.constBegin(); i != values.constEnd(); ++i) saved.setValue(i.key(), i.value());
    }
signals:
    void changed();
    void receiversChanged();
    void discoveryChanged();
private:
    QDBusInterface api;
    QTimer timer;
    QString text;
    QString actionError;
    bool control = true;
    bool sessionActive = false;
    QVariantList receiverList;
    QByteArray receiverJson;
    bool scanning = false;
    QString discoveryText;
    QString bluetoothText;
    bool bluetoothReady = false;
    QString coverText;
    QString coverInfo;
    QVariantMap setupInfo;
    bool videoReady = false;
    int detectedWidth = 0;
    int detectedHeight = 0;
    void pollDiscovery() {
        QDBusReply<QString> reply = api.call("DiscoveryStatus");
        if (!reply.isValid()) return;
        const QJsonObject info = QJsonDocument::fromJson(reply.value().toUtf8()).object();
        const QJsonArray found = info["receivers"].toArray();
        const QByteArray serialized = QJsonDocument(found).toJson(QJsonDocument::Compact);
        if (serialized != receiverJson) {
            receiverJson = serialized;
            receiverList = found.toVariantList();
            emit receiversChanged();
        }
        const bool busy = info["scanning"].toBool();
        QString message;
        if (!info["error"].toString().isEmpty()) message = StatusText::error(info["error"].toString());
        else if (busy) message = tr("Searching for receivers…");
        else if (found.isEmpty()) message = tr("No receivers found. Start receiving on your computer, then search again.");
        else message = tr("Receivers found: %1").arg(found.size());
        if (busy != scanning || message != discoveryText) {
            scanning = busy;
            discoveryText = message;
            emit discoveryChanged();
        }
    }
    void check(const QDBusMessage &reply) {
        if (reply.type() == QDBusMessage::ErrorMessage) {
            actionError = StatusText::error(reply.errorMessage());
            qWarning() << "Sailconnect action failed:" << reply.errorName() << reply.errorMessage();
            text = actionError; emit changed();
        } else { actionError.clear(); poll(); }
    }
    void poll() {
        QDBusReply<QString> reply = api.call("Status");
        if (!reply.isValid()) {
            text = tr("Background service unavailable: %1").arg(StatusText::error(reply.error().message()));
            sessionActive = false;
            videoReady = false;
            coverText = tr("Service unavailable");
            coverInfo.clear();
        }
        else {
            auto obj = QJsonDocument::fromJson(reply.value().toUtf8()).object();
            const QString rawState = obj["state"].toString();
            videoReady = rawState.startsWith("streaming");
            const bool ready = obj["bluetooth_ready"].toBool();
            if (ready)
                bluetoothText = tr("Bluetooth ready for iAP2. Video uses the local network.");
            else if (bluetoothReady || bluetoothText.isEmpty())
                bluetoothText = tr("Search again to prepare Bluetooth before starting the receiver.");
            bluetoothReady = ready;
            if (obj["native_width"].toInt() > 0 && obj["native_height"].toInt() > 0) {
                detectedWidth = obj["native_width"].toInt();
                detectedHeight = obj["native_height"].toInt();
            }
            const bool wasActive = sessionActive;
            sessionActive = obj.contains("active") ? obj["active"].toBool() : rawState != "stopped";
            coverInfo.clear();
            if (rawState.startsWith("streaming")) {
                coverText = tr("Screen sharing");
                const auto size = QRegularExpression("^streaming (\\d+)x(\\d+)").match(rawState);
                if (size.hasMatch()) coverInfo = size.captured(1) + " × " + size.captured(2);
            } else if (rawState == "stopping") coverText = StatusText::state(rawState);
            else if (sessionActive && (rawState.startsWith("reconnecting") || rawState == "waiting to reconnect"))
                coverText = tr("Reconnecting…");
            else if (sessionActive) coverText = tr("Connecting…");
            else coverText = tr("Ready to connect");
            if (sessionActive) control = obj["control"].toBool();
            else if (wasActive) control = true;
            text = StatusText::state(rawState);
            if (obj["locked"].toBool()) text += tr(" · phone locked");
            if (rawState.startsWith("streaming") && obj["fps"].toDouble() > 0)
                text += tr(" · actual %1 fps").arg(QLocale().toString(obj["fps"].toDouble(), 'f', 1));
            if (rawState.startsWith("streaming")) text += control ? tr(" · remote control") : tr(" · view only");
        }
        if (!actionError.isEmpty())
            text = actionError;
        emit changed();
        pollDiscovery();
    }
};

int main(int argc, char **argv) {
    QScopedPointer<QGuiApplication> app(SailfishApp::application(argc, argv));
    app->setOrganizationName("sailconnect");
    app->setApplicationName("harbour-sailconnect");
    QTranslator translator;
    const QLocale locale;
    QString language = locale.name();
    if (locale.language() == QLocale::Chinese)
        language = locale.script() == QLocale::TraditionalHanScript ? "zh_TW" : "zh_CN";
    if (translator.load("harbour-sailconnect_" + language,
                        "/usr/share/harbour-sailconnect/translations"))
        app->installTranslator(&translator);
    QScopedPointer<QQuickView> view(SailfishApp::createView());
    Backend backend;
    view->rootContext()->setContextProperty("backend", &backend);
    view->setSource(QUrl("/usr/share/harbour-sailconnect/qml/main.qml"));
    view->show();
    return app->exec();
}
#include "main.moc"
