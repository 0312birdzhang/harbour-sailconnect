import QtQuick 2.0
import Sailfish.Silica 1.0

CoverBackground {
    id: cover

    Column {
        objectName: "coverContent"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -Theme.paddingLarge
        width: parent.width - 2 * Theme.paddingLarge
        spacing: Theme.paddingSmall

        Label {
            width: parent.width
            text: "Sailconnect"
            color: Theme.highlightColor
            font.pixelSize: Theme.fontSizeSmall
            horizontalAlignment: Text.AlignHCenter
        }

        Icon {
            objectName: "coverIllustration"
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            height: width * 260 / 360
            source: Qt.resolvedUrl("../images/cover-sailconnect.png")
            color: Theme.highlightColor
            opacity: backend.active ? 0.9 : 0.55
            fillMode: Image.PreserveAspectFit
        }

        Label {
            width: parent.width
            text: backend.coverStatus
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.primaryColor
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Label {
            width: parent.width
            visible: text.length > 0
            text: backend.coverDetails
            font.pixelSize: Theme.fontSizeExtraSmall
            color: Theme.secondaryColor
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }

    CoverActionList {
        objectName: "coverActions"
        enabled: backend.active
        CoverAction {
            iconSource: "image://theme/icon-cover-cancel"
            onTriggered: backend.stop()
        }
    }
}
