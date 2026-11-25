Name: harbour-sailconnect
Version: 0.1.0
Release: 12
Summary: SailfishOS phone screen over CarPlay
License: GPL-3.0-or-later AND LGPL-2.1-or-later
Source0: %{name}-%{version}.tar.gz
BuildArch: aarch64
Requires: python3-base >= 3.7
Requires: python3-dbus
Requires: python3-gobject
Requires: sailfishsilica-qt5
Requires: libsailfishapp
Requires: qt5-qtdeclarative
Requires: qt5-qtdbus
Requires: wayland
Requires: bluez5
Requires: /bin/su
Requires: openssl-libs
Requires(post): systemd
Requires(preun): systemd

%description
Experimental LAN CarPlay source for the existing lipstick desktop. Includes
H.264 screen capture, default-enabled single-contact remote input and
English and Chinese interfaces. Discovers LAN receivers automatically and uses
paired Bluetooth iAP2 bootstrap for existing WinPlay/LinuxPlay/MacPlay receivers.
Screen video uses the local network. Requires uinput.

%prep
%setup -q

%build
# Target binaries are built by build-arm.sh before packaging.
test -x rpm/payload/carlife-capture
test -x rpm/payload/harbour-sailconnect

%install
mkdir -p %{buildroot}/opt/sailconnect
cp -r carplay_proto sailconnect %{buildroot}/opt/sailconnect/
install -m 2755 rpm/payload/carlife-capture %{buildroot}/opt/sailconnect/
install -D -m 0755 rpm/payload/harbour-sailconnect %{buildroot}/usr/bin/harbour-sailconnect
install -D -m 0644 app/main.qml %{buildroot}/usr/share/harbour-sailconnect/qml/main.qml
mkdir -p %{buildroot}/usr/share/harbour-sailconnect/qml/cover
install -m 0644 app/cover/*.qml %{buildroot}/usr/share/harbour-sailconnect/qml/cover/
mkdir -p %{buildroot}/usr/share/harbour-sailconnect/qml/pages
install -m 0644 app/pages/*.qml %{buildroot}/usr/share/harbour-sailconnect/qml/pages/
printf '%s\n' '%{version}-%{release}' > %{buildroot}/usr/share/harbour-sailconnect/version
mkdir -p %{buildroot}/usr/share/harbour-sailconnect/qml/images
install -m 0644 app/images/cover-sailconnect.png app/images/cover-sailconnect.svg %{buildroot}/usr/share/harbour-sailconnect/qml/images/
mkdir -p %{buildroot}/usr/share/harbour-sailconnect/translations
install -m 0644 rpm/payload/translations/*.qm %{buildroot}/usr/share/harbour-sailconnect/translations/
install -D -m 0644 rpm/harbour-sailconnect.desktop %{buildroot}/usr/share/applications/harbour-sailconnect.desktop
install -D -m 0644 rpm/harbour-sailconnect.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/harbour-sailconnect.svg
for size in 86 108 128 172; do
    install -D -m 0644 rpm/icons/${size}x${size}/harbour-sailconnect.png %{buildroot}/usr/share/icons/hicolor/${size}x${size}/apps/harbour-sailconnect.png
done
install -D -m 0644 rpm/sailconnect.service %{buildroot}/usr/lib/systemd/system/sailconnect.service
install -D -m 0644 rpm/org.sailconnect.Control.conf %{buildroot}/etc/dbus-1/system.d/org.sailconnect.Control.conf
mkdir -p %{buildroot}/var/lib/sailconnect
chmod 0700 %{buildroot}/var/lib/sailconnect
install -D -m 0644 LICENSE %{buildroot}/usr/share/licenses/%{name}/LICENSE
install -m 0644 THIRD_PARTY.md %{buildroot}/usr/share/licenses/%{name}/THIRD_PARTY.md
install -m 0644 third_party/GPL-3.txt third_party/LGPL-2.1.txt %{buildroot}/usr/share/licenses/%{name}/

%post
systemctl daemon-reload
systemctl enable sailconnect.service >/dev/null 2>&1 || :
systemctl restart sailconnect.service || :

%preun
if [ "$1" -eq 0 ]; then
    systemctl stop sailconnect.service || :
    systemctl disable sailconnect.service >/dev/null 2>&1 || :
fi

%postun
systemctl daemon-reload

%files
%dir /opt/sailconnect
/opt/sailconnect/carplay_proto
/opt/sailconnect/sailconnect
%attr(2755,root,privileged) /opt/sailconnect/carlife-capture
/usr/bin/harbour-sailconnect
/usr/share/harbour-sailconnect
/usr/share/applications/harbour-sailconnect.desktop
/usr/share/icons/hicolor/scalable/apps/harbour-sailconnect.svg
/usr/share/icons/hicolor/86x86/apps/harbour-sailconnect.png
/usr/share/icons/hicolor/108x108/apps/harbour-sailconnect.png
/usr/share/icons/hicolor/128x128/apps/harbour-sailconnect.png
/usr/share/icons/hicolor/172x172/apps/harbour-sailconnect.png
/usr/lib/systemd/system/sailconnect.service
%config /etc/dbus-1/system.d/org.sailconnect.Control.conf
%dir %attr(0700,root,root) /var/lib/sailconnect
/usr/share/licenses/%{name}
