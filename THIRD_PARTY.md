# Reused code

`carplay_proto/` and `display-source/capture/` were copied from
`D:\code\sfos-carlife\harbour-sailplay` on 2026-11-24. Sailplay contributors
retain their copyright. The protocol implementation and application fork are
GPL-3.0-or-later; see LICENSE. Runtime identities were changed to Sailconnect;
unused projection, vehicle, audio and network-management modules were removed.
Bluetooth bootstrap, accessory challenge verification and the iAP2 link/tunnel
are retained for existing wireless CarPlay receivers. Screen capture uses the
local network; the application does not alter Wi-Fi configuration. RTSP pairing
and encryption remain part of the network screen transport.
The source workspace HEAD was `e29d1bf7d62b7689fab35667e97a76a4d9e246be`;
the copied files are a workspace snapshot and may include its uncommitted changes.

The capture recorder derives from CODeRUS/screencast and giucam/nemomobile
(LGPL-2.1); original notices in the source and protocol XML are retained.
Conversion and encoding helpers derive from harbour-imira as carried by
Sailplay. x264 is GPL-2.0-or-later and is linked statically. Its corresponding
source is included in `third_party/x264.tar.gz`; the SDK script builds it
inside this project's build directory, with no dependency on Sailplay binaries.

Distribution must include the corresponding source for this application and
the exact x264 build. A prebuilt static library alone is not a source offer.

# Launcher icon template

The launcher icon base follows the opposite-corner circle-and-square shape in
Jolla's Sailfish Apps Icon Template, available at <https://sailfishos.org/design/icons/>.
The template is published under CC BY 3.0; its accompanying readme explicitly
waives attribution. The phone, receiver and transfer arrow are drawn for Sailconnect.
