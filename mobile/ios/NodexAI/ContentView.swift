import SwiftUI
import WebKit

// Point to your Railway hosted instance
let BASE_URL = "https://nodex-panel-production.up.railway.app"

struct ContentView: View {
    var body: some View {
        WebView(url: URL(string: BASE_URL)!)
            .ignoresSafeArea()
    }
}

struct WebView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 13/255, green: 17/255, blue: 23/255, alpha: 1)
        webView.scrollView.bounces = false

        let request = URLRequest(url: url)
        webView.load(request)
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

#Preview {
    ContentView()
}
