import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: guide
    objectName: "connectionGuide"
    property bool firstRun: false
    property int step: backend.active ? 4 : 0
    property var chosenReceiver: null
    property string selectedReceiverId: ""
    readonly property bool landscape: width > height
    readonly property var setup: backend.setupState
    readonly property bool canContinue: step === 0
        ? !!setup.bluetooth_powered && !!setup.peer_name && !setup.bluetooth_error
        : step === 1 ? !!setup.network_connected
        : step === 2 ? !!setup.bluetooth_ready
        : step === 3 ? selectedReceiver() !== null : backend.streaming
    allowedOrientations: Orientation.All

    function selectedReceiver() {
        return receiverChoice.currentIndex >= 0 && receiverChoice.currentIndex < backend.receivers.length
            ? backend.receivers[receiverChoice.currentIndex] : null
    }
    function activateStep() {
        tapHint.stop()
        swipeHint.stop()
        flickable.contentY = 0
        backend.refreshSetup()
        if (step === 2) backend.prepareBluetooth()
        if (step === 3) backend.scan()
        hintDelay.restart()
    }
    function nextStep() {
        if (!canContinue) return
        if (step === 3) chosenReceiver = selectedReceiver()
        if (step === 4) {
            backend.finishGuide(true)
            pageStack.pop()
        } else {
            step++
        }
    }
    function connectReceiver() {
        if (chosenReceiver !== null && !backend.active)
            backend.startReceiver(chosenReceiver)
    }
    function stepTitle() {
        switch (step) {
        case 0: return qsTr("Pair with your computer")
        case 1: return qsTr("Join the same local network")
        case 2: return qsTr("Prepare the phone")
        case 3: return qsTr("Start receiving on the computer")
        default: return qsTr("Connect and share your screen")
        }
    }
    function stepDescription() {
        switch (step) {
        case 0: return qsTr("Turn on Bluetooth on both devices. Pair this phone with the receiving computer in system settings, and confirm the same pairing code on both devices. Pairing is only needed once.")
        case 1: return qsTr("Connect the phone and computer to the same router, or connect the phone to the computer's hotspot. Keep Bluetooth on. The video will use this local network.")
        case 2: return qsTr("Return to Sailconnect before starting the receiver. Preparing the phone lets WinPlay, LinuxPlay or MacPlay complete its Bluetooth handshake.")
        case 3: return qsTr("Open WinPlay, LinuxPlay or MacPlay on the computer. Select this paired phone, choose the local network or hotspot mode that matches your connection, then start receiving. Search again if it has not appeared.")
        default: return qsTr("Tap Connect below and wait for the phone screen to appear on the computer. Remote control is enabled by default while the phone is unlocked; you can turn it off on the main page.")
        }
    }
    function stepStatus() {
        switch (step) {
        case 0:
            if (!setup.bluetooth_available) return qsTr("Bluetooth is unavailable on the phone.")
            if (!setup.bluetooth_powered) return qsTr("Turn on the phone's Bluetooth in system settings.")
            if (setup.peer_name) return qsTr("Paired device: %1").arg(setup.peer_name)
            return qsTr("Pair with the receiving computer. If several devices are paired, connect that computer's Bluetooth so Sailconnect can identify it.")
        case 1:
            return setup.network_connected
                ? qsTr("Phone's local IP: %1").arg((setup.network_addresses || []).join(", ") || qsTr("IPv6 network"))
                : qsTr("The phone is not connected to a local network yet.")
        case 2: return backend.bluetoothStatus
        case 3: return backend.discoveryStatus
        default: return backend.status
        }
    }

    onStepChanged: if (status === PageStatus.Active) activateStep()
    onStatusChanged: {
        if (status === PageStatus.Active) activateStep()
        else { tapHint.stop(); swipeHint.stop(); hintDelay.stop() }
    }
    onCanContinueChanged: if (canContinue && status === PageStatus.Active) hintDelay.restart()

    Timer {
        interval: 2000
        repeat: true
        running: guide.status === PageStatus.Active
        onTriggered: backend.refreshSetup()
    }
    Connections {
        target: backend
        onReceiversChanged: receiverRefresh.restart()
    }
    Timer {
        id: receiverRefresh
        interval: 1
        onTriggered: {
            var selected = -1
            for (var i = 0; i < backend.receivers.length; ++i) {
                if (backend.receivers[i].id === guide.selectedReceiverId) { selected = i; break }
            }
            receiverChoice.currentIndex = selected >= 0 ? selected : backend.receivers.length > 0 ? 0 : -1
        }
    }
    Timer {
        id: hintDelay
        interval: 1500
        onTriggered: {
            if (guide.status !== PageStatus.Active) return
            if (guide.canContinue) tapHint.start()
            else if (flickable.contentHeight > flickable.height) swipeHint.start()
        }
    }

    SilicaFlickable {
        id: flickable
        objectName: "guideFlickable"
        anchors { top: parent.top; left: parent.left; right: parent.right; bottom: navigation.top }
        contentHeight: content.height
        clip: true
        onDraggingChanged: if (dragging) swipeHint.stop()
        PullDownMenu {
            MenuItem {
                text: qsTr("Skip for now")
                onClicked: pageStack.pop()
            }
        }
        Column {
            id: content
            objectName: "guideContent"
            width: parent.width
            spacing: guide.landscape ? Theme.paddingMedium : Theme.paddingLarge
            PageHeader { title: qsTr("Connection guide") }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: qsTr("Step %1 of %2").arg(guide.step + 1).arg(5)
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
            }
            Row {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                spacing: Theme.paddingSmall
                Repeater {
                    model: 5
                    Rectangle {
                        width: (parent.width - 4 * parent.spacing) / 5
                        height: Theme.paddingSmall
                        radius: height / 2
                        color: index <= guide.step ? Theme.highlightColor : Theme.secondaryColor
                        opacity: index <= guide.step ? 1 : 0.25
                    }
                }
            }
            Icon {
                visible: !guide.landscape
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(parent.width / 3, Theme.iconSizeExtraLarge * 1.5)
                height: width
                source: guide.step === 0 ? "image://theme/icon-m-bluetooth"
                    : guide.step === 1 ? "image://theme/icon-m-wlan"
                    : guide.step === 3 ? "image://theme/icon-m-search"
                    : Qt.resolvedUrl("../images/cover-sailconnect.png")
                fillMode: Image.PreserveAspectFit
                color: Theme.highlightColor
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: guide.stepTitle()
                wrapMode: Text.Wrap
                color: Theme.highlightColor
                font.pixelSize: Theme.fontSizeLarge
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: guide.stepDescription()
                wrapMode: Text.Wrap
            }
            Label {
                objectName: "guideStatus"
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: guide.stepStatus()
                wrapMode: Text.Wrap
                font.pixelSize: Theme.fontSizeSmall
                color: guide.canContinue ? Theme.highlightColor : Theme.secondaryColor
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                visible: guide.step === 0 && !!setup.peer_name || guide.step === 1
                text: guide.step === 0
                    ? qsTr("Make sure this is the receiving computer, rather than a headset or another paired device.")
                    : qsTr("This checks the phone's network. Confirm that the computer is on the same network too; guest Wi-Fi or client isolation can prevent discovery.")
                font.pixelSize: Theme.fontSizeExtraSmall
                color: Theme.secondaryColor
                wrapMode: Text.Wrap
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: guide.step < 2
                text: guide.step === 0 ? qsTr("Open Bluetooth settings") : qsTr("Open Wi-Fi settings")
                onClicked: backend.openSystemSettings(guide.step === 0 ? "bluetooth" : "wlan")
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: guide.step === 2 || guide.step === 3
                text: guide.step === 2 ? qsTr("Prepare Bluetooth") : qsTr("Search receivers")
                enabled: guide.step === 2 || !backend.discovering
                onClicked: guide.step === 2 ? backend.prepareBluetooth() : backend.scan()
            }
            ComboBox {
                id: receiverChoice
                objectName: "guideReceiver"
                width: parent.width
                visible: guide.step === 3
                label: qsTr("Receiver")
                Component.onCompleted: receiverRefresh.restart()
                menu: ContextMenu {
                    Repeater {
                        model: backend.receivers
                        MenuItem {
                            text: modelData.name + " · " +
                                (modelData.host.indexOf(":") >= 0 ? "[" + modelData.host + "]" : modelData.host) + ":" + modelData.port
                            onClicked: guide.selectedReceiverId = modelData.id
                        }
                    }
                }
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                visible: guide.step === 4 && guide.chosenReceiver !== null
                text: guide.chosenReceiver ? guide.chosenReceiver.name + " · " + guide.chosenReceiver.host + ":" + guide.chosenReceiver.port : ""
                wrapMode: Text.Wrap
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
            }
            Button {
                objectName: "guideConnect"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: guide.step === 4 && !backend.active
                enabled: guide.chosenReceiver !== null
                text: qsTr("Connect")
                onClicked: guide.connectReceiver()
            }
            Button {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: guide.step === 4 && backend.active && !backend.streaming
                text: qsTr("Stop")
                onClicked: backend.stop()
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                visible: guide.step === 4 && backend.streaming
                text: qsTr("Screen sharing has started. Check the picture on the computer, then finish the guide.")
                wrapMode: Text.Wrap
                color: Theme.highlightColor
            }
            Item { width: 1; height: Theme.paddingLarge }
        }
        VerticalScrollDecorator {}
    }

    Column {
        id: navigation
        objectName: "guideNavigation"
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        spacing: Theme.paddingMedium
        Row {
            x: Theme.horizontalPageMargin
            width: parent.width - 2*x
            spacing: Theme.paddingMedium
            Button {
                width: (parent.width - parent.spacing) / 2
                text: qsTr("Previous")
                enabled: guide.step > 0
                onClicked: guide.step--
            }
            Button {
                id: nextButton
                objectName: "guideNext"
                width: (parent.width - parent.spacing) / 2
                text: guide.step === 4 ? qsTr("Finish") : qsTr("Continue")
                enabled: guide.canContinue
                onClicked: guide.nextStep()
            }
        }
        Label {
            x: Theme.horizontalPageMargin
            width: parent.width - 2*x
            text: qsTr("You can reopen this guide from the main page's pull-down menu.")
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }
        Item { width: 1; height: Theme.paddingLarge }
    }
    TapInteractionHint {
        id: tapHint
        parent: nextButton
        anchors.centerIn: parent
        loops: 2
    }
    TouchInteractionHint {
        id: swipeHint
        direction: TouchInteraction.Up
        interactionMode: TouchInteraction.Swipe
        loops: 2
    }
}
