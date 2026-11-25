import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: page
    objectName: "connectionPage"
    property bool initialGuideShown: false
    function openGuide(firstRun) {
        pageStack.push(Qt.resolvedUrl("ConnectionGuide.qml"), {firstRun: !!firstRun})
    }
    function openAbout() {
        pageStack.push(Qt.resolvedUrl("AboutPage.qml"))
    }
    onStatusChanged: {
        if (status === PageStatus.Active) {
            var saved = backend.settings()
            preferredHost = saved.host || ""
            host.text = preferredHost
            for (var i = 0; i < backend.receivers.length; ++i) {
                if (backend.receivers[i].host === preferredHost) {
                    receiverChoice.currentIndex = i
                    selectedReceiverId = backend.receivers[i].id
                    manualAddress.checked = savedBool(saved.manualAddress, false)
                    break
                }
            }
        }
        if (status === PageStatus.Active && !initialGuideShown) {
            initialGuideShown = true
            if (!backend.guideCompleted && !backend.active)
                initialGuideDelay.start()
        }
    }
    Timer {
        id: initialGuideDelay
        interval: 1
        onTriggered: if (page.status === PageStatus.Active && !backend.active)
            page.openGuide(true)
    }
    property bool advancedOpen: false
    property string selectedReceiverId: ""
    property string preferredHost: ""
    function savedBool(value, fallback) {
        return value === undefined ? fallback : String(value) === "true" || String(value) === "1"
    }
    function selectedReceiver() {
        return receiverChoice.currentIndex >= 0 && receiverChoice.currentIndex < backend.receivers.length
                ? backend.receivers[receiverChoice.currentIndex] : null
    }
    function connectReceiver() {
        var target = manualAddress.checked ? null : selectedReceiver()
        if (target) selectedReceiverId = target.id
        var address = target ? target.host : host.text
        var receiverPort = target ? target.port : parseInt(port.text)
        var network = target ? target.interface : iface.text
        backend.saveSettings({host: address, port: String(receiverPort), iface: network,
            nativeWidth: nw.text, nativeHeight: nh.text, nativeAuto: captureAuto.checked,
            manualAddress: manualAddress.checked, rotation: rotationChoice.currentIndex,
            quality: qualityChoice.currentIndex, fps: fpsChoice.currentIndex, bitrate: bitrate.text})
        host.text = address
        port.text = String(receiverPort)
        backend.start(address, receiverPort, network,
            captureAuto.checked ? 0 : parseInt(nw.text), captureAuto.checked ? 0 : parseInt(nh.text),
            [0,90,180,270][rotationChoice.currentIndex], qualityChoice.currentIndex,
            [15,30,60][fpsChoice.currentIndex], parseInt(bitrate.text))
    }
    Component.onCompleted: {
        var s = backend.settings()
        host.text = s.host || ""
        preferredHost = host.text
        port.text = s.port || "17000"
        iface.text = s.iface || ""
        nw.text = s.nativeWidth || "1080"
        nh.text = s.nativeHeight || "2160"
        captureAuto.checked = savedBool(s.nativeAuto, true)
        manualAddress.checked = savedBool(s.manualAddress, false)
        rotationChoice.currentIndex = s.rotation || 0
        qualityChoice.currentIndex = s.quality === undefined ? 3 : s.quality
        fpsChoice.currentIndex = s.fps === undefined ? 1 : s.fps
        bitrate.text = s.bitrate || "4000000"
        if (backend.guideCompleted) backend.scan()
    }
    Connections {
        target: backend
        onReceiversChanged: {
            var index = -1
            for (var i = 0; i < backend.receivers.length; ++i) {
                if (backend.receivers[i].id === page.selectedReceiverId ||
                        (!page.selectedReceiverId && backend.receivers[i].host === page.preferredHost)) {
                    index = i
                    break
                }
            }
            receiverChoice.currentIndex = index >= 0 ? index : backend.receivers.length ? 0 : -1
        }
    }
    allowedOrientations: Orientation.All
    SilicaFlickable {
        anchors.fill: parent
        contentHeight: content.height
        PullDownMenu {
            MenuItem {
                text: qsTr("About")
                onClicked: page.openAbout()
            }
            MenuItem {
                text: qsTr("Connection guide")
                onClicked: page.openGuide(false)
            }
        }
        Column {
            id: content
            width: parent.width
            spacing: Theme.paddingMedium
            PageHeader { title: "Sailconnect" }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                wrapMode: Text.Wrap
                text: backend.status
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                wrapMode: Text.Wrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                text: backend.bluetoothStatus
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: backend.discovering ? qsTr("Searching…") : qsTr("Search receivers")
                enabled: !backend.discovering
                onClicked: backend.scan()
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                wrapMode: Text.Wrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                text: backend.discoveryStatus
            }
            ComboBox {
                id: receiverChoice
                width: parent.width
                visible: !manualAddress.checked
                enabled: backend.receivers.length > 0 && !backend.active
                label: qsTr("Receiver")
                menu: ContextMenu {
                    Repeater {
                        model: backend.receivers
                        MenuItem {
                            text: modelData.name + " · " +
                                  (modelData.host.indexOf(":") >= 0 ? "[" + modelData.host + "]" : modelData.host) + ":" + modelData.port
                            onClicked: page.selectedReceiverId = modelData.id
                        }
                    }
                }
            }
            TextSwitch {
                id: manualAddress
                text: qsTr("Enter address manually")
                description: qsTr("Use this if your receiver is not discovered.")
            }
            Column {
                width: parent.width
                visible: manualAddress.checked
                TextField { id: host; width: parent.width; label: qsTr("Receiver IP address"); placeholderText: "192.168.137.1" }
                TextField { id: port; width: parent.width; label: qsTr("CarPlay RTSP port"); text: "17000"; inputMethodHints: Qt.ImhDigitsOnly }
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Connect")
                enabled: !backend.active && (manualAddress.checked ? host.text.length > 0 : page.selectedReceiver() !== null)
                onClicked: page.connectReceiver()
            }
            TextSwitch {
                text: qsTr("Remote control")
                description: qsTr("Enabled by default for each connection. Locking the phone turns it off.")
                checked: backend.allowed
                automaticCheck: false
                onClicked: backend.allow(!checked)
            }
            Button {
                objectName: "stopButton"
                anchors.horizontalCenter: parent.horizontalCenter
                text: qsTr("Stop")
                visible: backend.active
                enabled: backend.active
                onClicked: backend.stop()
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                text: page.advancedOpen ? qsTr("Hide advanced settings") : qsTr("Advanced settings")
                onClicked: page.advancedOpen = !page.advancedOpen
            }
            Column {
                width: parent.width
                spacing: Theme.paddingMedium
                visible: page.advancedOpen
                TextSwitch {
                    id: captureAuto
                    text: qsTr("Automatic screen size")
                    checked: true
                    description: backend.nativeWidth > 0
                        ? qsTr("Detected screen: %1 × %2").arg(backend.nativeWidth).arg(backend.nativeHeight)
                        : qsTr("Detect the phone screen size automatically.")
                    onCheckedChanged: {
                        if (!checked && backend.nativeWidth > 0) {
                            nw.text = String(backend.nativeWidth)
                            nh.text = String(backend.nativeHeight)
                        }
                    }
                }
                Row {
                    width: parent.width
                    visible: !captureAuto.checked
                    TextField { id: nw; width: parent.width/2; label: qsTr("Native width"); text: "1080"; inputMethodHints: Qt.ImhDigitsOnly }
                    TextField { id: nh; width: parent.width/2; label: qsTr("Native height"); text: "2160"; inputMethodHints: Qt.ImhDigitsOnly }
                }
                TextField { id: iface; width: parent.width; label: qsTr("Network interface"); placeholderText: qsTr("Automatic") }
                ComboBox {
                    id: rotationChoice; width: parent.width; label: qsTr("Fixed capture rotation")
                    menu: ContextMenu { MenuItem { text: "0°" } MenuItem { text: "90°" } MenuItem { text: "180°" } MenuItem { text: "270°" } }
                }
                ComboBox {
                    id: qualityChoice; width: parent.width; label: qsTr("Receiver resolution")
                    menu: ContextMenu { MenuItem { text: qsTr("Full") } MenuItem { text: "5/6" } MenuItem { text: "2/3" } MenuItem { text: qsTr("Automatic") } }
                }
                ComboBox {
                    id: fpsChoice; width: parent.width; label: qsTr("Frame rate"); currentIndex: 1
                    menu: ContextMenu { MenuItem { text: "15" } MenuItem { text: "30" } MenuItem { text: "60" } }
                }
                TextField { id: bitrate; width: parent.width; label: qsTr("Bitrate (bits/s)"); text: "4000000"; inputMethodHints: Qt.ImhDigitsOnly }
            }
            Label {
                x: Theme.horizontalPageMargin; width: parent.width - 2*x
                wrapMode: Text.Wrap; color: Theme.secondaryColor; font.pixelSize: Theme.fontSizeSmall
                text: qsTr("Pair the phone and computer in system Bluetooth settings once. Open Sailconnect first, then start receiving in WinPlay, LinuxPlay or MacPlay on the same local network. Choose a receiver and connect.")
            }
        }
        VerticalScrollDecorator {}
    }
}
