%global debug_package %{nil}
%global __spec_install_post %{lua: print(""); }

Name:           FFConverter
Version:        1.1.0
Release:        1
Summary:        Simple video, audio, and image converter
License:        GPL-3.0-or-later
Group:          Applications/Multimedia
URL:            https://github.com/369arc/FFconverter
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
AutoReqProv:    no

Requires:       python3
Requires:       python3-tkinter
Requires:       libXcursor
Recommends:     ffmpeg

%description
FFConverter is a graphical frontend for FFmpeg that converts video, audio,
and image files between common formats. The Python GUI dependencies are
bundled in the package, so no pip installation or network access is required.

%prep
%setup -q

%build
# Pure Python: nothing to compile.

%install
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_datadir}/ffconverter
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/icons/hicolor/256x256/apps

cp -a ffc.py run.sh LICENSE ffconverter.png resources vendor \
    %{buildroot}%{_datadir}/ffconverter/
install -m 644 usr/share/applications/ffconverter.desktop \
    %{buildroot}%{_datadir}/applications/ffconverter.desktop
install -m 644 usr/share/icons/hicolor/256x256/ffconverter.png \
    %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/ffconverter.png

cat > %{buildroot}%{_bindir}/FFConverter <<'EOF'
#!/bin/sh
exec /usr/share/ffconverter/run.sh "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/FFConverter
ln -s FFConverter %{buildroot}%{_bindir}/ffconverter

%files
%{_bindir}/FFConverter
%{_bindir}/ffconverter
%{_datadir}/ffconverter
%{_datadir}/applications/ffconverter.desktop
%{_datadir}/icons/hicolor/256x256/apps/ffconverter.png
%license LICENSE
%doc README.md
%doc THIRD_PARTY_NOTICES.md

%changelog
* Thu Oct 22 2026 369ARC <email@369arc.com> - 1.1.0-1
- Bundle Python dependencies; remove install-time pip/root network access
- Fix launch wrapper, desktop entry and package metadata
- Fix conversion pipeline, progress, cancellation and output collisions
