/// Deliberately independent of response bodies and exception strings.
String requestFailureMessage([int? statusCode]) => switch (statusCode) {
  400 || 422 => 'Please check your details and try again.',
  401 || 403 => 'This action is not available for this session.',
  404 => 'This item is no longer available. Refresh and try again.',
  409 => 'This item has changed. Refresh and try again.',
  429 => 'Things are busy right now. Please try again shortly.',
  _ => 'ARC is temporarily unavailable. Please try again in a moment.',
};
