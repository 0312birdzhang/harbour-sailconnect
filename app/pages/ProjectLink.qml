import QtQuick 2.0
import Sailfish.Silica 1.0

BackgroundItem {
    id: project
    objectName: "projectLink"
    property string title
    property string author
    property string description
    property string url
    height: details.height + 2 * Theme.paddingMedium
    onClicked: Qt.openUrlExternally(url)

    Column {
        id: details
        x: Theme.paddingMedium
        y: Theme.paddingMedium
        width: parent.width - 2*x - arrow.width - Theme.paddingMedium
        spacing: Theme.paddingSmall
        Label {
            width: parent.width
            text: project.title
            color: Theme.highlightColor
            font.pixelSize: Theme.fontSizeMedium
            wrapMode: Text.Wrap
        }
        Label {
            width: parent.width
            text: project.author
            visible: text.length > 0
            color: Theme.secondaryColor
            font.pixelSize: Theme.fontSizeExtraSmall
            wrapMode: Text.Wrap
        }
        Label {
            width: parent.width
            text: project.description
            visible: text.length > 0
            color: Theme.secondaryColor
            font.pixelSize: Theme.fontSizeSmall
            wrapMode: Text.Wrap
        }
    }
    Icon {
        id: arrow
        anchors { right: parent.right; rightMargin: Theme.paddingMedium; verticalCenter: parent.verticalCenter }
        source: "image://theme/icon-m-right"
        width: Theme.iconSizeSmall
        height: width
        opacity: 0.5
    }
}
