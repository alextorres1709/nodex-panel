#!/bin/bash
# ─────────────────────────────────────
# NodexAI Panel — Release Script
# Usage: ./scripts/release.sh 1.4.0
# Requires: gh (GitHub CLI) installed
# ─────────────────────────────────────
set -e

VERSION="${1:?Usage: $0 <version> (e.g. 1.4.0)}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DMG_NAME="NodexAI-Panel.dmg"
DMG_PATH="$PROJECT_DIR/dist/$DMG_NAME"

echo "══════════════════════════════════════"
echo "  NodexAI Panel — Release v${VERSION}"
echo "══════════════════════════════════════"

# 1. Update version in config.py
echo ""
echo "→ Updating version to ${VERSION}..."
sed -i '' "s/APP_VERSION = \".*\"/APP_VERSION = \"${VERSION}\"/" "$PROJECT_DIR/config.py"

# 2. Build
echo "→ Building app..."
cd "$PROJECT_DIR"
python3 -m PyInstaller nodexai-panel.spec --noconfirm --clean 2>&1 | tail -3

# 3. Create DMG
echo "→ Creating DMG..."
hdiutil create -volname "NodexAI Panel" \
    -srcfolder "$PROJECT_DIR/dist/NodexAI Panel.app" \
    -ov -format UDZO "$DMG_PATH" 2>&1 | tail -1

# 4. Install locally
echo "→ Installing locally..."
killall "NodexAI Panel" 2>/dev/null || true
rm -rf "/Applications/NodexAI Panel.app"
cp -R "$PROJECT_DIR/dist/NodexAI Panel.app" "/Applications/"

# 5. Git commit + push
echo "→ Committing and pushing..."
cd "$PROJECT_DIR"
git add .
git commit -m "release: v${VERSION}" 2>/dev/null || echo "  (nothing to commit)"
git push origin main

# 6. Create GitHub Release
echo "→ Creating GitHub Release v${VERSION}..."
gh release create "v${VERSION}" \
    "$DMG_PATH" \
    --title "v${VERSION}" \
    --notes "NodexAI Panel v${VERSION}" \
    --latest

echo ""
echo "══════════════════════════════════════"
echo "  ✅ Release v${VERSION} published!"
echo "  DMG: $DMG_PATH"
echo "══════════════════════════════════════"
