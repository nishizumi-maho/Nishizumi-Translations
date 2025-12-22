# Requires PyInstaller and PySide6 installed
python -m pip install jp2subs[gui] pyinstaller
pyinstaller --name jp2subs-gui --onefile --noconfirm --add-data "README.md;." --console -m jp2subs.gui.main

