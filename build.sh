#!/bin/zsh
# Build "PDF Vault.app" with PyInstaller and zip it for release.
# Usage: ./build.sh
set -e
cd "$(dirname "$0")"

PYTHON=.venv/bin/python
VERSION=$($PYTHON -c "from pdf_core import __version__; print(__version__)")
echo "Building PDF Vault $VERSION..."

rm -rf build dist
$PYTHON -m PyInstaller \
  --windowed \
  --name "PDF Vault" \
  --icon images/PDFVault.icns \
  --osx-bundle-identifier "com.bennphu.pdfvault" \
  --add-data "web:web" \
  --noconfirm \
  app.py

# Stamp the version into Info.plist
PLIST="dist/PDF Vault.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PLIST"

# Usage descriptions so macOS shows a permission prompt (instead of a silent
# denial) when the storage folder lives in Documents/Desktop/Downloads
for KEY in NSDocumentsFolderUsageDescription NSDesktopFolderUsageDescription NSDownloadsFolderUsageDescription; do
  /usr/libexec/PlistBuddy -c "Set :$KEY 'PDF Vault stores and manages your PDF library in the folder you choose.'" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :$KEY string 'PDF Vault stores and manages your PDF library in the folder you choose.'" "$PLIST"
done

# Optional codesigning: set CODESIGN_ID to your "Developer ID Application: ..." identity
if [ -n "$CODESIGN_ID" ]; then
  echo "Codesigning with $CODESIGN_ID..."
  codesign --deep --force --options runtime --sign "$CODESIGN_ID" "dist/PDF Vault.app"
fi

# Zip for distribution / GitHub Releases
cd dist
ZIP="PDF-Vault-$VERSION-macos.zip"
ditto -c -k --keepParent "PDF Vault.app" "$ZIP"
SHA=$(shasum -a 256 "$ZIP" | awk '{print $1}')
echo ""
echo "Built dist/$ZIP"
echo "SHA256: $SHA"
echo ""
echo "Include the line above in the GitHub release notes so the"
echo "auto-updater can verify the download."
