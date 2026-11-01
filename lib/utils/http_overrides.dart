import 'dart:io';

// Capture builds for tools/replay pass --dart-define=PDA_PROXY=host:port. Dart's HttpClient
// does not use the Android proxy, so without this the API calls would bypass mitmproxy.
const String _proxy = String.fromEnvironment('PDA_PROXY');

class MyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(context)
      ..badCertificateCallback = (X509Certificate cert, String host, int port) => true;
    if (_proxy.isNotEmpty) client.findProxy = (uri) => 'PROXY $_proxy';
    return client;
  }
}
