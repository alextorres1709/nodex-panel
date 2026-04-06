# WebView
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface
-keep class es.nodexai.panel.** { *; }

# Firebase Cloud Messaging — keep messaging service + model classes so the
# release build can still receive push notifications after R8 minification.
-keep class com.google.firebase.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.firebase.**
-dontwarn com.google.android.gms.**
-keepclassmembers class * extends com.google.firebase.messaging.FirebaseMessagingService {
    public *;
}
