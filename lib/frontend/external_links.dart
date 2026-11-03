/// External destinations come from API data, so validate them before launching.
Uri? trustedExternalUri(String? value, String expectedHost) {
  final uri = Uri.tryParse(value ?? '');
  if (uri == null ||
      uri.scheme != 'https' ||
      uri.host != expectedHost ||
      uri.userInfo.isNotEmpty ||
      uri.port != 443) {
    return null;
  }
  return uri;
}
