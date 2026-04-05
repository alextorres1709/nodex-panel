# NodexAI Panel — Mobile Apps

Thin WebView wrappers that load the hosted NodexAI Panel from Railway.

## Prerequisites

1. Deploy the panel to Railway with `HOSTED_MODE=true`:
   ```bash
   # From the nodex-panel root directory
   railway up
   ```
2. Update `BASE_URL` in each app to point to your Railway URL.

## Android (APK)

1. Open `mobile/android/` in Android Studio
2. Update `BASE_URL` in `MainActivity.kt` with your Railway URL
3. Build > Generate Signed APK
4. Min SDK: Android 7.0 (API 24)

## iOS

1. Open `mobile/ios/` in Xcode (create a new project, add the Swift files)
2. Update `BASE_URL` in `ContentView.swift` with your Railway URL
3. Set bundle identifier to `es.nodexai.panel`
4. Archive > Distribute to App Store / TestFlight
5. Min target: iOS 16.0
