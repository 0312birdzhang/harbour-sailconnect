import QtQuick 2.0
import Sailfish.Silica 1.0

Page {
    id: about
    objectName: "aboutPage"
    allowedOrientations: Orientation.All
    readonly property int columns: width > height ? 2 : 1
    SilicaFlickable {
        id: flickable
        objectName: "aboutFlickable"
        anchors.fill: parent
        contentHeight: content.height
        Column {
            id: content
            objectName: "aboutContent"
            width: parent.width
            spacing: Theme.paddingMedium
            PageHeader { title: qsTr("About") }
            Image {
                objectName: "aboutIcon"
                anchors.horizontalCenter: parent.horizontalCenter
                width: Theme.itemSizeExtraLarge
                height: width
                source: "file:///usr/share/icons/hicolor/172x172/apps/harbour-sailconnect.png"
                fillMode: Image.PreserveAspectFit
            }
            Label {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: "Sailconnect"
                color: Theme.highlightColor
                font.pixelSize: Theme.fontSizeExtraLarge
            }
            Label {
                objectName: "aboutVersion"
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: qsTr("Version %1").arg(backend.packageVersion)
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: qsTr("Share your Sailfish OS phone screen with a computer or another device, with remote touch control over the local network.")
            }
            Item { width: 1; height: Theme.paddingSmall }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.secondaryColor
                text: qsTr("Author")
            }
            BackgroundItem {
                anchors.horizontalCenter: parent.horizontalCenter
                width: authorLabel.width + 2 * Theme.paddingLarge
                height: Theme.itemSizeSmall
                onClicked: Qt.openUrlExternally("https://github.com/0312birdzhang")
                Label {
                    id: authorLabel
                    anchors.centerIn: parent
                    text: "0312birdzhang"
                    color: Theme.highlightColor
                }
            }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: qsTr("License: %1").arg("GPL-3.0-or-later")
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
            }

            SectionHeader { text: qsTr("Receiver apps") }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: qsTr("Open a project to find its source code, releases and setup instructions.")
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeSmall
                wrapMode: Text.Wrap
            }
            Flow {
                x: Theme.horizontalPageMargin - Theme.paddingMedium
                width: parent.width - 2*x
                Repeater {
                    model: [
                        {name: "WinPlay", platform: "Windows", url: "https://github.com/Roylyl/WinPlay"},
                        {name: "MacPlay", platform: "macOS", url: "https://github.com/Roylyl/MacPlay"},
                        {name: "LinuxPlay", platform: "Linux", url: "https://github.com/Roylyl/LinuxPlay"},
                        {name: "AndroidPlay", platform: "Android", url: "https://github.com/Roylyl/AndroidPlay"}
                    ]
                    ProjectLink {
                        width: parent.width / about.columns
                        title: modelData.name
                        author: "Roylyl"
                        description: modelData.platform
                        url: modelData.url
                    }
                }
            }

            SectionHeader { text: qsTr("Reference projects") }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: qsTr("Thanks to the projects that made Sailconnect possible. Upstream components retain their respective licenses and copyright notices.")
                font.pixelSize: Theme.fontSizeSmall
                wrapMode: Text.Wrap
            }
            Flow {
                x: Theme.horizontalPageMargin - Theme.paddingMedium
                width: parent.width - 2*x
                Repeater {
                    model: [
                        {name: "Sailplay", author: "0312birdzhang", url: "https://github.com/0312birdzhang/harbour-sailplay", detail: qsTr("CarPlay pairing, encrypted transport, screen projection and touch input.")},
                        {name: "Imira", author: "JimKnopfIoT", url: "https://github.com/JimKnopfIoT/harbour-imira", detail: qsTr("Screen capture, conversion and convergence pipeline.")},
                        {name: "screencast", author: "CODeRUS", url: "https://github.com/CODeRUS/screencast", detail: qsTr("Lipstick screen recording reference.")}
                    ]
                    ProjectLink {
                        width: parent.width / about.columns
                        title: modelData.name
                        author: modelData.author
                        description: modelData.detail
                        url: modelData.url
                    }
                }
            }
            SectionHeader { text: qsTr("Built with") }
            Flow {
                x: Theme.horizontalPageMargin - Theme.paddingMedium
                width: parent.width - 2*x
                Repeater {
                    model: [
                        {name: "Qt", url: "https://www.qt.io/", detail: qsTr("Application framework")},
                        {name: "Sailfish Silica", url: "https://docs.sailfishos.org/Reference/Silica/", detail: qsTr("Native interface and interaction hints")},
                        {name: "x264", url: "https://www.videolan.org/developers/x264.html", detail: qsTr("H.264 video encoding")},
                        {name: "BlueZ", url: "https://www.bluez.org/", detail: qsTr("Bluetooth connection")},
                        {name: "ConnMan", url: "https://git.kernel.org/pub/scm/network/connman/connman.git/", detail: qsTr("Network settings")},
                        {name: "OpenSSL", url: "https://www.openssl.org/", detail: qsTr("Encrypted pairing and transport")}
                    ]
                    ProjectLink {
                        width: parent.width / about.columns
                        title: modelData.name
                        description: modelData.detail
                        url: modelData.url
                    }
                }
            }
            Item { width: 1; height: Theme.paddingSmall }
            Label {
                x: Theme.horizontalPageMargin
                width: parent.width - 2*x
                text: qsTr("The release includes the corresponding source code and third-party license notices.")
                color: Theme.secondaryColor
                font.pixelSize: Theme.fontSizeExtraSmall
                wrapMode: Text.Wrap
            }
            Item { width: 1; height: Theme.paddingLarge }
        }
        VerticalScrollDecorator {}
    }
}
