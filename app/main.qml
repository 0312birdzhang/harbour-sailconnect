import QtQuick 2.0
import Sailfish.Silica 1.0
import "cover"
import "pages"

ApplicationWindow {
    initialPage: Component { MainPage {} }
    cover: Component { CoverPage {} }
    Component.onDestruction: if (backend) backend.stop()
}
